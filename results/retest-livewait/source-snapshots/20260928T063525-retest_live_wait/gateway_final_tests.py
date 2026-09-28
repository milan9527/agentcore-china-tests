import io
import json
import time
import zipfile
from urllib.parse import urlsplit, urlunsplit, parse_qsl
import jwt
import requests
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from cryptography.hazmat.primitives import serialization
from gateway_tests import target, call, openapi, TOOLS
from gateway_more_tests import smithy
from suite import ROOT, RESULTS

VERSIONS = ["2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"]


def presign(s, path, method="GET", unsigned=False):
    req = AWSRequest(method=method, url=s.state["api_url"] + path)
    if unsigned:
        req.context["payload_signing_enabled"] = False
    SigV4QueryAuth(s.session.get_credentials().get_frozen_credentials(), "execute-api", s.region, expires=14400).add_auth(req)
    return req.url


def deploy(s):
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("backend.py", (ROOT / "backend.py").read_bytes())
    lam = s.client("lambda")
    lam.update_function_code(FunctionName=s.name, ZipFile=z.getvalue())
    lam.get_waiter("function_updated_v2").wait(FunctionName=s.name)
    env = lam.get_function_configuration(FunctionName=s.name)["Environment"]["Variables"]
    env.update(OIDC_ISSUER=s.state["api_url"], JWKS_URL=presign(s, "/jwks"), TOKEN_URL=presign(s, "/token", "POST", True))
    lam.update_function_configuration(FunctionName=s.name, Environment={"Variables": env})
    lam.get_waiter("function_updated_v2").wait(FunctionName=s.name)
    s.state["discovery_url"] = presign(s, "/.well-known/openid-configuration")
    s.state["token_url"] = env["TOKEN_URL"]
    s.save()
    return {"backendUpdated": True}


def config(s, **kw):
    r = s.control.update_gateway(gatewayIdentifier=s.state["gateway"]["gatewayId"], name=s.name,
        roleArn=s.state["agentcore_role"], protocolType="MCP", authorizerType="AWS_IAM", exceptionLevel="DEBUG",
        **kw)
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=s.state["gateway"]["gatewayId"]))
    return r


def run(s):
    s.test("gateway.fixture.update", lambda: deploy(s))
    supported = s.test("gateway.protocols.configure", lambda: config(s, protocolConfiguration={"mcp": {"supportedVersions": VERSIONS}}))
    if not supported:
        config(s)
    for version in VERSIONS[:-1]:
        def negotiate(v=version):
            r = s.require_mcp(s.mcp("initialize", {"protocolVersion": v, "capabilities": {},
                "clientInfo": {"name": "cn-test", "version": "1.0"}}, version=v))
            b = r["body"][-1] if isinstance(r["body"], list) else r["body"]
            assert b["result"]["protocolVersion"] == v, r
            s.require_mcp(s.mcp("tools/list", {}, version=v), "lambda-inline___add")
            return r
        s.test("gateway.mcp.initialize." + version, negotiate)
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "cn-test", "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}, "url": {}}, "sampling": {}}}
    for method in ["server/discover", "tools/list"]:
        s.test("gateway.mcp." + method.replace("/", "_") + ".2026-07-28", lambda m=method: s.require_mcp(s.mcp(m, {"_meta": meta},
            version="2026-07-28", extra_headers={"Mcp-Method": m})))
    s.test("gateway.interceptors.configure", lambda: config(s, interceptorConfigurations=[{
        "interceptor": {"lambda": {"arn": s.state["lambda_arn"]}}, "interceptionPoints": ["REQUEST", "RESPONSE"],
        "inputConfiguration": {"passRequestHeaders": True}}]))
    def intercept():
        r = call(s, "lambda-inline___add", {"a": 1, "b": 2}, "response-ok")
        b = r["body"][-1] if isinstance(r["body"], list) else r["body"]
        data = json.loads(b["result"]["content"][0]["text"])
        assert data["sum"] == 4, r
        return {"requestTransformedSum": 4, "response": r}
    s.test("gateway.interceptors.response_effect", intercept)
    s.test("gateway.interceptors.remove", lambda: config(s, protocolConfiguration={"mcp": {"supportedVersions": VERSIONS}}))
    s.test("gateway.smithy", lambda: smithy(s))
    s.test("gateway.kms", lambda: encrypted(s))
    s.test("gateway.jwt", lambda: jwt_flow(s))
    s.test("gateway.outbound.api_key", lambda: api_key(s))
    s.test("gateway.outbound.oauth_client_credentials", lambda: oauth(s))
    s.test("gateway.http_passthrough", lambda: passthrough(s))
    s.test("gateway.sessions_streaming.configure", lambda: config(s, protocolConfiguration={"mcp": {
        "supportedVersions": VERSIONS, "sessionConfiguration": {"sessionTimeoutInSeconds": 900},
        "streamingConfiguration": {"enableResponseStreaming": True}}}))
    init = s.test("gateway.sessions.initialize", lambda: s.require_mcp(s.mcp("initialize", {
        "protocolVersion": "2025-11-25", "capabilities": {"sampling": {}, "elicitation": {"form": {}, "url": {}}},
        "clientInfo": {"name": "cn-test", "version": "1.0"}}, version="2025-11-25")))
    if init:
        sid = init["headers"].get("mcp-session-id")
        s.state["mcp_session_id"] = sid
        s.save()
        headers = {"Mcp-Session-Id": sid} if sid else {}
        s.test("gateway.streaming.tool_call", lambda: call(s, "lambda-inline___add", {"a": 10, "b": 32}, "42",
            version="2025-11-25", extra_headers=headers))
        def notifications():
            r = s.require_mcp(s.mcp("tools/call", {"name": "mcp-dynamic___progress", "arguments": {"text": "done"},
                "_meta": {"progressToken": "cn-progress"}}, version="2025-11-25", extra_headers=headers))
            assert isinstance(r["body"], list), r
            methods = [x.get("method") for x in r["body"]]
            assert "notifications/progress" in methods, r
            assert "notifications/message" in methods, r
            return r
        s.test("gateway.streaming.progress_logging", notifications)
    for tool in ["elicit", "sample"]:
        def mrtr(name=tool):
            params = {"name": "mcp-dynamic___" + name, "arguments": {}, "_meta": meta}
            headers = {"Mcp-Method": "tools/call", "Mcp-Name": params["name"]}
            r = s.require_mcp(s.mcp("tools/call", params, version="2026-07-28", extra_headers=headers))
            body = r["body"][-1] if isinstance(r["body"], list) else r["body"]
            result = body["result"]
            assert result.get("resultType") == "input_required", r
            answer = {"action": "accept", "content": {"confirm": True}} if name == "elicit" else {
                "role": "assistant", "content": {"type": "text", "text": "test-ok"}, "model": "synthetic-test", "stopReason": "endTurn"}
            params["inputResponses"] = {key: answer for key in result["inputRequests"]}
            if "requestState" in result:
                params["requestState"] = result["requestState"]
            done = s.require_mcp(s.mcp("tools/call", params, version="2026-07-28", extra_headers=headers), "roundtrip-ok")
            return {"request": r, "completed": done}
        s.test("gateway.mcp." + ("elicitation" if tool == "elicit" else "sampling") + "_roundtrip", mrtr)
    config(s, protocolConfiguration={"mcp": {"supportedVersions": VERSIONS}})
    s.test("gateway.rate_limits", lambda: rate_limits(s))


def encrypted(s):
    key_id = next(x["id"] for x in s.state["resources"] if x["kind"] == "kms")
    key_arn = s.client("kms").describe_key(KeyId=key_id)["KeyMetadata"]["Arn"]
    r = s.control.create_gateway(name=s.name + "-kms", roleArn=s.state["agentcore_role"], protocolType="MCP",
                                authorizerType="AWS_IAM", kmsKeyArn=key_arn)
    s.resource("gateway", r["gatewayId"])
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=r["gatewayId"]))
    old = s.state["gateway"]
    try:
        s.state["gateway"] = r
        target(s, "encrypted", {"mcp": {"lambda": {"lambdaArn": s.state["lambda_arn"], "toolSchema": {"inlinePayload": TOOLS}}}},
               [{"credentialProviderType": "GATEWAY_IAM_ROLE"}])
        return {"kmsKeyArn": key_arn, "invocation": call(s, "encrypted___add", {"a": 21, "b": 21}, "42")}
    finally:
        s.state["gateway"] = old
        s.save()


def jwt_flow(s):
    discovery = requests.get(s.state["discovery_url"], timeout=30)
    assert discovery.status_code == 200, {"discoveryStatus": discovery.status_code}
    jwks = requests.get(discovery.json()["jwks_uri"], timeout=30)
    assert jwks.status_code == 200, {"jwksStatus": jwks.status_code}
    r = s.control.create_gateway(name=s.name + "-jwt", roleArn=s.state["agentcore_role"], protocolType="MCP",
        authorizerType="CUSTOM_JWT", authorizerConfiguration={"customJWTAuthorizer": {"discoveryUrl": s.state["discovery_url"],
            "allowedAudience": ["cn-test"], "allowedClients": ["cn-test"], "allowedScopes": ["test"]}})
    s.resource("gateway", r["gatewayId"])
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=r["gatewayId"]))
    old = s.state["gateway"]
    key = serialization.load_pem_private_key((RESULTS / f"{s.region}-private-key.pem").read_bytes(), None)
    try:
        s.state["gateway"] = r
        target(s, "jwt-lambda", {"mcp": {"lambda": {"lambdaArn": s.state["lambda_arn"], "toolSchema": {"inlinePayload": TOOLS}}}},
               [{"credentialProviderType": "GATEWAY_IAM_ROLE"}])
        claims = {"iss": s.state["api_url"], "sub": "synthetic-user", "aud": "cn-test", "client_id": "cn-test",
                  "scope": "test", "iat": int(time.time()), "exp": int(time.time()) + 600}
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "cn-test"})
        good = call(s, "jwt-lambda___add", {"a": 20, "b": 22}, "42", token=token)
        rejected = {}
        for label, change in [("audience", {"aud": "wrong"}), ("scope", {"scope": "wrong"}), ("expiry", {"exp": int(time.time()) - 3600})]:
            bad = jwt.encode({**claims, **change}, key, algorithm="RS256", headers={"kid": "cn-test"})
            response = s.mcp("tools/list", {}, token=bad)
            assert response["status"] in (401, 403), response
            rejected[label] = response["status"]
        return {"validToken": good, "rejectedTokens": rejected}
    finally:
        s.state["gateway"] = old
        s.save()


def secured_schema(s, name):
    schema = openapi(s, "/secure", name)
    params = dict(parse_qsl(urlsplit(presign(s, "/secure")).query))
    schema["paths"]["/secure"]["get"]["parameters"] = [
        {"name": key, "in": "query", "required": True, "schema": {"type": "string"}} for key in params]
    return schema, params


def provider_permission(s, response):
    # Secret contents are never persisted in evidence.
    arn = response.get("secretArn") or response.get("apiKeySecretArn") or response.get("clientSecretArn")
    if isinstance(arn, dict):
        arn = arn.get("secretArn")
    if arn:
        s.client("iam").put_role_policy(RoleName=s.name + "-agentcore", PolicyName="identity-secret-" + str(len(s.state["resources"])),
            PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue"], "Resource": arn}]}))


def api_key(s):
    secret = json.loads((RESULTS / f"{s.region}-secrets.json").read_text())["test_secret"]
    p = s.control.create_api_key_credential_provider(name=s.name + "-key", apiKey=secret)
    s.resource("api-key-provider", s.name + "-key")
    provider_permission(s, p)
    schema, args = secured_schema(s, "secure_key")
    target(s, "api-key", {"mcp": {"openApiSchema": {"inlinePayload": json.dumps(schema)}}}, [{
        "credentialProviderType": "API_KEY", "credentialProvider": {"apiKeyCredentialProvider": {
            "providerArn": p["credentialProviderArn"], "credentialParameterName": "x-test-key", "credentialLocation": "HEADER"}}}])
    result = call(s, "api-key___secure_key", args, "true")
    return {"providerArn": p["credentialProviderArn"], "invocation": result}


def oauth(s):
    secret = json.loads((RESULTS / f"{s.region}-secrets.json").read_text())["test_secret"]
    probe = requests.post(s.state["token_url"], data={"grant_type": "client_credentials", "client_id": "cn-test", "client_secret": secret}, timeout=30)
    assert probe.status_code == 200, {"tokenEndpointStatus": probe.status_code, "error": probe.text[:400] if probe.status_code != 200 else None}
    p = s.control.create_oauth2_credential_provider(name=s.name + "-oauth", credentialProviderVendor="CustomOauth2",
        oauth2ProviderConfigInput={"customOauth2ProviderConfig": {"clientId": "cn-test", "clientSecret": secret,
            "oauthDiscovery": {"authorizationServerMetadata": {"issuer": s.state["api_url"],
                "authorizationEndpoint": s.state["api_url"] + "/authorize", "tokenEndpoint": s.state["token_url"],
                "responseTypes": ["code"], "tokenEndpointAuthMethods": ["client_secret_basic", "client_secret_post"]}}}})
    s.resource("oauth-provider", s.name + "-oauth")
    provider_permission(s, p)
    schema, args = secured_schema(s, "secure_oauth")
    target(s, "oauth", {"mcp": {"openApiSchema": {"inlinePayload": json.dumps(schema)}}}, [{
        "credentialProviderType": "OAUTH", "credentialProvider": {"oauthCredentialProvider": {
            "providerArn": p["credentialProviderArn"], "scopes": ["test"], "grantType": "CLIENT_CREDENTIALS"}}}])
    return {"providerArn": p["credentialProviderArn"], "invocation": call(s, "oauth___secure_oauth", args, "true")}


def passthrough(s):
    target(s, "http-test", {"http": {"passthrough": {"endpoint": s.state["api_url"], "protocolType": "CUSTOM"}}}, [{
        "credentialProviderType": "GATEWAY_IAM_ROLE", "credentialProvider": {"iamCredentialProvider": {"service": "execute-api", "region": s.region}}}])
    url = s.state["gateway"]["gatewayUrl"].removesuffix("/mcp") + "/http-test/echo"
    r = requests.get(url, headers=s.signed_headers(url), timeout=30)
    assert r.status_code == 200, {"status": r.status_code, "body": r.text}
    assert r.json()["message"] == "echo-ok"
    return {"status": r.status_code, "body": r.json()}


def rate_limits(s):
    c = s.control
    gid = s.state["gateway"]["gatewayId"]
    r = c.create_gateway_rate_limit(gatewayIdentifier=gid, rateLimitId="cn-test-limit", dimensionKeys=["targetName"],
        entries=[{"dimensions": {"targetName": "lambda-inline"}, "requests": [{"rate": 0, "period": "second"}]}])
    s.resource("rate-limit", r["rateLimitId"], gateway=gid)
    s.wait(lambda: c.get_gateway_rate_limit(gatewayIdentifier=gid, rateLimitId=r["rateLimitId"]))
    listed = c.list_gateway_rate_limits(gatewayIdentifier=gid)
    deadline = time.monotonic() + 45
    while True:
        rejected = s.mcp("tools/call", {"name": "lambda-inline___add", "arguments": {"a": 1, "b": 2}})
        if rejected["status"] == 429:
            break
        assert time.monotonic() < deadline, rejected
        time.sleep(3)
    c.update_gateway_rate_limit(gatewayIdentifier=gid, rateLimitId=r["rateLimitId"],
        entries=[{"dimensions": {"targetName": "lambda-inline"}, "requests": [{"rate": 100, "period": "second"}]}])
    s.wait(lambda: c.get_gateway_rate_limit(gatewayIdentifier=gid, rateLimitId=r["rateLimitId"]))
    c.delete_gateway_rate_limit(gatewayIdentifier=gid, rateLimitId=r["rateLimitId"])
    return {"createdListedUpdatedDeleted": True, "zeroRateRejected": rejected}
