"""Read-only verification of this run's resource inventory and tagged EC2 volumes."""
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent
RESULTS = Path(os.environ.get("VERIFY_RESULTS_DIR", str(ROOT / "results")))
REGIONS = ("cn-north-1", "cn-northwest-1")
MISSING = {"ResourceNotFoundException", "ResourceNotFound", "NotFoundException", "NoSuchEntity",
           "NoSuchBucket", "404", "InvalidGroup.NotFound", "FileSystemNotFound"}


def verify(region):
    state = json.loads((RESULTS / f"{region}-state.json").read_text())
    session = boto3.Session(profile_name="china", region_name=region)
    config = Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2})
    clients = {}

    def client(service):
        if service not in clients:
            clients[service] = session.client(service, config=config)
        return clients[service]

    control = client("bedrock-agentcore-control")
    checks = []
    for resource in state["resources"]:
        kind, ident = resource["kind"], resource["id"]
        getters = {
            "gateway": lambda: control.get_gateway(gatewayIdentifier=ident),
            "browser": lambda: control.get_browser(browserId=ident),
            "profile": lambda: control.get_browser_profile(profileId=ident),
            "runtime": lambda: control.get_agent_runtime(agentRuntimeId=ident),
            "lambda": lambda: client("lambda").get_function_configuration(FunctionName=ident),
            "api": lambda: client("apigateway").get_rest_api(restApiId=ident),
            "efs": lambda: client("efs").describe_file_systems(FileSystemId=ident),
            "sg": lambda: client("ec2").describe_security_groups(GroupIds=[ident]),
            "role": lambda: client("iam").get_role(RoleName=ident),
            "bucket": lambda: client("s3").head_bucket(Bucket=ident),
            "secret": lambda: client("secretsmanager").describe_secret(SecretId=ident),
            "kms": lambda: client("kms").describe_key(KeyId=ident),
        }
        if kind not in getters:
            continue
        check = {"kind": kind, "id": ident}
        try:
            response = getters[kind]()
            if kind == "kms":
                metadata = response["KeyMetadata"]
                check.update(status=metadata["KeyState"], deletionDate=str(metadata.get("DeletionDate")),
                             arn=metadata["Arn"])
                check["ok"] = metadata["KeyState"] == "PendingDeletion"
            elif kind == "secret" and response.get("DeletedDate"):
                check.update(status="ScheduledDeletion", deletionDate=str(response["DeletedDate"]), ok=True)
            else:
                check.update(status=response.get("status", "EXISTS"))
                check["ok"] = check["status"] == "DELETED"
        except ClientError as error:
            code = error.response["Error"]["Code"]
            check.update(status="ABSENT" if code in MISSING else code, ok=code in MISSING)
        checks.append(check)
    name = state["run"] + ("-bj" if region == REGIONS[0] else "-nx")
    ec2 = client("ec2")
    volumes = [v["VolumeId"] for page in ec2.get_paginator("describe_volumes").paginate(
        Filters=[{"Name": "tag:Purpose", "Values": [name]}]) for v in page["Volumes"]]
    checks.append({"kind": "tagged-volumes", "status": "ABSENT" if not volumes else "EXISTS",
                   "ids": volumes, "ok": not volumes})
    instances = [i for page in ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "tag:Purpose", "Values": [name]}])
        for reservation in page["Reservations"] for i in reservation["Instances"]]
    checks.append({"kind": "tagged-instances", "ok": all(i["State"]["Name"] == "terminated" for i in instances),
                   "instances": [{"id": i["InstanceId"], "status": i["State"]["Name"]} for i in instances]})
    enis = (ec2.describe_network_interfaces(Filters=[{"Name": "group-id", "Values": [state["sg"]]}])["NetworkInterfaces"]
            if state.get("sg") else [])
    checks.append({"kind": "security-group-interfaces", "ok": not enis,
                   "interfaces": [{k: e.get(k) for k in ["NetworkInterfaceId", "Status", "InterfaceType", "Attachment"]}
                                  for e in enis]})
    row = {"time": dt.datetime.now(dt.timezone.utc).isoformat(), "region": region,
           "feature": "cleanup.read_only_verification",
           "status": "PASS" if all(c["ok"] for c in checks) else "FAIL", "evidence": checks}
    (RESULTS / f"{region}-cleanup-verification.json").write_text(json.dumps(row, indent=2))
    with (RESULTS / f"{region}-results.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps({"region": region, "status": row["status"],
                      "remaining": [c for c in checks if not c["ok"] or c.get("status") in
                                    ("PendingDeletion", "ScheduledDeletion")]}), flush=True)


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(verify, REGIONS))
