#!/usr/bin/env python3
import os

import aws_cdk as cdk

from lambda_layers_testing.sample_stack import PublishLayers, Stack

app = cdk.App()

PublishLayers(app, "Boto3LayerStack")

Stack(
    app,
    "LambdaLayersTestingStack",
    env=cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION")),
    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */
    # env=cdk.Environment(account='123456789012', region='us-east-1'),
    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
)

app.synth()
