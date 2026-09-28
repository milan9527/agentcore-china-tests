import json
import time
from urllib.parse import urlparse
from cryptography.hazmat.primitives import serialization
import jwt
import requests
from botocore.config import Config
from gateway_tests import target, call, openapi, TOOLS
from suite import ROOT, RESULTS


def run(s):
    c = s.control
    gid = s.state["gateway"]["gatewayId"]
    role = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
    signed = [{"credentialProviderType": "GATEWAY_IAM_ROLE",
               "credentialProvider": {"iamCredentialProvider": {"service": "execute-api", "region": s.region}}}]
    r = s.test("gateway.openapi.inline_target", lambda: target(s, "openapi-inline",
        {"mcp": {"openApiSchema": {"inlinePayload": json.dumps(openapi(s))}}}, signed,
        metadataConfiguration={"allowedRequestHeaders": ["x-cn-test"], "allowedQueryParameters": ["cn_test"],
                               "allowedResponseHeaders": ["x-cn-result"]}))
    if r:
        s.test("gateway.openapi.invoke", lambda: call(s, "openapi-inline___get_echo", {"message": "openapi-ok"}, "openapi-ok"))
        s.test("gateway.metadata.request_header", lambda: call(s, "openapi-inline___get_echo", {},
            "forward-ok", extra_headers={"x-cn-test": "forward-ok"}))
    r = s.test("gateway.openapi.s3_schema", lambda: target(s, "openapi-s3",
        {"mcp": {"openApiSchema": {"s3": {"uri": f"s3://{s.state['bucket']}/openapi.json"}}}}, signed))
    if r:
        s.test("gateway.openapi.s3_invoke", lambda: call(s, "openapi-s3___get_echo", {}, "echo-ok"))
    r = s.test("gateway.api_gateway.filters_overrides", lambda: target(s, "api-stage", {"mcp": {"apiGateway": {
        "restApiId": s.state["api_id"], "stage": "test", "apiGatewayToolConfiguration": {
            "toolFilters": [{"filterPath": "/iam", "methods": ["GET"]}],
            "toolOverrides": [{"path": "/iam", "method": "GET", "name": "iam_echo", "description": "IAM authorized echo"}]}}}}, role))
    if r:
        s.test("gateway.api_gateway.iam_invocation", lambda: call(s, "api-stage___iam_echo", {}, "echo-ok"))
    r = s.test("gateway.mcp_server.target", lambda: target(s, "mcp-server", {"mcp": {"mcpServer": {"endpoint": s.state["api_url"] + "/mcp"}}}, signed))
    if r:
        s.test("gateway.mcp_server.invoke", lambda: call(s, "mcp-server___echo", {"text": "mcp-ok"}, "mcp-echo:mcp-ok"))
        s.test("gateway.mcp_server.synchronize", lambda: c.synchronize_gateway_targets(gatewayIdentifier=gid, targetIdList=[r["targetId"]]))
        for method, params, contains in [("prompts/list", {}, "hello"),
            ("prompts/get", {"name": "mcp-server___hello", "arguments": {"name": "China"}}, "Hello China"),
            ("resources/list", {}, "test://china/info"), ("resources/read", {"uri": "test://china/info"}, "china-resource-ok"),
            ("resources/templates/list", {}, "test://china/{name}")]:
            s.test("gateway.mcp." + method.replace("/", "_"), lambda m=method, p=params, x=contains: s.require_mcp(s.mcp(m, p), x))
    r = s.test("gateway.mcp_server.dynamic_listing", lambda: target(s, "mcp-dynamic",
        {"mcp": {"mcpServer": {"endpoint": s.state["api_url"] + "/mcp", "listingMode": "DYNAMIC"}}}, signed))
    if r:
        s.test("gateway.mcp_server.dynamic_invoke", lambda: call(s, "mcp-dynamic___echo", {"text": "dynamic-ok"}, "dynamic-ok"))
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
    # Stateless MCP version introduced in July 2026.
    s.test("gateway.mcp.server_discover.2026-07-28", lambda: s.require_mcp(s.mcp("server/discover", {
        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}, version="2026-07-28")))
    s.test("gateway.mcp.tools_list.2026-07-28", lambda: s.require_mcp(s.mcp("tools/list", {
        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}, version="2026-07-28"), "lambda-inline___add"))
    s.test("gateway.smithy", lambda: smithy(s))
    s.test("gateway.kms", lambda: kms(s))
    s.test("gateway.jwt", lambda: jwt_test(s))


def smithy(s):
    model = json.loads((ROOT / "docs/lambda-smithy.json").read_text())
    shapes = model["shapes"]
    svc = next(k for k, v in shapes.items() if v["type"] == "service")
    op = "com.amazonaws.lambda#GetFunctionConcurrency"
    service = shapes[svc]
    service["operations"] = [{"target": op}]
    service.pop("resources", None)
    for trait in ["smithy.rules#endpointBdd", "smithy.rules#endpointTests", "aws.api#tagEnabled"]:
        service["traits"].pop(trait, None)
    def refs(x):
        if isinstance(x, dict):
            if "target" in x and isinstance(x["target"], str):
                yield x["target"]
            for v in x.values():
                yield from refs(v)
        elif isinstance(x, list):
            for v in x:
                yield from refs(v)
    needed = {svc}
    queue = [svc]
    while queue:
        k = queue.pop()
        for ref in refs(shapes[k]):
            if ref in shapes and ref not in needed:
                needed.add(ref)
                queue.append(ref)
    model["shapes"] = {k: v for k, v in shapes.items() if k in needed}
    model.pop("metadata", None)
    payload = json.dumps(model)
    (ROOT / "docs/lambda-smithy-minimal.json").write_text(json.dumps(model, indent=2))
    iam = s.client("iam")
    iam.put_role_policy(RoleName=s.name + "-agentcore", PolicyName="smithy-read", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "lambda:GetFunctionConcurrency",
                                              "Resource": s.state["lambda_arn"]}]}))
    r = target(s, "smithy", {"mcp": {"smithyModel": {"inlinePayload": payload}}}, [{"credentialProviderType": "GATEWAY_IAM_ROLE"}])
    tools = s.require_mcp(s.mcp("tools/list", {}))
    body = tools["body"][-1] if isinstance(tools["body"], list) else tools["body"]
    tool = next(x for x in body["result"]["tools"] if x["name"].startswith("smithy___"))
    schema = tool["inputSchema"]
    args = {"FunctionName": s.name}
    for prop in schema.get("properties", {}):
        if prop.lower() == "region":
            args[prop] = s.region
    result = call(s, tool["name"], args)
    return {"targetId": r["targetId"], "tool": tool, "invocation": result}


def kms(s):
    key = s.client("kms").create_key(Description=s.name + " temporary Gateway encryption test", Tags=[{"TagKey": "Purpose", "TagValue": s.name}])["KeyMetadata"]
    s.resource("kms", key["KeyId"])
    s.client("iam").put_role_policy(RoleName=s.name + "-agentcore", PolicyName="kms-test", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["kms:CreateGrant", "kms:DescribeKey", "kms:Decrypt", "kms:GenerateDataKey"],
                                              "Resource": key["Arn"]}]}))
    r = s.control.update_gateway(gatewayIdentifier=s.state["gateway"]["gatewayId"], name=s.name, roleArn=s.state["agentcore_role"],
        authorizerType="AWS_IAM", protocolType="MCP", kmsKeyArn=key["Arn"])
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=s.state["gateway"]["gatewayId"]))
    invocation = call(s, "lambda-inline___add", {"a": 21, "b": 21}, "42")
    return {"kmsKeyArn": key["Arn"], "invocation": invocation}


def jwt_test(s):
    key = serialization.load_pem_private_key((RESULTS / f"{s.region}-private-key.pem").read_bytes(), None)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="cn-test", use="sig", alg="RS256")
    bucket = s.state["bucket"]
    s3 = s.session.client("s3", config=Config(signature_version="s3v4"))
    s3.put_object(Bucket=bucket, Key="jwks.json", Body=json.dumps({"keys": [jwk]}), ContentType="application/json")
    jwks_url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": "jwks.json"}, ExpiresIn=14400)
    issuer = f"https://{bucket}.s3.{s.region}.amazonaws.com.cn"
    metadata = {"issuer": issuer, "jwks_uri": jwks_url, "authorization_endpoint": issuer + "/authorize",
                "token_endpoint": issuer + "/token", "response_types_supported": ["code"],
                "subject_types_supported": ["public"], "id_token_signing_alg_values_supported": ["RS256"]}
    s3.put_object(Bucket=bucket, Key=".well-known/openid-configuration", Body=json.dumps(metadata), ContentType="application/json")
    discovery = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": ".well-known/openid-configuration"}, ExpiresIn=14400)
    # Validate discovery from this client before attributing errors to Gateway.
    response = requests.get(discovery, timeout=30)
    assert response.status_code == 200, {"discoveryStatus": response.status_code, "body": response.text[:500]}
    r = s.control.create_gateway(name=s.name + "-jwt", roleArn=s.state["agentcore_role"], protocolType="MCP",
        authorizerType="CUSTOM_JWT", authorizerConfiguration={"customJWTAuthorizer": {"discoveryUrl": discovery,
            "allowedAudience": ["cn-test"], "allowedClients": ["cn-test"], "allowedScopes": ["test"]}})
    s.resource("gateway", r["gatewayId"])
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=r["gatewayId"]))
    old = s.state["gateway"]
    try:
        s.state["gateway"] = r
        target(s, "jwt-lambda", {"mcp": {"lambda": {"lambdaArn": s.state["lambda_arn"], "toolSchema": {"inlinePayload": TOOLS}}}},
               [{"credentialProviderType": "GATEWAY_IAM_ROLE"}])
        claims = {"iss": issuer, "sub": "synthetic-user", "aud": "cn-test", "client_id": "cn-test",
                  "scope": "test", "iat": int(time.time()), "exp": int(time.time()) + 600}
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "cn-test"})
        good = call(s, "jwt-lambda___add", {"a": 20, "b": 22}, "42", token=token)
        claims["aud"] = "wrong-audience"
        bad = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "cn-test"})
        rejected = s.mcp("tools/list", {}, token=bad)
        assert rejected["status"] in (401, 403), rejected
        return {"validToken": good, "wrongAudienceRejected": rejected}
    finally:
        s.state["gateway"] = old
        s.save()
