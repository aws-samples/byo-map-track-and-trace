# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import geopandas as gpd
import osmnx as ox
import pandas as pd
import shapely
from shapely import LineString


# to find source and dest, find the closest point on the graph (looking at edges)
# once you've got an edge, split it on the nearest point and inject 3 new edges: 1) from the source point to the nearest point on the existing network, 2) split the edge on the point and insert both halves (with distances calculated)
def split_graph(G, target, edges, utm, extend=True):
    """Split a graph on a target point, generating new nodes and edges as necessary. Optionally extend the graph to include a path to the target. Returns (node ID, point) where node ID is the ID assigned to the target and point is the target's position, which will be on the original graph if extend=False"""

    # TODO implement extend

    # find the closest edge to the input point
    # there will be 2 results (since we have 2 edges for each segment)
    candidates = gpd.sjoin_nearest(
        gpd.GeoDataFrame(geometry=[target], crs=4326).to_crs(utm),
        edges.to_crs(utm),
        how="inner",
    )[["u", "v", "key"]]

    # join to edges to get segment geometry (vs. point geometry)
    candidates = edges.join(candidates.set_index(["u", "v", "key"]), how="inner")

    # get the highest vertex ID in use (for use as a starting point for new nodes)
    node_id = max(edges.index.max()) + 1

    # initialize the list of new nodes
    new_nodes = gpd.GeoDataFrame(
        {
            "x": [target.x],
            "y": [target.y],
            "point_geom": [target],
        },
        geometry="point_geom",
        crs=4326,
        index=[node_id],
    )

    # pull the segment geometry out to work with
    edge = candidates.iloc[0]
    closest_line = edge["geometry"]

    # locate the closest point on the segment
    normalized_distance = closest_line.line_locate_point(target, normalized=True)
    point_on_line = closest_line.interpolate(normalized_distance, normalized=True)

    if normalized_distance > 0 and normalized_distance < 1:
        # split the segment at that point (using distance is more forgiving than splitting on a point that MUST be coincident with the line)
        left = shapely.ops.substring(
            closest_line, 0, normalized_distance, normalized=True
        )
        right = shapely.ops.substring(
            closest_line, normalized_distance, 1, normalized=True
        )

        intermediate_node_id = node_id + 1

        new_nodes = pd.concat(
            [
                new_nodes,
                gpd.GeoDataFrame(
                    {
                        "x": [point_on_line.x],
                        "y": [point_on_line.y],
                        "point_geom": [point_on_line],
                    },
                    geometry="point_geom",
                    crs=4326,
                    index=[intermediate_node_id],
                ),
            ]
        )

        new_edges = gpd.GeoDataFrame(
            {
                "u": [edge.name[0], intermediate_node_id, intermediate_node_id],
                "v": [intermediate_node_id, edge.name[1], node_id],
                "key": 0,
            },
            geometry=[left, right, LineString([point_on_line, target])],
            crs=4326,
        )

    elif normalized_distance <= 0:
        new_edges = gpd.GeoDataFrame(
            {
                "u": [edge.name[0]],
                "v": [node_id],
                "key": 0,
            },
            geometry=[LineString([point_on_line, target])],
            crs=4326,
        )

    elif normalized_distance >= 1:
        new_edges = gpd.GeoDataFrame(
            {
                "u": [edge.name[1]],
                "v": [node_id],
                "key": 0,
            },
            geometry=[LineString([point_on_line, target])],
            crs=4326,
        )

    # calculate length using the intermediate CRS (to ensure that we're using the same units as before)
    new_edges["length"] = round(new_edges.to_crs(utm).length, 2)

    # reverse edges
    reversed_new_edges = new_edges.rename(columns={"u": "v", "v": "u"})

    # indicate which edges have been reversed
    reversed_new_edges["key"] = 1

    all_new_edges = pd.concat([new_edges, reversed_new_edges]).set_index(
        ["u", "v", "key"]
    )

    G.update(ox.convert.graph_from_gdfs(new_nodes, all_new_edges))

    return (node_id, pd.concat([edges, all_new_edges]), target)
