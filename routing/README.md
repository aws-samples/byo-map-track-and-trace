# Custom Routing API

This is a custom routing engine for use with route graphs.

## Prerequisites

- [Docker](https://docker.com/) or [Finch](https://runfinch.com/) to build Docker images for the routing engine.
- [Python](https://python.org/) >= 3.11.x to run the routing engine locally.
- [Poetry](https://python-poetry.org/) to manage Python dependencies locally. You may need to install `wheel` using `pip` for binary dependencies to install correctly.

To install dependencies, run:

```shell
poetry install
```

## Graph preparation

The routing engine operates on a NetworkX (OSMnx) graph produced by a GeoJSON file. To prepare the graph as GML, run:

```shell
poetry run prepare data/graph.gml < path/to/network.json
```

## Environment variables

- `GRAPH` -- path to a prepared graph file. Defaults to `data/graph.gml`.

## Basic requests

To make requests to the API, `POST` JSON request bodies to an API Gateway endpoint similar to `https://w1zp1s03ba.execute-api.us-west-2.amazonaws.com/prod/route`. The API Gateway hostname (`CdkStaack.RoutingApiEndpoint<something>`) will be output when deploying the CDK stack along with an API key that can be used to make requests (`CdkStack.RoutingApiKey`). Provide the API key by setting `x-api-key: <API key>` as an HTTP header in the `POST` request.

Basic routing requests look like the following and return GeoJSON FeatureCollections containing LineStrings.

```json
{
  "Origin": [-6.893, 37.1795],
  "Destination": [-6.889, 37.1782]
}
```

## Areas to avoid

Routing requests that include areas to avoid look like the following. There is currently no limit to the number of areas that can be provided, although the route graph is updated at runtime. Areas to avoid may be `Polygon`s (in which case the value matches a GeoJSON Polygon's `coordinates`) or `Circle`s.

```json
{
  "Origin": [-6.893, 37.1795],
  "Destination": [-6.889, 37.1782],
  "Avoid": {
    "Areas": [
      {
        "Area": {
          "Polygon": [
            [
              [-6.8924842568777365, 37.17886318897119],
              [-6.892600504618201, 37.17849711569747],
              [-6.8919860522785825, 37.17855445259218],
              [-6.8924842568777365, 37.17886318897119]
            ]
          ]
        }
      },
      {
        "Area": {
          "Circle": {
            "Center": [-6.89187, 37.17829],
            "Radius": 10
          }
        }
      }
    ]
  }
}
```

## Ancillary functionality

### External geofences as areas to avoid

You can reference Amazon Location geofences by ARN and use them as areas to avoid provided that the Lambda function is either deployed in the same account as the the geofence collection or has been configured (using environment variables) to make calls to the geofencing API **as** a different account (cross-account access will not work).

API requests making use of this functionality look like the following.

```json
{
  "Origin": [-6.893, 37.1795],
  "Destination": [-6.889, 37.1782],
  "Avoid": {
    "Areas": [
      {
        "Area": {
          "Arn": "arn:aws:geo:us-west-2::geofence-collection/MyGeofenceCollection#MyArea"
        }
      },
      {
        "Area": {
          "Arn": "arn:aws:geo:us-west-2::geofence-collection/MyGeofenceCollection#MyCircle"
        }
      }
    ]
  }
}
```

#### Create geofences in Amazon Location

To use this functionality, you must first create a geofence collection in Amazon Location and then create geofences within that collection.

Create a geofence collection:

```shell
aws location create-geofence-collection --collection-name MyGeofenceCollection
```

Create a polygonal geofence:

```shell
aws location put-geofence \
  --collection-name MyGeofenceCollection \
  --geofence-id MyArea \
  --geometry file://./resources/MyArea.json
```

Create a a circular geofence:

```shell
aws location put-geofence \
  --collection-name MyGeofenceCollection \
  --geofence-id MyCircle \
  --geometry file://./resources/MyCircle.json
```

## Testing

This project uses [pytest](https://docs.pytest.org/) for testing. To run the tests, use `poetry run pytest`.

## Security

See [../CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the MIT-0 License. See the LICENSE file.
