"""Retry only the test security groups while AWS releases AgentCore ENIs.

Run after suite.py cleanup completes. Does not detach AWS-owned interfaces.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent
RESULTS = Path(os.environ.get("DEFERRED_RESULTS_DIR", str(ROOT / "results")))
STATUS = RESULTS / "deferred-cleanup.json"
REGIONS = ("cn-north-1", "cn-northwest-1")


def main():
    started = dt.datetime.now(dt.timezone.utc)
    deadline = time.monotonic() + 8.5 * 3600
    targets = []
    clients = {}
    for region in REGIONS:
        state = json.loads((RESULTS / f"{region}-state.json").read_text())
        clients[region] = boto3.Session(profile_name="china", region_name=region).client(
            "ec2", config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2}))
        name = state["run"] + ("-bj" if region == REGIONS[0] else "-nx")
        targets.extend({"region": region, "id": r["id"], "purposeTag": name, "status": "PENDING"}
                       for r in state["resources"] if r["kind"] == "sg" and not r.get("deleted"))

    def save(status, **extra):
        STATUS.write_text(json.dumps({
            "status": status, "pid": os.getpid(), "profile": "china",
            "startedAt": started.isoformat(),
            "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "deadline": (started + dt.timedelta(hours=8.5)).isoformat(),
            "targets": targets, **extra,
        }, indent=2))

    save("WAITING_FOR_AWS_ENI_RELEASE")
    try:
        while True:
            for target in targets:
                if target["status"] == "DELETED":
                    continue
                ec2 = clients[target["region"]]
                try:
                    group = ec2.describe_security_groups(GroupIds=[target["id"]])["SecurityGroups"][0]
                    tags = {t["Key"]: t["Value"] for t in group.get("Tags", [])}
                    if tags.get("Purpose") != target["purposeTag"]:
                        raise RuntimeError("Test security group ownership tag changed: " + target["id"])
                    ec2.delete_security_group(GroupId=target["id"])
                    target["status"] = "DELETED"
                except ClientError as error:
                    code = error.response["Error"]["Code"]
                    if code == "InvalidGroup.NotFound":
                        target["status"] = "DELETED"
                    elif code == "DependencyViolation":
                        target["status"] = "WAITING_FOR_AWS_ENI_RELEASE"
                    else:
                        raise
            save("WAITING_FOR_AWS_ENI_RELEASE")
            if all(t["status"] == "DELETED" for t in targets):
                break
            if time.monotonic() >= deadline:
                save("TIMED_OUT", nextStep=".venv/bin/python suite.py cleanup --profile china")
                return
            time.sleep(60)
        save("REFRESHING_VERIFICATION")
        env = {**os.environ, "RETEST_RESULTS_DIR": str(RESULTS), "VERIFY_RESULTS_DIR": str(RESULTS)}
        command = ([sys.executable, str(ROOT / "suite.py"), "cleanup", "--profile", "china"]
                   if RESULTS == ROOT / "results" else [sys.executable, str(ROOT / "retest.py"), "cleanup_tests"])
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        subprocess.run([sys.executable, str(ROOT / "verify_cleanup.py")], cwd=ROOT, env=env, check=True)
        verified = all(json.loads((RESULTS / f"{r}-cleanup-verification.json").read_text())["status"] == "PASS"
                       for r in REGIONS)
        save("COMPLETE" if verified else "VERIFICATION_FAILED")
        if RESULTS == ROOT / "results":
            subprocess.run([sys.executable, str(ROOT / "export_report.py")], cwd=ROOT, check=True)
    except Exception as error:
        save("ERROR", errorType=type(error).__name__, message=str(error))
        raise


if __name__ == "__main__":
    main()
