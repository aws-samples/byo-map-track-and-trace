# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
from unittest.mock import patch

import botocore
import pytest

from routing.lambda_handler import handle


@pytest.fixture
def fixture_path():
    return f"{os.path.dirname(os.path.realpath(__file__))}/fixtures"


@pytest.fixture
def simple_route_request(fixture_path):
    with open(f"{fixture_path}/simple-route-request.json", "r") as f:
        return json.loads(f.read())


@pytest.fixture
def simple_route_response(fixture_path):
    with open(f"{fixture_path}/simple-route-response.json", "r") as f:
        return json.loads(f.read())


@pytest.fixture
def route_request_with_avoidance_areas(fixture_path):
    with open(f"{fixture_path}/route-request-with-avoidance-areas.json", "r") as f:
        return json.loads(f.read())


@pytest.fixture
def route_response_with_avoidance_areas(fixture_path):
    with open(f"{fixture_path}/route-response-with-avoidance-areas.json", "r") as f:
        return json.loads(f.read())


@pytest.fixture
def route_request_with_invalid_avoidance_areas(fixture_path):
    with open(
        f"{fixture_path}/route-request-with-invalid-avoidance-areas.json", "r"
    ) as f:
        return json.loads(f.read())


@pytest.fixture
def route_request_with_geofenced_avoidance_areas(fixture_path):
    with open(
        f"{fixture_path}/route-request-with-geofenced-avoidance-areas.json", "r"
    ) as f:
        return json.loads(f.read())


@pytest.fixture
def route_response_with_geofenced_avoidance_areas(fixture_path):
    with open(
        f"{fixture_path}/route-response-with-geofenced-avoidance-areas.json", "r"
    ) as f:
        return json.loads(f.read())


@pytest.fixture
def route_request_with_unavailable_geofenced_avoidance_areas(fixture_path):
    with open(
        f"{fixture_path}/route-request-with-unavailable-geofenced-avoidance-areas.json",
        "r",
    ) as f:
        return json.loads(f.read())


@pytest.fixture
def unroutable_request_with_avoidance_areas(fixture_path):
    with open(
        f"{fixture_path}/unroutable-request-with-avoidance-areas.json",
        "r",
    ) as f:
        return json.loads(f.read())

@pytest.fixture
def list_geofences_response(fixture_path):
    with open(
        f"{fixture_path}/list-geofences-response.json",
        "r",
    ) as f:
        return json.loads(f.read())


def make_request_event(body):
    return {
        "resource": "/route",
        "path": "/route",
        "httpMethod": "POST",
        "headers": {
            "Accept": "*/*",
            "Host": "w1zp1s03ba.execute-api.us-west-2.amazonaws.com",
            "User-Agent": "curl/8.6.0",
        },
        "multiValueHeaders": {
            "Accept": ["*/*"],
            "Host": ["w1zp1s03ba.execute-api.us-west-2.amazonaws.com"],
            "User-Agent": ["curl/8.6.0"],
        },
        "queryStringParameters": None,
        "multiValueQueryStringParameters": None,
        "pathParameters": None,
        "body": json.dumps(body),
        "isBase64Encoded": False,
    }


# Original botocore _make_api_call function
orig = botocore.client.BaseClient._make_api_call


# Mocked botocore _make_api_call function
def mock_make_api_call(list_geofences_response):
    def make_api_call(self, operation_name, kwargs):
        # For example for the Access Analyzer service
        # As you can see the operation_name has the list_analyzers snake_case form but
        # we are using the ListAnalyzers form.
        # Rationale -> https://github.com/boto/botocore/blob/develop/botocore/client.py#L810:L816
        if operation_name == "ListGeofences":
            return list_geofences_response

        # If we don't want to patch the API call
        return orig(self, operation_name, kwargs)

    return make_api_call


def test_with_origin_and_destination(simple_route_request, simple_route_response):
    rsp = handle(make_request_event(simple_route_request))

    assert json.loads(rsp["body"]) == simple_route_response


def test_with_avoidance_areas(
    route_request_with_avoidance_areas, route_response_with_avoidance_areas
):
    rsp = handle(make_request_event(route_request_with_avoidance_areas))

    assert json.loads(rsp["body"]) == route_response_with_avoidance_areas


def test_with_multiple_geometries_in_one_avoidance_area(
    route_request_with_invalid_avoidance_areas,
):
    rsp = handle(make_request_event(route_request_with_invalid_avoidance_areas))

    assert rsp["statusCode"] == 400
    assert (
        json.loads(rsp["body"])["Error"]
        == "Only one of {Circle, Polygon, Arn} may be provided per Area."
    )


def test_with_geofenced_avoidance_areas(
    route_request_with_geofenced_avoidance_areas,
    route_response_with_geofenced_avoidance_areas,
    list_geofences_response,
):
    with patch(
        "botocore.client.BaseClient._make_api_call",
        new=mock_make_api_call(list_geofences_response),
    ):
        rsp = handle(make_request_event(route_request_with_geofenced_avoidance_areas))

    assert json.loads(rsp["body"]) == route_response_with_geofenced_avoidance_areas


def test_with_unavailable_geofenced_avoidance_areas(
    route_request_with_unavailable_geofenced_avoidance_areas, list_geofences_response
):
    with patch(
        "botocore.client.BaseClient._make_api_call",
        new=mock_make_api_call(list_geofences_response),
    ):
        rsp = handle(
            make_request_event(route_request_with_unavailable_geofenced_avoidance_areas)
        )

    assert rsp["statusCode"] == 500
    assert (
        json.loads(rsp["body"])["Error"]
        == f"Unable to fetch geofence ({route_request_with_unavailable_geofenced_avoidance_areas["Avoid"]["Areas"][0]["Area"]["Arn"]})"
    )


def test_unroutable_request(unroutable_request_with_avoidance_areas):
    rsp = handle(make_request_event(unroutable_request_with_avoidance_areas))
    assert rsp["statusCode"] == 404
    assert json.loads(rsp["body"])["Error"] == "No route found."
