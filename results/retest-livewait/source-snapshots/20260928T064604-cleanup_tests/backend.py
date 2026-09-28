"""Temporary synthetic backend. Never returns or logs received credentials."""
import json
import os
import base64
import urllib.parse

HTML = """<!doctype html><html><head><title>AgentCore China feature test</title></head>
<body><h1>AgentCore China feature test</h1>
<input id="name" placeholder="Name"><button id="submit" onclick="document.querySelector('#result').textContent='Hello '+document.querySelector('#name').value">Submit</button>
<p id="result"></p><input id="upload" type="file"><p id="file"></p>
<a id="download" download="agentcore-test.txt" href="data:text/plain,agentcore-download-ok">Download</a>
<script>document.querySelector('#upload').onchange=e=>document.querySelector('#file').textContent=e.target.files[0].name;</script>
<div style="height:1800px">Scroll test</div><p id="bottom">Bottom</p></body></html>"""


def handler(event, context):
    if "interceptorInputVersion" in event or "mcp" in event:
        mcp = event.get("mcp", {})
        if mcp.get("gatewayResponse"):
            response = mcp["gatewayResponse"]
            payload = response["body"]
            if "result" in payload:
                payload["result"].setdefault("_meta", {})["cn_interceptor"] = "response-ok"
            return {"interceptorOutputVersion": "1.0", "mcp": {"transformedGatewayResponse": {
                "statusCode": response.get("statusCode", 200), "body": payload}}}
        req = mcp.get("gatewayRequest", {})
        payload = req["body"]
        if payload.get("method") == "tools/call" and payload["params"]["name"].endswith("___add"):
            payload["params"]["arguments"]["a"] += 1
        return {"interceptorOutputVersion": "1.0", "mcp": {"transformedGatewayRequest": {"body": payload}}}
    if "httpMethod" not in event:
        name = getattr(context, "client_context", None)
        custom = getattr(name, "custom", {}) or {}
        tool = custom.get("bedrockAgentCoreToolName", "")
        if event.get("fail"):
            raise ValueError("deliberate-synthetic-error")
        return {"sum": event.get("a", 0) + event.get("b", 0), "echo": event.get("text", ""),
                "region": os.environ["AWS_REGION"], "tool": tool}
    path = event.get("path", "")
    query = event.get("queryStringParameters") or {}
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    issuer = os.environ.get("OIDC_ISSUER") or ("https://" + headers.get("host", "") + "/" + event["requestContext"]["stage"])

    def response(data, status=200, content_type="application/json", extra=None):
        return {"statusCode": status, "headers": {"Content-Type": content_type, **(extra or {})},
                "body": json.dumps(data) if content_type == "application/json" else data}
    if path.endswith("/.well-known/openid-configuration"):
        return response({"issuer": issuer, "jwks_uri": os.environ.get("JWKS_URL", issuer + "/jwks"), "authorization_endpoint": issuer + "/authorize",
                         "token_endpoint": os.environ.get("TOKEN_URL", issuer + "/token"), "response_types_supported": ["code"],
                         "subject_types_supported": ["public"], "id_token_signing_alg_values_supported": ["RS256"],
                         "grant_types_supported": ["client_credentials", "authorization_code"],
                         "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"]})
    if path.endswith("/jwks"):
        return response({"keys": [json.loads(os.environ["JWK"])]})
    if path.endswith("/token"):
        fields = urllib.parse.parse_qs(body)
        good = fields.get("client_secret", [None])[0] == os.environ["TEST_SECRET"]
        expected = "Basic " + base64.b64encode(("cn-test:" + os.environ["TEST_SECRET"]).encode()).decode()
        if not good and headers.get("authorization") != expected:
            return response({"error": "invalid_client"}, 401)
        return response({"access_token": os.environ["TEST_SECRET"], "token_type": "Bearer", "expires_in": 3600, "scope": "test"})
    if path.endswith("/page"):
        return response(HTML, content_type="text/html")
    if path.endswith("/mcp"):
        if event["httpMethod"] == "GET":
            return response({}, 405)
        req = json.loads(body or "{}")
        print(json.dumps({"cnMcpDebug": True, "keys": list(req), "method": req.get("method"),
                          "paramKeys": list(req.get("params", {})), "name": req.get("params", {}).get("name"),
                          "version": headers.get("mcp-protocol-version")}))
        method = req.get("method", "")
        args = req.get("params", {})
        if "id" not in req:
            return response({}, 202)
        if method == "initialize":
            result = {"protocolVersion": args.get("protocolVersion", "2025-03-26"),
                      "capabilities": {"tools": {"listChanged": True}, "prompts": {}, "resources": {}},
                      "serverInfo": {"name": "cn-synthetic-mcp", "version": "1.0"}}
        elif method == "server/discover":
            result = {"resultType": "complete", "supportedVersions": ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26"],
                      "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "cn-synthetic-mcp", "version": "1.0"}},
                      "capabilities": {"tools": {}, "prompts": {}, "resources": {}}}
        elif method == "tools/list":
            result = {"tools": [{"name": n, "description": "Synthetic test " + n,
                                "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}
                               for n in ["echo", "progress", "elicit", "sample"]]}
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": "mcp-echo:" + args.get("arguments", {}).get("text", "")}], "isError": False}
            name = args.get("name")
            if name == "progress":
                events = [{"jsonrpc": "2.0", "method": "notifications/progress", "params": {
                    "progressToken": args.get("_meta", {}).get("progressToken", "progress-test"), "progress": x, "total": 2}} for x in [1, 2]]
                events.append({"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info", "data": "synthetic-log-ok"}})
                events.append({"jsonrpc": "2.0", "id": req["id"], "result": result})
                return response("".join("event: message\ndata: " + json.dumps(x) + "\n\n" for x in events), content_type="text/event-stream")
            if name in ["elicit", "sample"]:
                if args.get("inputResponses"):
                    result = {"content": [{"type": "text", "text": "roundtrip-ok:" + json.dumps(args["inputResponses"])}], "isError": False}
                else:
                    request = {"method": "elicitation/create", "params": {"mode": "form", "message": "Confirm synthetic test",
                        "requestedSchema": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": ["confirm"]}}}
                    if name == "sample":
                        request = {"method": "sampling/createMessage", "params": {"messages": [
                            {"role": "user", "content": {"type": "text", "text": "Reply test-ok"}}], "maxTokens": 20}}
                    result = {"resultType": "input_required", "inputRequests": {"cn-input": request}, "requestState": "synthetic-state"}
        elif method == "prompts/list":
            result = {"prompts": [{"name": "hello", "description": "Synthetic prompt", "arguments": [{"name": "name", "required": True}]}]}
        elif method == "prompts/get":
            result = {"messages": [{"role": "user", "content": {"type": "text", "text": "Hello " + args.get("arguments", {}).get("name", "")}}]}
        elif method == "resources/list":
            result = {"resources": [{"uri": "test://china/info", "name": "China info", "mimeType": "text/plain"}]}
        elif method == "resources/read":
            result = {"contents": [{"uri": args["uri"], "mimeType": "text/plain", "text": "china-resource-ok"}]}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": [{"uriTemplate": "test://china/{name}", "name": "Named info"}]}
        else:
            result = {}
        if headers.get("mcp-protocol-version") == "2026-07-28":
            result.setdefault("resultType", "complete")
        return response({"jsonrpc": "2.0", "id": req["id"], "result": result})
    if path.endswith("/secure"):
        authenticated = (headers.get("x-test-key") == os.environ["TEST_SECRET"] or
                         query.get("test_key") == os.environ["TEST_SECRET"] or
                         headers.get("authorization") == "Bearer " + os.environ["TEST_SECRET"])
        if not authenticated:
            return response({"error": "unauthorized"}, 401)
        return response({"authenticated": True, "region": os.environ["AWS_REGION"]})
    return response({"message": query.get("message", "echo-ok"), "path": path,
                     "region": os.environ["AWS_REGION"],
                     "forwardedHeader": headers.get("x-cn-test", ""),
                     "forwardedQuery": query.get("cn_test", "")}, extra={"x-cn-result": "header-ok"})
