# Custom routing for a bring-your-own-map tracking solution

This is a CDK app that deploys a custom routing engine to support a bring-your-own-map tracking solution.

## Prerequisites

* [Node.js](https://nodejs.org/) to build the CDK app.
* [AWS CDK](https://aws.amazon.com/cdk/) to deploy the CDK app: `npm install -g aws-cdk`
* [Docker](https://docker.com/) or [Finch](https://runfinch.com/) to build Docker images for the routing engine.
* [Python](https://python.org/) >= 3.11.x to run the routing engine locally.
* [Poetry](https://python-poetry.org/) to manage Python dependencies locally.

To initialize deployment dependencies, run:

```shell
npm install
```

## Deployment

```shell
export AWS_PROFILE=<profile> # or credentials
export AWS_REGION=<region>
cdk bootstrap # required when deploying to a new region or profile.
cdk deploy
```

## Routing engine

This project includes a routing engine that operates over a limited area while supporting dynamic exclusion areas, either provided as input or as Amazon Location geofences.

[See `routing/README.md`](routing/README.md) for more information on the routing engine.

## Map conversion

This project also includes a conversion tool that converts AutoCAD KML output to GeoJSON suitable for display on a web map (including simplifying and shrinking the output while preserving style attributes).

[See `kml-conversion/README.md`](kml-conversion/README.md) for more information on the map conversion tool.

## Useful commands

* `npm run build`   compile typescript to js
* `npm run watch`   watch for changes and compile
* `npm run test`    perform the jest unit tests
* `npx cdk deploy`  deploy this stack to your default AWS account/region
* `npx cdk diff`    compare deployed stack with current state
* `npx cdk synth`   emits the synthesized CloudFormation template
* `npm run tail`    tails the CloudWatch log stream for the routing Lambda function

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the MIT-0 License. See the LICENSE file.
