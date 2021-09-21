#!/usr/bin/env python3
import os

import aws_cdk as cdk
from aws_cdk import Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk.aws_lambda import Code, Function, LayerVersion, Runtime, RuntimeFamily
from aws_cdk.aws_logs import LogGroup, RetentionDays
from constructs import Construct

from lambda_layers_testing import layer

app_code = Code.from_inline(
    """
import json
import boto3

sts = boto3.client('sts')

def handler(event, context):
    return {
        'body': json.dumps(sts.get_caller_identity())
    }
""".strip()
)


class PublishLayers(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        layer.Boto3Layer(
            self,
            "AllServices",
            layer_name="all-services",
        )
        layer.Boto3Layer(
            self,
            "AllServicesPickled",
            layer_name="all-pickled",
            pickle_data=True,
        )
        layer.Boto3Layer(
            self,
            "CognitoHook",
            boto3_version="1.18.43",
            pickle_data=True,
            layer_name="cognito-hooks",
            only_services=("dynamodb", "cognito-identity", "cognito-idp"),
        )
        layer.Boto3Layer(
            self,
            "Serverless",
            layer_name="serverless-basics",
            only_services=(
                "dynamodb",
                "iam",
                "s3",
                "sqs",
                "sts",
                "sns",
            ),
        )
        layer.Boto3Layer(
            self,
            "ServerlessKitchenSink",
            layer_name="serverless-sink",
            pickle_data=True,
            only_services=(
                "apigateway",
                "apigatewaymanagementapi",
                "apigatewayv2",
                "athena",
                "ce",
                "cloudformation",
                "cloudtrail",
                "cloudwatch",
                "cognito-identity",
                "cognito-idp",
                "config",
                "dynamodb",
                "dynamodbstreams",
                "ec2",
                "events",
                "firehose",
                "glue",
                "iam",
                "kinesis",
                "kms",
                "lambda",
                "s3",
                "sns",
                "sqs",
                "ssm",
                "sts",
            ),
        )
        layer.Boto3Layer(
            self,
            "SfResume",
            layer_name="sf-resume",
            only_services=(
                "stepfunctions",
                "sqs",
            ),
        )


class Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        role = iam.Role(
            self,
            "Role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies=[
                iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=["*"],
                        )
                    ]
                )
            ],
        )
        sls_layer = LayerVersion.from_layer_version_arn(
            self,
            "ServerlessLayer",
            ssm.StringParameter.from_string_parameter_name(
                self, "ImportedVersionArn", "/layers/python3.8/boto3/latest/serverless-basics"
            ).string_value,
        )

        for mem_size in (128, 256):
            f = Function(
                self,
                f"SlsFunc{mem_size}",
                code=app_code,
                handler="index.handler",
                layers=[sls_layer],
                memory_size=mem_size,
                role=role,
                timeout=Duration.seconds(15),
                runtime=Runtime(
                    "python3.9",
                    family=RuntimeFamily.PYTHON,
                    supports_inline_code=True,
                ),
            )
            LogGroup(
                self,
                f"Group{mem_size}",
                log_group_name=f"/aws/lambda/{f.function_name}",
                retention=RetentionDays.TWO_WEEKS,
            )


app = cdk.App()

PublishLayers(app, "Boto3LayerStack")

Stack(app, "LambdaLayersTestingStack")

app.synth()
