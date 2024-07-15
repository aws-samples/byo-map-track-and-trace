# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import sys

import click
import geopandas as gpd
import osmnx as ox
import pandas as pd
import shapely
from shapely import LineString, Point


def flatten(xss):
    return [x for xs in xss for x in xs]


# cluster coordinates within `threshold` to snap them to the same point
# multiple invocations may be necessary to re-cluster overlapping clusters
def cluster(coords, intermediate_crs, threshold):
    transformed_coords = coords.to_crs(intermediate_crs)[
        ["x", "y", "point_geom"]
    ].reset_index(drop=True)

    cluster_pairs = (
        gpd.sjoin_nearest(
            transformed_coords,
            transformed_coords,
            max_distance=threshold,
            exclusive=True,
        ).rename(columns={"index_left": "a", "index_right": "b"})
    ).rename_axis(["a"])

    # group destinations
    dest_groups = cluster_pairs.groupby("a")[["b"]].agg(list)
    # can't group on lists, so create a string version that works
    dest_groups["b_str"] = dest_groups["b"].astype(str)

    # group origins
    origin_groups = pd.DataFrame(
        dest_groups.index.to_frame(name="a")
        .merge(dest_groups, left_index=True, right_index=True)
        .groupby("b_str")[["a", "b"]]
        # .agg(list)
        .agg({"a": list, "b": lambda x: set(flatten(x))})
        .apply(lambda x: set(x["a"] + list(x["b"])), axis=1)
        .reset_index(drop=True),
        columns=["vertices"],
    )
    origin_groups["vertices_str"] = origin_groups["vertices"].astype(str)

    # generate clusters (union of (a,b))
    clusters = (
        origin_groups.groupby(by=["vertices_str"])
        .agg(
            "first"
        )  # instead of first, consider calculating the centroid and using that as the point geometry instead
        .reset_index(drop=True)
        .rename_axis(["cluster"])
    )

    # prepare to join back to original coordinates
    pre_clustered = clusters.explode(column="vertices").rename(
        columns={"vertices": "vertex"}
    )

    # use the first referenced vertex as the shared point **for clustered vertices**
    pre_clustered_with_xy = pre_clustered.join(transformed_coords, on="vertex")[
        ["vertex", "x", "y"]
    ]

    # calculate the centroid of each cluster and use that as the calculated vertex
    # NOTE can look up vertex by using clusters["cluster"]
    clustered = (
        pre_clustered_with_xy.groupby(by=["cluster"])
        .agg({"vertex": list, "x": "mean", "y": "mean"})
        .reset_index()
    )

    # get the non-clustered vertices (RIGHT join)
    all = pre_clustered.reset_index().join(transformed_coords, how="right", on="vertex")

    non_clustered = all[all["cluster"].isna()][["vertex", "x", "y"]]

    # generate the complete list of unique coordinates
    uniq_coords = (
        pd.concat([clustered.explode("vertex"), non_clustered])
        .drop(columns=["cluster"])
        .groupby(by=["x", "y"])
        .agg(list)
        .reset_index()
    )

    # NOTE vertex is a key into transformed_coords
    nodes = gpd.GeoDataFrame(
        uniq_coords,
        geometry=gpd.points_from_xy(uniq_coords["x"], uniq_coords["y"], crs=4326),
        crs=4326,
    ).rename_axis(["node_id"])

    return (
        nodes.rename(columns={"geometry": "point_geom"})
        .set_geometry("point_geom")
        .drop(columns=["vertex"])
    )


def get_coords(gdf):
    # node geometries (create shared vertices where lines cross) and merge linework into a single feature that gets broken into its constituent geometries
    lines = (
        gpd.GeoDataFrame(geometry=shapely.node(gdf[["geometry"]]).line_merge())
        .explode(ignore_index=True)
        .rename_axis(["line_id"])
    )

    coords = lines.get_coordinates(index_parts=True).rename_axis(["line_id", "idx"])
    coords = coords.merge(lines, on=["line_id"])
    coords["terminal"] = coords.apply(
        lambda x: x["geometry"].coords[0] == (x["x"], x["y"])
        or x["geometry"].coords[-1] == (x["x"], x["y"]),
        axis=1,
    )
    coords["point_geom"] = coords.apply(lambda x: Point(x["x"], x["y"]), axis=1)
    coords = gpd.GeoDataFrame(coords, geometry="point_geom", crs=4326)

    return coords


def make_nodes(gdf, intermediate_crs, threshold=5):
    """Generate a set of nodes from approximately-overlapping vertices present in an input GeoDataFrame"""

    # dump coordinates (start and end are insufficient; we need to find shared vertices that might be in the middle)
    coords = get_coords(gdf)

    # generate nodes (id, x, y)

    nodes = cluster(
        cluster(coords, intermediate_crs=intermediate_crs, threshold=threshold),
        intermediate_crs=intermediate_crs,
        threshold=threshold,
    )

    return nodes


def make_edges(gdf, nodes, intermediate_crs, threshold=5):
    """Generate a set of edges (u, v, key, [attributes], [id])"""

    coords = get_coords(gdf)

    # update linestrings to use substituted coordinates (snapped) and segment them
    # this assumes that vertices exist where lines are expected to intersect (vs. crossing or terminating on a line)

    # TODO join coordinates to itself, since the segmentation process should be a precursor to generating nodes (rather than the other way around)
    pairs = gpd.sjoin(
        coords.to_crs(intermediate_crs),
        nodes.to_crs(intermediate_crs),
        predicate="dwithin",
        distance=threshold,
    )

    # this assumes that a vertex exists (even it it doesn't match) on a segment intersected by another line
    # TODO split nearby lines on the nearest point on that line to the vertex on another line
    gpd.sjoin(
        coords.to_crs(intermediate_crs),
        coords.to_crs(intermediate_crs),
        predicate="dwithin",
        distance=threshold,
    )

    def fn(x):
        geom = x["geometry"]
        substitutions = x["substitutions"]
        coords = list(geom.coords)

        # apply substitutions
        for i, s in substitutions:
            coords[i] = s

        # get split locations
        splits = list(set([0] + [i for (i, s) in substitutions] + [len(coords) - 1]))

        pieces = []

        if len(splits) == 2:
            # just 1 piece
            pieces = [LineString(coords)]
        else:
            for i in range(0, len(splits) - 1):
                start, end = splits[i], splits[i + 1]
                pieces.append(LineString(coords[start : end + 1]))

        return pieces

    pairs["substitutions"] = pairs.apply(
        lambda x: (
            list(x["geometry"].coords).index((x["x_left"], x["y_left"])),
            (x["x_right"], x["y_right"]),
        ),
        axis=1,
    )
    with_substitutions = pairs.groupby(by=["line_id"])[
        ["node_id", "geometry", "substitutions"]
    ].agg({"node_id": list, "geometry": "first", "substitutions": set})
    # apply substitutions and split
    with_substitutions["geometry"] = with_substitutions.apply(fn, axis=1)

    segments = with_substitutions.explode("geometry")[["geometry"]]
    segments["first_x"] = segments["geometry"].apply(lambda x: x.coords[0][0])
    segments["first_y"] = segments["geometry"].apply(lambda x: x.coords[0][1])
    segments["last_x"] = segments["geometry"].apply(lambda x: x.coords[-1][0])
    segments["last_y"] = segments["geometry"].apply(lambda x: x.coords[-1][1])

    segments = gpd.GeoDataFrame(segments, geometry="geometry", crs=4326)

    xy_nodes = nodes.set_index(["x", "y"], append=True).drop(columns="point_geom")

    with_start = xy_nodes.rename_axis(["u", "first_x", "first_y"]).join(
        segments.set_index(["first_x", "first_y"]), how="right"
    )

    edges = gpd.GeoDataFrame(
        with_start.reset_index(level=["u"])
        .set_index(["last_x", "last_y"])
        .join(xy_nodes.rename_axis(["v", "last_x", "last_y"]), how="left")
        .reset_index(level=["v"]),
        geometry="geometry",
        crs=4326,
    )
    edges["key"] = 0

    # remove self-edges
    edges = edges[edges["u"] != edges["v"]]
    # calculate lengths for each edge (using an intermediate CRS where units are meters)
    edges["length"] = round(edges.to_crs(intermediate_crs).length, 2)

    # create a DF with reversed node IDs
    reversed_edges = edges.rename(columns={"u": "v", "v": "u"})
    # indicate which edges have been reversed
    reversed_edges["key"] = 1

    # finalize edge creation by merging directions and creating an index
    edges = pd.concat([edges, reversed_edges]).set_index(["u", "v", "key"])

    return edges


def prepare(input):
    """Prepare GML suitable for loading into an OSMnx / NetworkX graph"""
    gdf = gpd.read_file(input)

    # estimate the UTM zone that covers our area of interest
    utm = gdf.estimate_utm_crs()

    # generate nodes and edges
    nodes = make_nodes(gdf, intermediate_crs=utm)
    edges = make_edges(gdf, nodes, intermediate_crs=utm)

    # return an OSMnx (NetworkX) graph
    return ox.convert.graph_from_gdfs(nodes, edges)


@click.command()
@click.option(
    "--input",
    type=click.Path(exists=True),
    help="Input GeoJSON (if not provided on stdin)",
)
@click.argument("output", type=click.Path())
def cli(input, output):
    ox.io.save_graphml(prepare(input or sys.stdin), output)


if __name__ == "__main__":
    cli()
