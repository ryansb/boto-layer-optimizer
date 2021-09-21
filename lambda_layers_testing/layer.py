import json

from aws_cdk import RemovalPolicy
from aws_cdk import aws_ssm as ssm
from aws_cdk.aws_lambda import Code, LayerVersion, Runtime, RuntimeFamily
from constructs import Construct

from . import layer_processor


class Boto3Layer(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        layer_name: str,
        boto3_version=None,
        only_services=None,
        pickle_data: bool = False,
        retain_layers: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        if only_services:
            only_services = sorted(only_services)

        layer_dir, version_info = layer_processor.build_botocore_zip(construct_id, only_services=only_services, boto3_version=boto3_version)
        if only_services:
            description = f"Boto3 and botocore stripped to {','.join(only_services)[:100]}. "
        else:
            description = "Boto3 and botocore stripped of docs. "
        if pickle_data:
            layer_processor.pickle_service_json(layer_dir)

        description += ",".join(f"{k}={version_info[k]}" for k in sorted(version_info))
        # f" {json.dumps(version_info, sort_keys=True)}"

        self.layer = LayerVersion(
            self,
            "Boto3Layer",
            # arn:[a-zA-Z0-9-]+:lambda:[a-zA-Z0-9-]+:\d{12}:layer:[a-zA-Z0-9-_]+)|[a-zA-Z0-9-_]+
            layer_version_name=f"{layer_name}_boto3_{boto3_version or 'latest'}".replace(".", "-"),
            code=Code.from_asset(path=str(layer_dir)),
            compatible_runtimes=[
                Runtime.PYTHON_3_8,
                Runtime(
                    "python3.9",
                    RuntimeFamily.PYTHON,
                    supports_inline_code=True,
                ),
            ],
            description=description,
            removal_policy=RemovalPolicy.RETAIN if retain_layers else RemovalPolicy.DESTROY,
        )

        ssm.StringParameter(
            self,
            "VersionIdentifier",
            description=description,
            string_value=self.layer.layer_version_arn,
            parameter_name=f"/layers/python3.8/boto3/{boto3_version or 'latest'}/{layer_name}",
        )
