import json
import socket
import uuid
from botocore.exceptions import ClientError
from browser_tests import start, stop
from gateway_tests import TOOLS, call


def run(s):
    c = s.control
    gid = s.state["gateway"]["gatewayId"]
    def gateway_pagination():
        page = c.list_gateway_targets(gatewayIdentifier=gid, maxResults=1)
        ids = [x["targetId"] for x in page["items"]]
        pages = 1
        while page.get("nextToken"):
            page = c.list_gateway_targets(gatewayIdentifier=gid, maxResults=1, nextToken=page["nextToken"])
            ids.extend(x["targetId"] for x in page["items"])
            pages += 1
        assert len(set(ids)) == len(ids) and pages > 1, ids
        return {"pages": pages, "uniqueTargets": len(ids)}
    s.test("gateway.targets.pagination", gateway_pagination)
    def update_target():
        tid = next(x["id"] for x in s.state["resources"] if x["kind"] == "target" and x.get("name") == "lambda-inline")
        r = c.update_gateway_target(gatewayIdentifier=gid, targetId=tid, name="lambda-inline", description="Updated active target",
            targetConfiguration={"mcp": {"lambda": {"lambdaArn": s.state["lambda_arn"], "toolSchema": {"inlinePayload": TOOLS}}}},
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}])
        s.wait(lambda: c.get_gateway_target(gatewayIdentifier=gid, targetId=tid))
        return call(s, "lambda-inline___echo", {"text": "update-ok"}, "update-ok")
    s.test("gateway.targets.update_active_and_invoke", update_target)
    def target_idempotency():
        params = {"gatewayIdentifier": gid, "name": "idempotent", "clientToken": str(uuid.uuid4()),
            "targetConfiguration": {"mcp": {"lambda": {"lambdaArn": s.state["lambda_arn"], "toolSchema": {"inlinePayload": TOOLS}}}},
            "credentialProviderConfigurations": [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]}
        a = c.create_gateway_target(**params)
        s.resource("target", a["targetId"], gateway=gid, name="idempotent")
        b = c.create_gateway_target(**params)
        assert a["targetId"] == b["targetId"], (a["targetId"], b["targetId"])
        return {"sameTargetId": a["targetId"]}
    s.test("gateway.targets.idempotency", target_idempotency)
    def browser_pagination():
        r = c.list_browsers(maxResults=1)
        ids = [x["browserId"] for x in r["browserSummaries"]]
        while r.get("nextToken"):
            r = c.list_browsers(maxResults=1, nextToken=r["nextToken"])
            ids.extend(x["browserId"] for x in r["browserSummaries"])
        assert len(set(ids)) == len(ids) and len(ids) > 1
        return {"uniqueBrowsers": len(ids)}
    s.test("browser.pagination", browser_pagination)
    def idempotency():
        token = str(uuid.uuid4())
        a = start(s, clientToken=token)
        b = start(s, clientToken=token)
        try:
            assert a["sessionId"] == b["sessionId"], (a["sessionId"], b["sessionId"])
            return {"sameSessionId": a["sessionId"]}
        finally:
            stop(s, a)
            if a["sessionId"] != b["sessionId"]:
                stop(s, b)
    s.test("browser.session.idempotency", idempotency)
    def profile_tags():
        pid = next(x["id"] for x in s.state["resources"] if x["kind"] == "profile")
        r = c.get_browser_profile(profileId=pid)
        arn = r["profileArn"]
        c.tag_resource(resourceArn=arn, tags={"TestFeature": "profiles"})
        tags = c.list_tags_for_resource(resourceArn=arn)
        assert tags["tags"]["TestFeature"] == "profiles", tags
        c.untag_resource(resourceArn=arn, tagKeys=["TestFeature"])
        assert "TestFeature" not in c.list_tags_for_resource(resourceArn=arn)["tags"]
        return {"tagAddListRemoveVerified": True}
    s.test("browser.profile.tags", profile_tags)
    available = s.client("ec2").describe_vpc_endpoint_services()["ServiceNames"]
    names = [x for x in available if "agentcore" in x]
    s.record("gateway.private_link", "NOT_AVAILABLE" if not names else "PARTIAL",
        {"advertisedAgentCoreEndpointServices": names, "scope": "Service catalog in this account/region"})
    s.record("browser.private_link", "NOT_AVAILABLE" if not names else "PARTIAL",
        {"advertisedAgentCoreEndpointServices": names, "scope": "Service catalog in this account/region; Browser VPC egress tested separately"})
    private_target(s)
    for name, settings in [("no_auth", {"authorizerType": "NONE"}), ("semantic_search", {
        "authorizerType": "AWS_IAM", "protocolConfiguration": {"mcp": {"searchType": "SEMANTIC"}}})]:
        params = {"name": s.name + "-" + name.replace("_", "-"), "roleArn": s.state["agentcore_role"], "protocolType": "MCP", **settings}
        try:
            r = c.create_gateway(**params)
            s.resource("gateway", r["gatewayId"])
            s.record("china_exclusion.gateway." + name, "UNEXPECTED_ACCEPTANCE", {"gatewayId": r["gatewayId"]})
        except ClientError as e:
            s.record("china_exclusion.gateway." + name, "CONFIRMED", e.response)


def private_target(s):
    from gateway_tests import target, openapi
    schema = openapi(s)
    schema["servers"] = [{"url": "https://" + s.state["private_ip"] + ":8443"}]
    try:
        r = target(s, "private-target", {"mcp": {"openApiSchema": {"inlinePayload": json.dumps(schema)}}},
            privateEndpoint={"managedVpcResource": {"vpcIdentifier": s.state["vpc"], "subnetIds": [s.state["subnet"]],
                "securityGroupIds": [s.state["sg"]], "endpointIpAddressType": "IPV4"}})
        s.record("gateway.private_target", "PARTIAL", {"readyTarget": r["targetId"],
            "unverified": "Invocation needs a private endpoint certificate trusted by Gateway"})
    except Exception as e:
        s.record("gateway.private_target", "NOT_AVAILABLE" if "not supported" in str(e).lower() else "BLOCKED",
            {"type": type(e).__name__, "message": str(e)})
