// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from "aws-cdk-lib";
import { CfnOutput, Duration } from "aws-cdk-lib";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import { PolicyStatement } from "aws-cdk-lib/aws-iam";
import {
  Architecture,
  DockerImageCode,
  DockerImageFunction,
} from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";

function generateRandomString(length: number) {
  const characters =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let result = "";
  const charactersLength = characters.length;

  for (let i = 0; i < length; i++) {
    result += characters.charAt(Math.floor(Math.random() * charactersLength));
  }

  return result;
}

export class CdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // create a Docker-based Lambda function using the Python project in routing/
    const dockerRoutingLambda = new DockerImageFunction(this, "RoutingLambda", {
      // architecture: Architecture.X86_64,
      architecture: Architecture.ARM_64,
      code: DockerImageCode.fromImageAsset("./routing/"),
      functionName: "RoutingApi",
      memorySize: 1024,
      timeout: Duration.seconds(30),
      initialPolicy: [
        new PolicyStatement({
          actions: ["geo:ListGeofences"],
          resources: ["*"],
        }),
      ],
    });

    // register an API Gateway resource backed by the Lambda function
    // TODO configure auth
    const api = new apigateway.LambdaRestApi(this, "RoutingApi", {
      handler: dockerRoutingLambda,
      proxy: false,
      defaultCorsPreflightOptions: {
        allowHeaders: [
          "Content-Type",
          "X-Amz-Date",
          "Authorization",
          "X-Api-Key",
        ],
        allowMethods: ["POST"],
        allowCredentials: true,
        allowOrigins: ["*"],
      },
      apiKeySourceType: apigateway.ApiKeySourceType.HEADER,
    });

    const secret = generateRandomString(20);

    // Create an API key
    const apiKey = api.addApiKey("RoutingApiKey", {
      value: secret,
    });

    // Create a usage plan
    const plan = api.addUsagePlan("RoutingUsagePlan", {
      name: "RoutingUsagePlan",
    });

    plan.addApiKey(apiKey);

    // Associate the API's stage with the usage plan
    plan.addApiStage({
      stage: api.deploymentStage,
    });

    // register POST /route
    const routeResource = api.root.addResource("route");
    routeResource.addMethod(
      "POST",
      new apigateway.LambdaIntegration(dockerRoutingLambda),
      {
        apiKeyRequired: true,
      }
    );

    // output the Lambda function name (to facilitate manual invocation)
    new CfnOutput(this, "RoutingLambdaFunctionName", {
      value: dockerRoutingLambda.functionName,
      description: "Routing Lambda function ARN",
    });

    // output the Lambda function's log group (to facilitate log tailing)
    new CfnOutput(this, "RoutingLambdaLogGroup", {
      value: dockerRoutingLambda.logGroup.logGroupArn,
      description: "Routing Lambda log group ARN",
    });

    new CfnOutput(this, "RoutingApiKey", {
      value: secret,
      description: "API key",
    });
  }
}
