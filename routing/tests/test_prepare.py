# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from io import StringIO
import json

import pytest

from routing.prepare import prepare


def as_geojson(features):
    return StringIO(json.dumps({"type": "FeatureCollection", "features": features}))


def test_prepare_simple():
    input = as_geojson(
        [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[1, 1], [2, 2]]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[1, 1], [2, 0]]},
            },
        ]
    )

    graph = prepare(input)

    assert len(graph.nodes) == 4, graph.nodes
    # it's a digraph, so there are double the number of edges
    assert len(graph.edges) == 3 * 2, graph.edges


def test_prepare_disconnected():
    input = as_geojson(
        [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[1, 1], [2, 2]]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[1, 1], [2, 0]]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 1], [0, 2]]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 2], [0, 3]]},
            },
        ]
    )
    graph = prepare(input)

    assert len(graph.nodes) == 7
    assert len(graph.edges) == 5 * 2


def test_prepare_approximate():
    input = as_geojson(
        [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0, 0], [1.00001, 1]],
                },
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[1, 1], [2, 2]],
                },
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0.99998, 1], [2, 0]],
                },
            },
        ]
    )

    graph = prepare(input)

    assert len(graph.nodes) == 4, graph.nodes
    # it's a digraph, so there are double the number of edges
    assert len(graph.edges) == 3 * 2, graph.edges


@pytest.mark.skip(
    reason="make_edges needs to node geometries in order to segment them properly"
)
def test_prepare_segmentation_necessary():
    input = as_geojson(
        [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [2, 2]]},
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[1, 1], [2, 0]]},
            },
        ]
    )

    graph = prepare(input)

    assert len(graph.nodes) == 4, graph.nodes
    # it's a digraph, so there are double the number of edges
    assert len(graph.edges) == 3 * 2, graph.edges
