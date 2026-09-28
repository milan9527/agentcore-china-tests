import json
import time
import requests
import jwt
from suite import RESULTS

TOOLS = [
    {"name": "add", "description": "Add two numbers", "inputSchema": {"type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}},
    {"name": "echo", "description": "Echo text", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
    {"name": "error", "description": "Return a synthetic test error", "inputSchema": {"type": "object",
        "properties": {"fail": {"type": "boolean"}}, "required": ["fail"]}}]


def target(s, name, configuration, credentials=None, **kw):
    existing = next((r for r in s.state["resources"] if r["kind"] == "target" and r.get("name") == name
                     and r.get("gateway") == s.state["gateway"]["gatewayId"] and not r.get("deleted")), None)
    if existing:
        r = s.control.get_gateway_target(gatewayIdentifier=existing["gateway"], targetId=existing["id"])
        if r["status"] == "FAILED":
            if credentials:
                kw["credentialProviderConfigurations"] = credentials
            s.control.update_gateway_target(gatewayIdentifier=existing["gateway"], targetId=existing["id"],
                name=name, targetConfiguration=configuration, **kw)
            r = s.wait(lambda: s.control.get_gateway_target(gatewayIdentifier=existing["gateway"], targetId=existing["id"]))
        assert r["status"] == "READY", r
        return r
    if credentials:
        kw["credentialProviderConfigurations"] = credentials
    r = s.control.create_gateway_target(gatewayIdentifier=s.state["gateway"]["gatewayId"], name=name,
        targetConfiguration=configuration, **kw)
    s.resource("target", r["targetId"], gateway=s.state["gateway"]["gatewayId"], name=name)
    return s.wait(lambda: s.control.get_gateway_target(gatewayIdentifier=s.state["gateway"]["gatewayId"], targetId=r["targetId"]))


def call(s, name, arguments, contains=None, **kw):
    return s.require_mcp(s.mcp("tools/call", {"name": name, "arguments": arguments}, **kw), contains)


def openapi(s, path="/echo", name="get_echo", security=None):
    schema = {"openapi": "3.0.3", "info": {"title": "China synthetic API", "version": "1.0"},
        "servers": [{"url": s.state["api_url"]}], "paths": {path: {"get": {"operationId": name,
        "description": "Read a synthetic response", "parameters": [{"name": "message", "in": "query", "schema": {"type": "string"}}],
        "responses": {"200": {"description": "Success", "content": {"application/json": {"schema": {"type": "object",
                    "properties": {"message": {"type": "string"}, "authenticated": {"type": "boolean"}}}}}}}}}}}
    if security:
        schema["components"] = {"securitySchemes": security}
        schema["security"] = [{next(iter(security)): []}]
    return schema


def run(s):
    c = s.control
    if "gateway" not in s.state:
        r = s.test("gateway.create_iam", lambda: c.create_gateway(name=s.name, roleArn=s.state["agentcore_role"],
            protocolType="MCP", authorizerType="AWS_IAM", exceptionLevel="DEBUG",
            protocolConfiguration={"mcp": {"instructions": "Synthetic China feature test"}},
            tags={"Purpose": s.name}))
        if not r:
            return
        s.state["gateway"] = r
        s.resource("gateway", r["gatewayId"])
    gateway = s.state["gateway"]
    gid, arn = gateway["gatewayId"], gateway["gatewayArn"]
    s.test("gateway.get_ready", lambda: s.wait(lambda: c.get_gateway(gatewayIdentifier=gid)))
    s.test("gateway.list", lambda: c.list_gateways(maxResults=1))
    s.test("gateway.tags.add", lambda: c.tag_resource(resourceArn=arn, tags={"Feature": "gateway"}))
    s.test("gateway.tags.list", lambda: c.list_tags_for_resource(resourceArn=arn))
    s.test("gateway.tags.remove", lambda: c.untag_resource(resourceArn=arn, tagKeys=["Feature"]))
    role = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    s.test("gateway.lambda.inline_target", lambda: target(s, "lambda-inline",
        {"mcp": {"lambda": {"lambdaArn": s.state["lambda_arn"], "toolSchema": {"inlinePayload": TOOLS}}}}, role))
    for version in ["2025-03-26", "2025-06-18", "2025-11-25"]:
        s.test("gateway.mcp.initialize." + version, lambda v=version: s.require_mcp(s.mcp("initialize", {
            "protocolVersion": v, "capabilities": {}, "clientInfo": {"name": "china-test", "version": "1.0"}}, version=v), "protocolVersion"))
    s.test("gateway.mcp.tools_list", lambda: s.require_mcp(s.mcp("tools/list", {}), "lambda-inline___add"))
    s.test("gateway.lambda.invoke_add", lambda: call(s, "lambda-inline___add", {"a": 17, "b": 25}, "42"))
    s.test("gateway.lambda.invoke_unicode", lambda: call(s, "lambda-inline___echo", {"text": "北京宁夏"}, "\\u5317"))
    def negative():
        r = s.mcp("tools/call", {"name": "lambda-inline___error", "arguments": {"fail": True}})
        assert "error" in json.dumps(r).lower() or "isError" in json.dumps(r), r
        return r
    s.test("gateway.debug.target_error", negative)
    def unauthenticated():
        r = requests.post(gateway["gatewayUrl"], json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                          headers={"Accept": "application/json, text/event-stream"}, timeout=30)
        assert r.status_code in (401, 403), {"status": r.status_code, "body": r.text}
        return {"status": r.status_code, "body": r.text}
    s.test("gateway.iam.unsigned_denied", unauthenticated)
    s.client("s3").put_object(Bucket=s.state["bucket"], Key="lambda-tools.json", Body=json.dumps(TOOLS))
    s.test("gateway.lambda.s3_schema", lambda: target(s, "lambda-s3", {"mcp": {"lambda": {
        "lambdaArn": s.state["lambda_arn"], "toolSchema": {"s3": {"uri": f"s3://{s.state['bucket']}/lambda-tools.json",
                                                             "bucketOwnerAccountId": s.account}}}}}, role))
    s.test("gateway.lambda.s3_invoke", lambda: call(s, "lambda-s3___add", {"a": 20, "b": 22}, "42"))
    s.test("gateway.targets.list", lambda: c.list_gateway_targets(gatewayIdentifier=gid, maxResults=1))
    res = s.test("gateway.openapi.inline_target", lambda: target(s, "openapi-inline",
        {"mcp": {"openApiSchema": {"inlinePayload": json.dumps(openapi(s))}}},
        metadataConfiguration={"allowedRequestHeaders": ["x-cn-test"], "allowedQueryParameters": ["cn_test"],
                               "allowedResponseHeaders": ["x-cn-result"]}))
    if res:
        s.test("gateway.openapi.invoke", lambda: call(s, "openapi-inline___get_echo", {"message": "openapi-ok"}, "openapi-ok"))
        s.test("gateway.metadata.request_header", lambda: call(s, "openapi-inline___get_echo", {},
            "forward-ok", extra_headers={"x-cn-test": "forward-ok"}))
    s.client("s3").put_object(Bucket=s.state["bucket"], Key="openapi.json", Body=json.dumps(openapi(s)))
    res = s.test("gateway.openapi.s3_schema", lambda: target(s, "openapi-s3",
        {"mcp": {"openApiSchema": {"s3": {"uri": f"s3://{s.state['bucket']}/openapi.json"}}}}))
    if res:
        s.test("gateway.openapi.s3_invoke", lambda: call(s, "openapi-s3___get_echo", {}, "echo-ok"))
    res = s.test("gateway.api_gateway.filters_overrides", lambda: target(s, "api-stage", {"mcp": {"apiGateway": {
        "restApiId": s.state["api_id"], "stage": "test", "apiGatewayToolConfiguration": {
            "toolFilters": [{"filterPath": "/iam", "methods": ["GET"]}],
            "toolOverrides": [{"path": "/iam", "method": "GET", "name": "iam_echo", "description": "IAM authorized echo"}]}}}}, role))
    if res:
        s.test("gateway.api_gateway.iam_invocation", lambda: call(s, "api-stage___iam_echo", {}, "echo-ok"))
    res = s.test("gateway.mcp_server.target", lambda: target(s, "mcp-server", {"mcp": {"mcpServer": {"endpoint": s.state["api_url"] + "/mcp"}}}))
    if res:
        s.test("gateway.mcp_server.invoke", lambda: call(s, "mcp-server___echo", {"text": "mcp-ok"}, "mcp-echo:mcp-ok"))
        s.test("gateway.mcp_server.synchronize", lambda: c.synchronize_gateway_targets(gatewayIdentifier=gid, targetIdList=[res["targetId"]]))
        for method, params, contains in [("prompts/list", {}, "hello"), ("prompts/get", {"name": "mcp-server___hello", "arguments": {"name": "China"}}, "Hello China"),
            ("resources/list", {}, "test://china/info"), ("resources/read", {"uri": "test://china/info"}, "china-resource-ok"),
            ("resources/templates/list", {}, "test://china/{name}")]:
            s.test("gateway.mcp." + method.replace("/", "_"), lambda m=method, p=params, x=contains: s.require_mcp(s.mcp(m, p), x))
    s.test("gateway.update_description", lambda: c.update_gateway(gatewayIdentifier=gid, name=s.name,
        description="Updated by China feature test", roleArn=s.state["agentcore_role"], protocolType="MCP", authorizerType="AWS_IAM",
        protocolConfiguration={"mcp": {"instructions": "Synthetic China feature test"}}, exceptionLevel="DEBUG"))
    s.wait(lambda: c.get_gateway(gatewayIdentifier=gid))
    s.test("gateway.interceptors.configure", lambda: c.update_gateway(gatewayIdentifier=gid, name=s.name,
        roleArn=s.state["agentcore_role"], protocolType="MCP", authorizerType="AWS_IAM", exceptionLevel="DEBUG",
        interceptorConfigurations=[{"interceptor": {"lambda": {"arn": s.state["lambda_arn"]}}, "interceptionPoints": ["REQUEST", "RESPONSE"],
                                   "inputConfiguration": {"passRequestHeaders": True}}]))
    s.wait(lambda: c.get_gateway(gatewayIdentifier=gid))
    def intercept():
        r = call(s, "lambda-inline___add", {"a": 1, "b": 2}, "3")
        assert r["headers"].get("x-cn-test-interceptor") == "response-ok", r
        return r
    s.test("gateway.interceptors.response_effect", intercept)
    s.test("gateway.interceptors.remove", lambda: c.update_gateway(gatewayIdentifier=gid, name=s.name,
        roleArn=s.state["agentcore_role"], protocolType="MCP", authorizerType="AWS_IAM"))
    s.wait(lambda: c.get_gateway(gatewayIdentifier=gid))
    def sessions():
        r = c.update_gateway(gatewayIdentifier=gid, name=s.name, roleArn=s.state["agentcore_role"],
            protocolType="MCP", authorizerType="AWS_IAM", protocolConfiguration={"mcp": {
                "sessionConfiguration": {"sessionTimeoutInSeconds": 900}, "streamingConfiguration": {"enableResponseStreaming": True}}})
        s.wait(lambda: c.get_gateway(gatewayIdentifier=gid))
        return r
    r = s.test("gateway.sessions_streaming.configure", sessions)
    if r:
        init = s.test("gateway.sessions.initialize", lambda: s.require_mcp(s.mcp("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {"sampling": {}, "elicitation": {}},
            "clientInfo": {"name": "china-test", "version": "1.0"}}, version="2025-11-25")))
        if init:
            s.state["mcp_session_id"] = init["headers"].get("mcp-session-id")
            s.save()
            s.test("gateway.streaming.tool_call", lambda: call(s, "lambda-inline___add", {"a": 10, "b": 32}, "42",
                version="2025-11-25", extra_headers={"Mcp-Session-Id": s.state["mcp_session_id"]} if s.state["mcp_session_id"] else {}))
    return {"gateway": gid}
