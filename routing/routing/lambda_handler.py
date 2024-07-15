# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
from collections import defaultdict

import boto3
import botocore
import geopandas as gpd
import osmnx as ox
import pandas as pd
from pyproj import Transformer
from shapely import GeometryCollection, Point, Polygon
from shapely.ops import transform

from routing import split_graph

GRAPH = os.environ.get("GRAPH", "./data/graph.gml")

# load the network (as GML) from disk
original_graph = ox.load_graphml(GRAPH)

# fetch edges
(nodes, edges) = ox.convert.graph_to_gdfs(original_graph)

# estimate the UTM zone that covers the graph (for use as an intermediate CRS when meters are needed as units) using the nodes
utm = nodes.estimate_utm_crs()

# create projection functions between WGS84 and the appropriate UTM zone
project = Transformer.from_crs(nodes.crs, utm, always_xy=True).transform
inv_project = Transformer.from_crs(utm, nodes.crs, always_xy=True).transform


class LambdaException(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def parse_arn(arn):
    # http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html
    elements = arn.split(":", 5)
    result = {
        "arn": elements[0],
        "partition": elements[1],
        "service": elements[2],
        "region": elements[3],
        "account": elements[4],
        "resource": elements[5],
        "resource_type": None,
    }
    if "/" in result["resource"]:
        result["resource_type"], result["resource"] = result["resource"].split("/", 1)
    elif ":" in result["resource"]:
        result["resource_type"], result["resource"] = result["resource"].split(":", 1)
    return result


def remap_missing_nodes(starting_node_id, removed_nodes):
    current_missing_node_id = starting_node_id

    def remap(row):
        nonlocal current_missing_node_id

        (u, v, key) = row

        if u in removed_nodes:
            u = current_missing_node_id
            current_missing_node_id += 1

        if v in removed_nodes:
            v = current_missing_node_id
            current_missing_node_id += 1

        return (u, v, key)

    return remap


def prefetch_geofences(areas):
    geofences = {}

    arns = list(
        map(
            lambda x: (x, parse_arn(x)),
            map(
                lambda x: x["Area"]["Arn"],
                filter(lambda x: "Arn" in x.get("Area", {}), areas),
            ),
        )
    )

    if arns:
        # group areas by region/resource since we'll need to make requests for each
        grouped = defaultdict(lambda: defaultdict(str))
        for arn, arn_components in arns:
            arn_without_id = arn.split("#")[0]

            if arn_without_id not in grouped[arn_components["region"]]:
                grouped[arn_components["region"]][
                    arn_components["resource"].split("#")[0]
                ] = arn_without_id

        # fetch all geofence geometries from referenced geofence collections
        for region, resources in grouped.items():
            client = boto3.client("location", region_name=region)
            for resource, arn in resources.items():
                paginator = client.get_paginator("list_geofences")
                pages = paginator.paginate(CollectionName=resource)

                try:
                    for page in pages:
                        for geofence in page["Entries"]:
                            geofences[f"{arn}#{geofence["GeofenceId"]}"] = geofence
                except botocore.exceptions.ClientError as e:
                    print(e)
                    raise LambdaException(
                        500,
                        f"Unable to pre-fetch geofences ({region} / {resource})",
                    )

    return geofences


def get_exclusion_areas(areas, geofences):
    exclusion_areas = []

    for area in areas:
        _area = area.get("Area", {})
        circle = _area.get("Circle")
        polygon = _area.get("Polygon")
        arn = _area.get("Arn")

        if len(list(filter(lambda x: x, [circle, polygon, arn]))) != 1:
            raise LambdaException(
                400, "Only one of {Circle, Polygon, Arn} may be provided per Area."
            )

        # fetch geofences and override point_area+point_radius / polygon as appropriate
        if arn:
            arn_components = parse_arn(arn)
            if arn_components["service"] != "geo":
                raise LambdaException(
                    400, f"Unrecognized service: {arn_components['service']}"
                )

            if arn not in geofences:
                raise LambdaException(500, f"Unable to fetch geofence ({arn})")

            geofence = geofences[arn]

            if geofence["Geometry"].get("Polygon"):
                polygon = geofence["Geometry"]["Polygon"]

            elif geofence["Geometry"].get("Circle"):
                circle = geofence["Geometry"]["Circle"]

        try:
            if circle:
                center = Point(*circle["Center"])
                radius = circle["Radius"]
                exclusion_areas.append(
                    transform(inv_project, transform(project, center).buffer(radius))
                )
        except Exception as e:
            raise LambdaException(400, f"Invalid Circle area: {e}")

        try:
            if polygon:
                exclusion_areas.append(Polygon(*polygon))
        except Exception as e:
            raise LambdaException(400, f"Invalid Polygon area: {e}")

    return GeometryCollection(exclusion_areas)


def handle(event, context=None):
    try:
        body = json.loads(event["body"])

        # validate that Origin and Destination exist in the request body

        # get the origin and destination from the request body
        origin = Point(*body["Origin"])
        destination = Point(*body["Destination"])

        # circle, polygon, and geofence restricted areas
        areas = body.get("Avoid", {}).get("Areas", [])

        # create a copy of the graph to modify with exclusion areas and origin/destination vertices
        G = original_graph.copy()

        # generate a list of exclusion areas (using UTM coordinates to support radii)

        # if ARNs were provided, pre-fetch geofence geometries
        geofences = prefetch_geofences(areas)

        # extract and resolve exclusion areas from the request
        exclusion_areas = get_exclusion_areas(areas, geofences)

        if exclusion_areas:
            # create local copies of nodes + edges so that they can be manipulated
            local_nodes = nodes.copy()
            # filter out reversed edges
            local_edges = edges.xs(0, level="key").copy()

            # re-index
            local_edges["key"] = 0
            local_edges = local_edges.reset_index().set_index(["u", "v", "key"])

            # update node and edge geometries to reflect the exclusion areas
            # node geometries will be empty if they were masked out
            local_nodes["geometry"] = nodes.difference(exclusion_areas)
            local_edges["geometry"] = edges.difference(exclusion_areas)

            # re-calculate length (for the edges that got clipped)
            local_edges["length"] = round(local_edges.to_crs(utm).length, 2)

            # generate a list of nodes to remove (because they were masked out)
            nodes_to_remove = local_nodes[local_nodes.is_empty]

            # update the list of nodes used for this operation
            local_nodes = local_nodes[~local_nodes.is_empty]

            # remap missing node IDs to new IDs to avoid sharing IDs (even if nodes with these IDs are absent from the graph, they will be used as vertices for routing)
            local_edges.index = local_edges.index.map(
                remap_missing_nodes(nodes.index.max() + 1, nodes_to_remove.index)
            )

            # create new intermediate nodes
            max_node_id = nodes.index.max()

            def make_nodes(row):
                (u, v, _) = row.name

                if u > max_node_id:
                    # use the leftmost point
                    row["u_geometry"] = Point(*row.geometry.coords[0])

                if v > max_node_id:
                    # use the rightmost point
                    row["v_geometry"] = Point(*row.geometry.coords[-1])

                return row

            extra_nodes = local_edges.apply(make_nodes, axis=1).reset_index()

            # massage + merge nodes to account for nodes that are source- or destination-only
            new_nodes = pd.concat(
                [
                    gpd.GeoDataFrame(
                        extra_nodes[extra_nodes["u_geometry"].notna()][
                            ["u", "u_geometry"]
                        ]
                        .rename(columns={"u": "osmid", "u_geometry": "geometry"})
                        .set_index(["osmid"]),
                        geometry="geometry",
                        crs=4326,
                    ),
                    gpd.GeoDataFrame(
                        extra_nodes[extra_nodes["v_geometry"].notna()][
                            ["v", "v_geometry"]
                        ]
                        .rename(columns={"v": "osmid", "v_geometry": "geometry"})
                        .set_index(["osmid"]),
                        geometry="geometry",
                        crs=4326,
                    ),
                ]
            ).drop_duplicates()

            # set x/y values for OSMnx
            new_nodes["x"] = new_nodes.geometry.x
            new_nodes["y"] = new_nodes.geometry.y

            # create a comprehensive list of nodes that should be used for this request
            local_nodes = pd.concat([local_nodes, new_nodes])

            # reverse edges
            reversed_edges = local_edges.reset_index().rename(
                columns={"u": "v", "v": "u"}
            )
            reversed_edges["key"] = 1
            reversed_edges = reversed_edges.set_index(["u", "v", "key"])

            # create a comprehensive list of edges that should be used for this request
            local_edges = pd.concat([local_edges, reversed_edges])

            # create a new graph for this request
            G = ox.convert.graph_from_gdfs(local_nodes, local_edges)
        else:
            # no manipulation is necessary; reference the original graph instead
            local_nodes = nodes
            local_edges = edges

        # split the graph to include origin/destination points
        (origin_id, all_edges, _) = split_graph(
            G, origin, local_edges, utm, extend=True
        )
        (destination_id, _, _) = split_graph(
            G, destination, all_edges, utm, extend=True
        )

        # TODO what happens if the path to the nearest point on the graph passes through an exclusion area?
        # find nearest edges and iterate over them until one is found that doesn't require crossing an exclusion area

        route = ox.shortest_path(G, origin_id, destination_id, weight="length")

        if route is None:
            raise LambdaException(404, "No route found.")

        route_geojson = ox.routing.route_to_gdf(G, route).to_json(drop_id=True)

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/geo+json",
            },
            "body": route_geojson,
        }
    except LambdaException as e:
        return {
            "statusCode": e.status,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps(
                {
                    "Error": e.message,
                }
            ),
        }
