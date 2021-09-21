import sys

sys.path.append(sys.argv[1])

import boto3

for _ in range(20):
    sess = boto3.Session(region_name="us-west-2")
    sess.client("ec2")
    sess.client("firehose")
    sess.client("iam")
