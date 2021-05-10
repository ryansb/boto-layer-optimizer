from aws_cdk import Fn, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk.aws_lambda import Code, Function, LayerVersion, Runtime
from constructs import Construct

from . import layer

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
            "AllServicesLayer",
            layer_name="all",
        )
        layer.Boto3Layer(
            self,
            "CognitoHookLayer",
            boto3_version="1.17.55",
            layer_name="cognito_hook",
            only_services=("dynamodb", "cognito"),
        )
        layer.Boto3Layer(
            self,
            "ServerlessLayer",
            layer_name="serverless",
            only_services=(
                "dynamodb",
                "iam",
                "s3",
                "sqs",
                "sns",
            ),
        )


class Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        role = iam.Role(
            self,
            "Role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")],
        )
        sls_layer = LayerVersion.from_layer_version_arn(
            self,
            "ServerlessLayer",
            ssm.StringParameter.from_string_parameter_name(
                self, "ImportedVersionArn", "/layers/python3.8/boto3/latest/serverless"
            ).string_value,
        )

        for mem_size in (128, 256):
            Function(
                self,
                f"Hello{mem_size}",
                code=app_code,
                handler="index.handler",
                layers=[sls_layer],
                memory_size=mem_size,
                role=role,
                runtime=Runtime.PYTHON_3_8,
            )
