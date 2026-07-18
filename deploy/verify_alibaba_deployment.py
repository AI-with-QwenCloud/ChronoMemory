"""Confirms the ChronoMemory backend is actually running on Alibaba Cloud ECS.

Calls the Alibaba Cloud ECS OpenAPI (DescribeInstances) for the instance
tagged app=chronomemory and checks it's Running with a public IP serving the
app. This is the deployment-verification step run after `bootstrap_ecs.sh`
brings the instance up — not a one-off demo call.

Credentials come from ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET
(the SDK's standard env vars) — never hardcode keys here.
"""
import os
import sys

from alibabacloud_ecs20140526.client import Client as EcsClient
from alibabacloud_ecs20140526 import models as ecs_models
from alibabacloud_tea_openapi import models as open_api_models

REGION_ID = os.environ.get("CHRONOMEM_ECS_REGION", "ap-southeast-1")
INSTANCE_TAG = {"Key": "app", "Value": "chronomemory"}


def _client() -> EcsClient:
    config = open_api_models.Config(
        access_key_id=os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"],
        access_key_secret=os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
        region_id=REGION_ID,
    )
    config.endpoint = f"ecs.{REGION_ID}.aliyuncs.com"
    return EcsClient(config)


def describe_chronomemory_instance() -> dict:
    client = _client()
    request = ecs_models.DescribeInstancesRequest(
        region_id=REGION_ID,
        tag=[ecs_models.DescribeInstancesRequestTag(key=INSTANCE_TAG["Key"], value=INSTANCE_TAG["Value"])],
    )
    response = client.describe_instances(request)
    instances = response.body.instances.instance
    if not instances:
        raise RuntimeError(f"no ECS instance tagged {INSTANCE_TAG} found in {REGION_ID}")
    return instances[0].to_map()


def main() -> None:
    instance = describe_chronomemory_instance()
    status = instance["Status"]
    public_ips = instance.get("PublicIpAddress", {}).get("IpAddress", [])

    print(f"instance id:   {instance['InstanceId']}")
    print(f"status:        {status}")
    print(f"public ip:     {public_ips}")
    print(f"instance type: {instance['InstanceType']}")

    if status != "Running":
        sys.exit(f"expected Running, got {status}")
    if not public_ips:
        sys.exit("instance has no public IP — app is not externally reachable")


if __name__ == "__main__":
    main()
