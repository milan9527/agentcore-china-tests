"""End-to-end Gateway outbound OAuth checks, including service account gates."""
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urljoin, urlsplit

from botocore.exceptions import ClientError
import requests
from gateway_tests import openapi, target
from retest_gateway import gw, jwt_config, keys, user_token
from suite import RESULTS

EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
JWT_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "cn-oauth-validation", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"url": {}}}}


def events(s):
    path = RESULTS / f"{s.region}-issuer-events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def body(result):
    return result["body"][-1] if isinstance(result["body"], list) else result["body"]


def invoke(s, label, token, **extra):
    name = label + "___secure"
    return s.mcp("tools/call", {"name": name, "arguments": {}, "_meta": META, **extra},
        token=token, version="2026-07-28", extra_headers={"Mcp-Method": "tools/call", "Mcp-Name": name})


def confirm(s, result, grant, since, inbound):
    s.require_mcp(result)
    result_body = body(result)["result"]
    backend = json.loads(next(x["text"] for x in result_body["content"] if x["type"] == "text"))
    assert backend["authenticated"] and backend["grant"] == grant, result
    assert backend["tokenSha256"] != hashlib.sha256(inbound.encode()).hexdigest(), "Unexpected token passthrough"
    matched = [e for e in events(s)[since:] if e.get("tokenSha256") == backend["tokenSha256"]]
    issued = [e for e in matched if e["endpoint"] == "/token" and e["status"] == 200]
    used = [e for e in matched if e["endpoint"] == "/secure" and e["status"] == 200]
    assert issued and used, {"issued": issued, "used": used}
    return {"gatewayResponse": result, "backend": backend,
            "issuerIssuance": issued, "issuerUsage": used, "outboundTokenDiffersFromInbound": True}


def provider(s, label, authentication="CLIENT_SECRET_BASIC", obo=None):
    sec, _ = keys(s)
    name = s.name + "-" + label
    config = {"clientId": "cn-retest", "clientSecret": sec["clientSecret"],
        "clientAuthenticationMethod": authentication,
        "oauthDiscovery": {"discoveryUrl": s.state["issuer"] + "/.well-known/openid-configuration"}}
    if obo:
        config["onBehalfOfTokenExchangeConfig"] = obo
    created = s.control.create_oauth2_credential_provider(name=name,
        credentialProviderVendor="CustomOauth2",
        oauth2ProviderConfigInput={"customOauth2ProviderConfig": config})
    s.resource("oauth-provider", name)
    fetched = s.control.get_oauth2_credential_provider(name=name)
    s.record("gateway.oauth.provider." + label, "PASS", {
        "create": created, "get": fetched, "requestedClientAuthentication": authentication,
        "requestedOboConfiguration": obo})
    return fetched["credentialProviderArn"]


def configure_target(s, label, arn, grant):
    credentials = {"providerArn": arn, "scopes": ["test"], "grantType": grant}
    if grant == "AUTHORIZATION_CODE":
        credentials["defaultReturnUrl"] = s.state["issuer"] + "/callback"
    return target(s, label, {"mcp": {"openApiSchema": {
        "inlinePayload": json.dumps(openapi(s, path="/secure", name="secure"))}}},
        [{"credentialProviderType": "OAUTH",
          "credentialProvider": {"oauthCredentialProvider": credentials}}])


def fixture_baselines(s):
    sec, _ = keys(s)
    issuer = s.state["issuer"]
    denied = requests.get(issuer + "/secure", timeout=30)
    assert denied.status_code == 401, denied.status_code
    bad = requests.post(issuer + "/token", auth=("cn-retest", "invalid-secret"),
                        data={"grant_type": "client_credentials"}, timeout=30)
    assert bad.status_code == 401 and bad.json()["error"] == "invalid_client", bad.status_code
    inbound = user_token(s, sub="direct-obo-baseline")
    flows = {}
    for grant in (EXCHANGE, JWT_GRANT):
        form = {"grant_type": grant, "scope": "test"}
        form.update({"subject_token": inbound,
                     "subject_token_type": "urn:ietf:params:oauth:token-type:jwt"}
                    if grant == EXCHANGE else {"assertion": inbound})
        response = requests.post(issuer + "/token", auth=("cn-retest", sec["clientSecret"]),
                                 data=form, timeout=30)
        assert response.status_code == 200, response.text
        secure = requests.get(issuer + "/secure",
            headers={"Authorization": "Bearer " + response.json()["access_token"]}, timeout=30)
        assert secure.status_code == 200, secure.text
        assert secure.json()["sub"] == "direct-obo-baseline" and secure.json()["grant"] == grant, secure.text
        flows[grant] = secure.json()
    return {"unauthenticatedBackendStatus": denied.status_code,
            "badClientSecretStatus": bad.status_code, "directIdpOboBaselines": flows,
            "scope": "IdP direct baselines; these are not Gateway OBO success"}


def two_legged(s, authentication):
    label = "cc-" + ("basic" if authentication == "CLIENT_SECRET_BASIC" else "post")
    arn = provider(s, label, authentication)
    configured = configure_target(s, label, arn, "CLIENT_CREDENTIALS")
    start = len(events(s))
    inbound = user_token(s, sub="two-legged-caller")
    result = invoke(s, label, inbound)
    proof = confirm(s, result, "client_credentials", start, inbound)
    assert all(e["clientAuthentication"] == authentication for e in proof["issuerIssuance"]), proof
    assert proof["backend"]["sub"] == "synthetic-service", proof
    before_repeat = len(events(s))
    repeated = invoke(s, label, inbound)
    s.require_mcp(repeated, "client_credentials")
    return {**proof, "targetId": configured["targetId"], "repeatCall": repeated,
        "repeatTokenEndpointRequests": sum(e["endpoint"] == "/token" for e in events(s)[before_repeat:])}


def three_legged(s):
    label = "authorization-code"
    arn = provider(s, label)
    configure_target(s, label, arn, "AUTHORIZATION_CODE")
    gateway = s.state["gateway"]
    workload = gateway["workloadIdentityDetails"]["workloadIdentityArn"].rsplit("/", 1)[-1]
    s.control.update_workload_identity(name=workload,
        allowedResourceOauth2ReturnUrls=[s.state["issuer"] + "/callback"])
    inbound = user_token(s, sub="three-legged-" + secrets.token_hex(6))
    start = len(events(s))
    initial = invoke(s, label, inbound)
    s.require_mcp(initial)
    requested = body(initial)["result"]
    assert requested["resultType"] == "input_required", initial
    assert not any(e["endpoint"] == "/secure" for e in events(s)[start:])
    s.record("gateway.oauth.3lo.consent_required", "PASS", initial)
    url = requested["inputRequests"]["urlElicitation"]["params"]["url"]
    allowed = {urlsplit(s.state["issuer"]).hostname,
               f"bedrock-agentcore.{s.region}.amazonaws.com.cn"}
    redirects = []
    with requests.Session() as http:
        for _ in range(8):
            parsed = urlsplit(url)
            assert parsed.scheme == "https" and parsed.hostname in allowed
            response = http.get(url, allow_redirects=False, timeout=45)
            redirects.append({"host": parsed.hostname, "path": parsed.path, "status": response.status_code})
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
            else:
                break
    assert response.status_code == 200 and urlsplit(url).path.endswith("/callback"), redirects
    query = parse_qs(urlsplit(url).query)
    session_uri = next((v[0] for k, v in query.items() if k.lower().replace("_", "") == "sessionuri"), None)
    if not session_uri and query.get("session_id"):
        session_uri = query["session_id"][0]
        if not session_uri.startswith("urn:"):
            session_uri = "urn:ietf:params:oauth:request_uri:" + session_uri
    assert session_uri, {"callbackQueryKeys": list(query)}
    bound = s.runtime.complete_resource_token_auth(userIdentifier={"userToken": inbound}, sessionUri=session_uri)
    s.record("gateway.oauth.3lo.session_binding", "PASS", {"redirects": redirects, "binding": bound})
    extra = {"inputResponses": {k: {"action": "accept"} for k in requested["inputRequests"]}}
    if "requestState" in requested:
        extra["requestState"] = requested["requestState"]
    resumed = invoke(s, label, inbound, **extra)
    proof = confirm(s, resumed, "authorization_code", start, inbound)
    assert body(resumed)["result"]["resultType"] == "complete", resumed
    before_repeat = len(events(s))
    repeated = invoke(s, label, inbound)
    s.require_mcp(repeated, "authorization_code")
    assert body(repeated)["result"].get("resultType") != "input_required", repeated
    s.record("gateway.oauth.3lo.cached_user", "PASS", {"response": repeated,
        "repeatTokenEndpointRequests": sum(e["endpoint"] == "/token" for e in events(s)[before_repeat:])})
    before_other = len(events(s))
    other = invoke(s, label, user_token(s, sub="different-user-" + secrets.token_hex(6)))
    s.require_mcp(other)
    assert body(other)["result"]["resultType"] == "input_required", other
    assert not any(e["endpoint"] == "/secure" for e in events(s)[before_other:])
    s.record("gateway.oauth.3lo.user_isolation", "PASS",
             {"otherUserConsentRequired": True, "otherUserReachedBackend": False, "response": other})
    return {**proof, "redirects": redirects, "sessionBinding": bound}


def on_behalf_of(s, label, config):
    feature = "gateway.oauth.obo." + label
    arn = provider(s, label, obo=config)
    start = len(events(s))
    rejections = []
    for attempt in range(2):
        try:
            configured = configure_target(s, label + "-" + str(attempt + 1), arn, "TOKEN_EXCHANGE")
        except ClientError as error:
            if "Token Exchange is not available for this account" not in error.response["Error"]["Message"]:
                raise
            rejections.append({"attempt": attempt + 1, "response": error.response})
            s.record(feature + ".attempt_" + str(attempt + 1), "INFO", error.response)
        else:
            inbound = user_token(s, sub="gateway-obo-subject")
            result = invoke(s, label + "-" + str(attempt + 1), inbound)
            proof = confirm(s, result, EXCHANGE if config["grantType"] == "TOKEN_EXCHANGE"
                            else JWT_GRANT, start, inbound)
            assert proof["backend"]["sub"] == "gateway-obo-subject", proof
            s.record(feature, "PASS", {**proof, "targetId": configured["targetId"]})
            return
    token_requests = [e for e in events(s)[start:] if e["endpoint"] == "/token"]
    assert len(rejections) == 2 and not token_requests
    s.record(feature, "BLOCKED", {
        "scope": "Current account and region; Gateway target creation is account-gated",
        "providerArn": arn, "providerConfiguration": config, "rejections": rejections,
        "gatewayTokenEndpointRequests": len(token_requests), "endToEndInvocationExecuted": False})


def run(s):
    s.test("oauth.fixture.baselines", lambda: fixture_baselines(s))
    gateway = gw(s, "jwt", auth="CUSTOM_JWT", authorizerConfiguration=jwt_config(s),
        protocolConfiguration={"mcp": {"supportedVersions": ["2025-03-26", "2025-11-25", "2026-07-28"],
            "sessionConfiguration": {"sessionTimeoutInSeconds": 900},
            "streamingConfiguration": {"enableResponseStreaming": True}}})
    s.record("gateway.oauth.gateway_ready", "PASS", gateway)
    for authentication in ("CLIENT_SECRET_BASIC", "CLIENT_SECRET_POST"):
        s.test("gateway.oauth.2lo." + authentication.lower(), lambda auth=authentication: two_legged(s, auth))
    s.test("gateway.oauth.3lo.authorization_code", lambda: three_legged(s))
    variants = {f"rfc8693-{actor.lower().replace('_', '-')}": {
        "grantType": "TOKEN_EXCHANGE", "tokenExchangeGrantTypeConfig": {
            "actorTokenContent": actor, **({"actorTokenScopes": ["test"]} if actor == "M2M" else {})}}
        for actor in ("NONE", "M2M", "AWS_IAM_ID_TOKEN_JWT")}
    variants["rfc7523-jwt-bearer"] = {"grantType": "JWT_AUTHORIZATION_GRANT"}
    for label, config in variants.items():
        s.test("gateway.oauth.obo_configuration_check." + label,
               lambda lab=label, conf=config: on_behalf_of(s, lab, conf))
