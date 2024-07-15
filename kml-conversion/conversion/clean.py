# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import itertools
import json
import sys

import click
import geojson
import geojson.utils
from shapely import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Polygon,
    force_2d,
    make_valid,
    union_all,
)
from shapely.geometry import shape

grid_size = 0.000001
# we got 1e-10 by eyeballing the histogram of areas between adjacent triangles
sliver_threshold = 1e-10


def tweeze(geometry):
    """
    Remove polygon slivers
    """
    if isinstance(geometry, Polygon):
        holes = []
        for interior in geometry.interiors:
            p = Polygon(interior)
            if p.area > sliver_threshold:
                holes.append(interior)

        return Polygon(geometry.exterior.coords, holes=holes)

    elif isinstance(geometry, MultiPolygon):
        return MultiPolygon(list(map(tweeze, geometry.geoms)))

    elif isinstance(geometry, GeometryCollection):
        return GeometryCollection(list(map(tweeze, geometry.geoms)))

    return geometry


def lint_roll(geometry):
    """
    Remove LineStrings from GeometryCollections that also contain Polygons
    """
    if isinstance(geometry, GeometryCollection):
        polygons = list(filter(lambda x: isinstance(x, Polygon), geometry.geoms))
        linestrings = list(filter(lambda x: isinstance(x, LineString), geometry.geoms))

        if polygons and linestrings:
            if len(polygons) > 1:
                return MultiPolygon(polygons)
            else:
                return polygons[0]

    return geometry


def clean_geometries(fc):
    """
    Clean geometries. This assumes that the GeoJSON has already been wound correctly (potentially using @mapbox/geojson-rewind)
    """
    sys.stdout.write("""{"type":"FeatureCollection","features":[\n""")

    def keyfunc(x):
        return json.dumps(x["properties"])

    # group features according to their properties
    # this may have the side-effect of re-ordering features and introducing visual artifacts
    grouped = itertools.groupby(
        sorted(
            filter(lambda x: x["properties"].get("visibility", True), fc["features"]),
            key=keyfunc,
        ),
        keyfunc,
    )

    for i, (k, features) in enumerate(grouped):
        properties = json.loads(k)

        # prepare geometries: convert from GeoJSON, drop Z-coordinate, make valid
        geometries = list(
            map(lambda f: make_valid(force_2d(shape(f["geometry"]))), features)
        )

        # union geometries together
        unioned = union_all(geometries)

        # remove sliver polygons
        tweezed = tweeze(unioned)

        # remove extraneous linestrings
        rolled = lint_roll(tweezed)

        new_feature = geojson.Feature(geometry=rolled, properties=properties)

        if i > 0:
            sys.stdout.write(",")
        sys.stdout.write(geojson.dumps(new_feature))
        sys.stdout.write("\n")

    sys.stdout.write("""]}\n""")


@click.command()
@click.option(
    "--input",
    type=click.File("r"),
    default=sys.stdin,
    help="Input GeoJSON (if not provided on stdin)",
)
def cli(input):
    clean_geometries(geojson.load(input))


if __name__ == "__main__":
    clean_geometries(geojson.load(sys.stdin))
