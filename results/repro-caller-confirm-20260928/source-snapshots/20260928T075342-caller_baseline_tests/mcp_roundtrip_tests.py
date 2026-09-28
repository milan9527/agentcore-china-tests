from gateway_final_tests import deploy, config, VERSIONS, secured_schema
from gateway_tests import target, call


def run(s):
    deploy(s)
    config(s, protocolConfiguration={"mcp": {"supportedVersions": VERSIONS}})
    def api_key():
        _, args = secured_schema(s, "secure_key")
        return call(s, "api-key___secure_key", args, "true")
    s.test("gateway.outbound.api_key", api_key)
    signed = [{"credentialProviderType": "GATEWAY_IAM_ROLE",
               "credentialProvider": {"iamCredentialProvider": {"service": "execute-api", "region": s.region}}}]
    target(s, "mcp-roundtrip", {"mcp": {"mcpServer": {"endpoint": s.state["api_url"] + "/mcp", "listingMode": "DYNAMIC"}}}, signed)
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "cn-test", "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}, "url": {}}, "sampling": {}}}
    for tool in ["elicit", "sample"]:
        def mrtr(name=tool):
            params = {"name": "mcp-roundtrip___" + name, "arguments": {}, "_meta": meta}
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
