"""Delete only resources recorded as created by this test run."""
import concurrent.futures
import json
import os
import time
from botocore.exceptions import ClientError
from suite import RESULTS


def missing(e):
    return isinstance(e, ClientError) and e.response["Error"]["Code"] in [
        "ResourceNotFoundException", "ResourceNotFound", "NotFoundException", "NoSuchEntity", "NoSuchBucket",
        "InvalidInstanceID.NotFound", "InvalidNetworkInterfaceID.NotFound", "InvalidGroup.NotFound",
        "FileSystemNotFound", "MountTargetNotFound", "AccessPointNotFound", "NoSuchKey"]


def gone(fn, timeout=300):
    end = time.monotonic() + timeout
    while True:
        try:
            r = fn()
            if r.get("status") == "DELETED":
                return
        except Exception as e:
            if missing(e):
                return
            raise
        if time.monotonic() > end:
            raise TimeoutError("Resource still exists after deletion")
        time.sleep(3)


def run(s):
    sessions = list(s.state.get("sessions", []))
    initial = RESULTS / f"{s.region}-initial-session.json"
    if initial.exists():
        r = json.loads(initial.read_text())
        sessions.append({"browser": r["browserIdentifier"], "id": r["sessionId"]})
    sessions = list({(x["browser"], x["id"]): x for x in sessions}.values())
    def stop(x):
        args = {"browserIdentifier": x["browser"], "sessionId": x["id"]}
        try:
            current = s.runtime.get_browser_session(**args)
            if current["status"] not in ["TERMINATED", "TIMED_OUT", "STOPPED"]:
                s.runtime.stop_browser_session(**args)
                current = s.runtime.get_browser_session(**args)
            assert current["status"] in ["TERMINATED", "TIMED_OUT", "STOPPED"], current["status"]
            return {"sessionId": x["id"], "status": current["status"]}
        except Exception as e:
            if missing(e):
                return {"sessionId": x["id"], "status": "absent"}
            return {"sessionId": x["id"], "error": str(e)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        stopped = list(ex.map(stop, sessions))
    s.record("cleanup.browser_sessions", "FAIL" if any("error" in x for x in stopped) else "PASS", stopped)
    for sid in s.state.get("runtime_sessions", []):
        try:
            s.runtime.stop_runtime_session(agentRuntimeArn=s.state["runtime_arn"], runtimeSessionId=sid)
        except Exception as e:
            if not missing(e):
                s.record("cleanup.runtime_session", "INFO", {"sessionId": sid, "message": str(e)})
    # Save automatically managed credential secret ARNs for cleanup verification.
    for r in list(s.state["resources"]):
        if r["kind"] in ["api-key-provider", "oauth-provider"] and not r.get("deleted"):
            try:
                p = (s.control.get_api_key_credential_provider(name=r["id"]) if r["kind"] == "api-key-provider"
                     else s.control.get_oauth2_credential_provider(name=r["id"]))
                secret = p.get("apiKeySecretArn", p.get("clientSecretArn", {})).get("secretArn")
                if secret and not any(x["kind"] == "secret" and x["id"] == secret for x in s.state["resources"]):
                    s.resource("secret", secret, serviceManaged=True)
            except Exception as e:
                if not missing(e):
                    raise
    # Gateway-generated workload identities are owned by these gateways.
    for r in list(s.state["resources"]):
        if r["kind"] in ["gateway", "runtime"] and not r.get("deleted"):
            try:
                gw = (s.control.get_gateway(gatewayIdentifier=r["id"]) if r["kind"] == "gateway"
                      else s.control.get_agent_runtime(agentRuntimeId=r["id"]))
                wi = gw.get("workloadIdentityDetails", {}).get("workloadIdentityArn")
                if wi and not any(x["kind"] == "workload" and x["id"] == wi.split("/")[-1] for x in s.state["resources"]):
                    s.resource("workload", wi.split("/")[-1], arn=wi)
            except Exception as e:
                if not missing(e):
                    raise
    order = ["delivery", "delivery-source", "delivery-destination", "rate-limit", "target", "gateway",
             "browser", "profile", "runtime", "workload", "api-key-provider", "oauth-provider", "api", "lambda",
             "instance", "efs-ap", "efs-mount", "efs", "eni", "sg", "secret", "kms", "bucket", "log-group", "role"]
    for kind in order:
        resources = [x for x in s.state["resources"] if x["kind"] == kind and not x.get("deleted") and not x.get("scheduledDeletion")]
        if not resources:
            continue
        def remove(r):
            try:
                extra = delete(s, r)
                return r, True, extra
            except Exception as e:
                if missing(e):
                    return r, True, {"alreadyAbsent": True}
                return r, False, {"type": type(e).__name__, "message": str(e)}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(remove, resources))
        for r, ok, extra in results:
            if ok:
                if kind == "kms" or extra.get("scheduledDeletion"):
                    r["scheduledDeletion"] = extra
                else:
                    r["deleted"] = True
            r["cleanupResult"] = extra
        s.save()
        s.record("cleanup." + kind, "PASS" if all(x[1] for x in results) else "FAIL",
                 [{"id": x[0]["id"], "deleted": x[1], "detail": x[2]} for x in results])
    # Remove service-created log groups that belong to this run.
    groups = {"/aws/lambda/" + s.name}
    if s.state.get("runtime_id"):
        prefix = "/aws/bedrock-agentcore/runtimes/" + s.state["runtime_id"]
        groups.update(x["logGroupName"] for x in s.client("logs").describe_log_groups(logGroupNamePrefix=prefix)["logGroups"])
    for group in groups:
        try:
            s.client("logs").delete_log_group(logGroupName=group)
        except Exception as e:
            if not missing(e):
                s.record("cleanup.automatic_logs", "FAIL", {"group": group, "message": str(e)})
    remaining = [x for x in s.state["resources"] if not x.get("deleted")]
    s.record("cleanup.inventory", "PASS" if all(x.get("scheduledDeletion") for x in remaining) else "FAIL", remaining)
    return {"remaining": remaining}


def delete(s, r):
    kind, ident = r["kind"], r["id"]
    c = s.control
    if kind == "delivery":
        s.client("logs").delete_delivery(id=ident)
    elif kind == "delivery-source":
        s.client("logs").delete_delivery_source(name=ident)
    elif kind == "delivery-destination":
        s.client("logs").delete_delivery_destination(name=ident)
    elif kind == "rate-limit":
        c.delete_gateway_rate_limit(gatewayIdentifier=r["gateway"], rateLimitId=ident)
    elif kind == "target":
        c.delete_gateway_target(gatewayIdentifier=r["gateway"], targetId=ident)
        gone(lambda: c.get_gateway_target(gatewayIdentifier=r["gateway"], targetId=ident))
    elif kind == "gateway":
        c.delete_gateway(gatewayIdentifier=ident)
        gone(lambda: c.get_gateway(gatewayIdentifier=ident))
    elif kind == "browser":
        c.delete_browser(browserId=ident)
        gone(lambda: c.get_browser(browserId=ident))
    elif kind == "profile":
        c.delete_browser_profile(profileId=ident)
        gone(lambda: c.get_browser_profile(profileId=ident))
    elif kind == "runtime":
        c.delete_agent_runtime(agentRuntimeId=ident)
        gone(lambda: c.get_agent_runtime(agentRuntimeId=ident), timeout=600)
    elif kind == "workload":
        c.delete_workload_identity(name=ident)
    elif kind == "api-key-provider":
        c.delete_api_key_credential_provider(name=ident)
    elif kind == "oauth-provider":
        c.delete_oauth2_credential_provider(name=ident)
    elif kind == "api":
        s.client("apigateway").delete_rest_api(restApiId=ident)
    elif kind == "lambda":
        s.client("lambda").delete_function(FunctionName=ident)
    elif kind == "instance":
        ec2 = s.client("ec2")
        ec2.terminate_instances(InstanceIds=[ident])
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[ident], WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    elif kind == "efs-ap":
        s.client("efs").delete_access_point(AccessPointId=ident)
    elif kind == "efs-mount":
        s.client("efs").delete_mount_target(MountTargetId=ident)
        gone(lambda: s.client("efs").describe_mount_targets(MountTargetId=ident))
    elif kind == "efs":
        s.client("efs").delete_file_system(FileSystemId=ident)
        gone(lambda: s.client("efs").describe_file_systems(FileSystemId=ident))
    elif kind == "eni":
        s.client("ec2").delete_network_interface(NetworkInterfaceId=ident)
    elif kind == "sg":
        ec2 = s.client("ec2")
        end = time.monotonic() + int(os.environ.get("CLEANUP_SG_WAIT_SECONDS", "600"))
        while True:
            try:
                ec2.delete_security_group(GroupId=ident)
                break
            except ClientError as e:
                if e.response["Error"]["Code"] != "DependencyViolation" or time.monotonic() >= end:
                    raise
                # Any interface in this unique test security group belongs to this test.
                for eni in ec2.describe_network_interfaces(Filters=[{"Name": "group-id", "Values": [ident]}])["NetworkInterfaces"]:
                    if eni["Status"] == "available" and not eni.get("RequesterManaged"):
                        ec2.delete_network_interface(NetworkInterfaceId=eni["NetworkInterfaceId"])
                time.sleep(5)
    elif kind == "secret":
        try:
            s.client("secretsmanager").delete_secret(SecretId=ident, ForceDeleteWithoutRecovery=True)
        except ClientError as e:
            if r.get("serviceManaged") and "owned by another service" in str(e):
                info = s.client("secretsmanager").describe_secret(SecretId=ident)
                assert info.get("DeletedDate"), "Service-managed test secret has not been scheduled for deletion"
                return {"serviceManaged": True, "scheduledDeletion": str(info["DeletedDate"])}
            raise
    elif kind == "kms":
        response = s.client("kms").schedule_key_deletion(KeyId=ident, PendingWindowInDays=7)
        return {"keyState": response["KeyState"], "deletionDate": str(response["DeletionDate"])}
    elif kind == "bucket":
        s3 = s.client("s3")
        uploads = s3.list_multipart_uploads(Bucket=ident).get("Uploads", [])
        for upload in uploads:
            s3.abort_multipart_upload(Bucket=ident, Key=upload["Key"], UploadId=upload["UploadId"])
        for page in s3.get_paginator("list_object_versions").paginate(Bucket=ident):
            objects = [{"Key": x["Key"], "VersionId": x["VersionId"]} for x in page.get("Versions", []) + page.get("DeleteMarkers", [])]
            if objects:
                response = s3.delete_objects(Bucket=ident, Delete={"Objects": objects, "Quiet": True})
                assert not response.get("Errors"), response.get("Errors")
        s3.delete_bucket(Bucket=ident)
    elif kind == "log-group":
        s.client("logs").delete_log_group(logGroupName=ident)
    elif kind == "role":
        iam = s.client("iam")
        for name in iam.list_role_policies(RoleName=ident)["PolicyNames"]:
            iam.delete_role_policy(RoleName=ident, PolicyName=name)
        for policy in iam.list_attached_role_policies(RoleName=ident)["AttachedPolicies"]:
            iam.detach_role_policy(RoleName=ident, PolicyArn=policy["PolicyArn"])
        iam.delete_role(RoleName=ident)
    return {"deleted": True}
