import json
import time
import requests
from gateway_final_tests import deploy, config, VERSIONS, secured_schema, provider_permission
from gateway_tests import target, call


def run(s):
    deploy(s)
    config(s, protocolConfiguration={"mcp": {"supportedVersions": VERSIONS}})
    p = s.control.get_api_key_credential_provider(name=s.name + "-key")
    provider_permission(s, p)
    def api_key():
        schema, args = secured_schema(s, "secure_key")
        r = call(s, "api-key___secure_key", args, "true")
        return {"authenticatedBackendResponse": r}
    s.test("gateway.outbound.api_key", api_key)
    s.test("gateway.http_passthrough", lambda: http_gateway(s))
    s.test("gateway.outbound.caller_iam", lambda: caller(s))
    jwt_result = s.test("gateway.jwt.configuration_and_rejection", lambda: jwt_config(s))
    s.record("gateway.jwt", "PARTIAL" if jwt_result else "BLOCKED", {"tested": "CUSTOM_JWT configuration and invalid-token rejection" if jwt_result else "see configuration test failure",
        "unverified": "Valid token invocation", "blocker": "No approved OIDC issuer/test identity with usable signing credentials; discovery URLs reject signed query strings."})
    s.test("gateway.outbound.oauth_configuration", lambda: oauth_config(s))
    for feature in ["gateway.outbound.oauth_client_credentials", "gateway.outbound.oauth_authorization_code",
                    "gateway.outbound.oauth_token_exchange", "gateway.outbound.jwt_passthrough"]:
        s.record(feature, "BLOCKED", {"reason": "No approved test OAuth/OIDC provider or user token. Fixture API requires AWS_IAM and cannot receive Bearer authorization; China API Gateway unauthenticated endpoints require ICP registration."})
    signed = [{"credentialProviderType": "GATEWAY_IAM_ROLE",
               "credentialProvider": {"iamCredentialProvider": {"service": "execute-api", "region": s.region}}}]
    s.test("gateway.mcp_server.refresh_schema", lambda: target(s, "mcp-new",
        {"mcp": {"mcpServer": {"endpoint": s.state["api_url"] + "/mcp", "listingMode": "DYNAMIC"}}}, signed))
    config(s, protocolConfiguration={"mcp": {"supportedVersions": VERSIONS,
        "sessionConfiguration": {"sessionTimeoutInSeconds": 900}, "streamingConfiguration": {"enableResponseStreaming": True}}})
    init = s.require_mcp(s.mcp("initialize", {"protocolVersion": "2025-11-25", "capabilities": {
        "sampling": {}, "elicitation": {"form": {}, "url": {}}},
        "clientInfo": {"name": "cn-test", "version": "1.0"}}, version="2025-11-25"))
    sid = init["headers"]["mcp-session-id"]
    headers = {"Mcp-Session-Id": sid}
    initialized = s.mcp("notifications/initialized", {}, version="2025-11-25", extra_headers=headers)
    assert initialized["status"] in (200, 202), initialized
    s.record("gateway.sessions.full_handshake", "PASS", {"sessionId": sid, "notificationStatus": initialized["status"]})
    s.test("gateway.streaming.tool_call", lambda: call(s, "lambda-inline___add", {"a": 10, "b": 32}, "42",
        version="2025-11-25", extra_headers=headers))
    def progress():
        r = s.require_mcp(s.mcp("tools/call", {"name": "mcp-new___progress", "arguments": {"text": "done"},
            "_meta": {"progressToken": "cn-progress"}}, version="2025-11-25", extra_headers=headers))
        assert isinstance(r["body"], list), r
        methods = [x.get("method") for x in r["body"]]
        assert "notifications/progress" in methods and "notifications/message" in methods, r
        return r
    s.test("gateway.streaming.progress_logging", progress)
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "cn-test", "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}, "url": {}}, "sampling": {}}}
    for tool in ["elicit", "sample"]:
        def mrtr(name=tool):
            params = {"name": "mcp-new___" + name, "arguments": {}, "_meta": meta}
            h = {"Mcp-Method": "tools/call", "Mcp-Name": params["name"]}
            r = s.require_mcp(s.mcp("tools/call", params, version="2026-07-28", extra_headers=h))
            body = r["body"][-1] if isinstance(r["body"], list) else r["body"]
            result = body["result"]
            assert result.get("resultType") == "input_required", r
            answer = {"action": "accept", "content": {"confirm": True}} if name == "elicit" else {
                "role": "assistant", "content": {"type": "text", "text": "test-ok"}, "model": "synthetic-test", "stopReason": "endTurn"}
            params["inputResponses"] = {key: answer for key in result["inputRequests"]}
            if "requestState" in result:
                params["requestState"] = result["requestState"]
            done = s.require_mcp(s.mcp("tools/call", params, version="2026-07-28", extra_headers=h), "roundtrip-ok")
            return {"inputRequested": r, "completed": done}
        s.test("gateway.mcp." + ("elicitation" if tool == "elicit" else "sampling") + "_roundtrip", mrtr)
    config(s, protocolConfiguration={"mcp": {"supportedVersions": VERSIONS}})


def http_gateway(s):
    r = s.control.create_gateway(name=s.name + "-http", roleArn=s.state["agentcore_role"], authorizerType="AWS_IAM")
    s.resource("gateway", r["gatewayId"])
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=r["gatewayId"]))
    old = s.state["gateway"]
    try:
        s.state["gateway"] = r
        target(s, "http-test", {"http": {"passthrough": {"endpoint": s.state["api_url"], "protocolType": "CUSTOM"}}}, [{
            "credentialProviderType": "GATEWAY_IAM_ROLE", "credentialProvider": {"iamCredentialProvider": {"service": "execute-api", "region": s.region}}}])
        url = r["gatewayUrl"].removesuffix("/mcp") + "/http-test/echo"
        response = requests.get(url, headers=s.signed_headers(url), timeout=30)
        assert response.status_code == 200, {"status": response.status_code, "body": response.text}
        assert response.json()["message"] == "echo-ok"
        return {"gatewayWithoutProtocolType": True, "status": response.status_code, "body": response.json()}
    finally:
        s.state["gateway"] = old
        s.save()


def caller(s):
    from gateway_tests import openapi
    target(s, "caller-iam", {"mcp": {"openApiSchema": {"inlinePayload": json.dumps(openapi(s))}}}, [{
        "credentialProviderType": "CALLER_IAM_CREDENTIALS",
        "credentialProvider": {"iamCredentialProvider": {"service": "execute-api", "region": s.region}}}])
    return call(s, "caller-iam___get_echo", {}, "echo-ok")


def jwt_config(s):
    discovery = "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"
    response = requests.get(discovery, timeout=30)
    assert response.status_code == 200, response.status_code
    r = s.control.create_gateway(name=s.name + "-jwt-public", roleArn=s.state["agentcore_role"], protocolType="MCP",
        authorizerType="CUSTOM_JWT", authorizerConfiguration={"customJWTAuthorizer": {
            "discoveryUrl": discovery, "allowedAudience": ["cn-test"], "allowedClients": ["cn-test"], "allowedScopes": ["test"]}})
    s.resource("gateway", r["gatewayId"])
    s.wait(lambda: s.control.get_gateway(gatewayIdentifier=r["gatewayId"]))
    rejected = s.mcp("tools/list", {}, gateway=r, token="synthetic.invalid.jwt")
    assert rejected["status"] in (401, 403), rejected
    return {"configurationReady": True, "invalidTokenRejected": rejected["status"], "discoveryProvider": "Microsoft public OIDC metadata"}


def oauth_config(s):
    from suite import RESULTS
    secret = json.loads((RESULTS / f"{s.region}-secrets.json").read_text())["test_secret"]
    r = s.control.create_oauth2_credential_provider(name=s.name + "-oauth", credentialProviderVendor="CustomOauth2",
        oauth2ProviderConfigInput={"customOauth2ProviderConfig": {"clientId": "cn-test", "clientSecret": secret,
            "oauthDiscovery": {"authorizationServerMetadata": {"issuer": s.state["api_url"],
                "authorizationEndpoint": s.state["api_url"] + "/authorize", "tokenEndpoint": s.state["api_url"] + "/token",
                "responseTypes": ["code"], "tokenEndpointAuthMethods": ["client_secret_basic", "client_secret_post"]}}}})
    s.resource("oauth-provider", s.name + "-oauth")
    provider_permission(s, r)
    return {"credentialProviderArn": r["credentialProviderArn"], "scope": "control plane configuration only"}
