import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from invoke import task

from lambda_layers_testing.layer_processor import (
    build_botocore_zip,
    pickle_service_json,
    rewrite_loaders_for_caching,
    rewrite_loaders_for_pickling,
)

PY_VER = f"python{sys.version_info.major}.{sys.version_info.minor}"


@task
def clean(ctx):
    try:
        shutil.rmtree("./cdk.out")
    except FileNotFoundError:
        pass


@task
def all_services_zipped(ctx):
    build_botocore_zip("all-services")


@task
def sls_services_zipped(ctx):
    build_botocore_zip("stripped", only_services=["iam", "s3", "dynamodb", "sts", "sqs", "sns"])


@task
def all_services_pickled(ctx):
    all_services, _ = build_botocore_zip("all-services")
    pickle_service_json(all_services)


@task
def sls_services_pickled(ctx):
    stripped, _ = build_botocore_zip(
        "stripped",
        only_services=[
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
        ],
    )
    pickle_service_json(stripped)


@task(pre=[clean, all_services_pickled, sls_services_pickled])
def benchmark_everything(ctx):
    durations = []
    (Path(__file__).parent / "profiles").mkdir(exist_ok=True)
    for d in (
        "all-services",
        "all-services-dedented",
        "all-services-dedented-docless",
        "all-services-orig",
        "all-services-pickles",
        "stripped-pickles",
        "stripped",
    ):

        mod_path = str((Path(__file__).parent / f"cdk.out/layers/{d}/python/lib/{PY_VER}/site-packages/").resolve())
        args = [
            "sudo",
            os.path.expanduser("~/Code/py-spy/target/release/py-spy"),
            "record",
            "--rate",
            "500",
            "-f",
            "speedscope",
            "-o",
            f"profiles/{d}-out.json",
            "--",
            "/usr/local/bin/python3.9",
            "perf_dummy.py",
            mod_path,
        ]
        print(" ".join(args))
        now = time.time()
        subprocess.check_call(args)
        args = [
            "sudo",
            os.path.expanduser("~/Code/py-spy/target/release/py-spy"),
            "record",
            "--rate",
            "500",
            "-o",
            f"profiles/{d}-out.svg",
            "--",
            "/usr/local/bin/python3.9",
            "perf_dummy.py",
            mod_path,
        ]
        print(" ".join(args))
        now = time.time()
        subprocess.check_call(args)
        durations.append(f"{d} ran in {1000*(time.time() - now):.2f}ms")

    for d in durations:
        print(d)


@task
def reparse_loaders(ctx):
    with open("cdk.out/layers/all-services-orig/python/lib/python3.8/site-packages/botocore/loaders.py") as f:
        out = rewrite_loaders_for_pickling(f.read())
        out = rewrite_loaders_for_caching(out)
    with open("cdk.out/progress.py", "w") as f:
        f.write(out)
