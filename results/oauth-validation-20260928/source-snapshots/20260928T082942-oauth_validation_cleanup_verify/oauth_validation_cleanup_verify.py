"""Read back every resource type created by the focused OAuth run."""
import json
from pathlib import Path
import time
from botocore.exceptions import ClientError
from cleanup_tests import missing


def run(s):
    checks = []
    c = s.control
    for item in s.state["resources"]:
        kind, ident = item["kind"], item["id"]
        getters = {
            "role": lambda: s.client("iam").get_role(RoleName=ident),
            "gateway": lambda: c.get_gateway(gatewayIdentifier=ident),
            "target": lambda: c.get_gateway_target(gatewayIdentifier=item["gateway"], targetId=ident),
            "oauth-provider": lambda: c.get_oauth2_credential_provider(name=ident),
            "workload": lambda: c.get_workload_identity(name=ident),
            "secret": lambda: s.client("secretsmanager").describe_secret(SecretId=ident),
        }
        assert kind in getters, kind
        row = {"kind": kind, "id": ident}
        try:
            found = getters[kind]()
            scheduled = kind == "secret" and bool(found.get("DeletedDate"))
            row.update(ok=scheduled or found.get("status") == "DELETED",
                       status="ScheduledDeletion" if scheduled else found.get("status", "EXISTS"))
            if scheduled:
                row["deletionDate"] = str(found["DeletedDate"])
        except ClientError as error:
            row.update(ok=missing(error), status="ABSENT" if missing(error) else error.response["Error"]["Code"],
                       requestId=error.response["ResponseMetadata"]["RequestId"])
        checks.append(row)
    for pid in s.state.get("local_processes", []):
        path = Path(f"/proc/{pid}/stat")
        for _ in range(20):
            if not path.exists() or path.read_text().split(") ")[1].startswith("Z"):
                break
            time.sleep(0.2)
        stopped = not path.exists() or path.read_text().split(") ")[1].startswith("Z")
        checks.append({"kind": "local-process", "pid": pid, "ok": stopped})
    for suffix in ("private-key.pem", "secrets.json"):
        path = s.state_path.parent / f"{s.region}-{suffix}"
        checks.append({"kind": "local-secret", "file": path.name, "ok": not path.exists()})
    result = {"status": "PASS" if all(row["ok"] for row in checks) else "FAIL", "checks": checks}
    (s.state_path.parent / f"{s.region}-cleanup-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    s.record("cleanup.oauth.read_only_verification", result["status"], checks)
    assert result["status"] == "PASS", result
    return result
