import json
import secrets
import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials


def run(s):
    temp = s.client("sts").get_session_token(DurationSeconds=900)["Credentials"]
    session = boto3.Session(aws_access_key_id=temp["AccessKeyId"], aws_secret_access_key=temp["SecretAccessKey"],
                            aws_session_token=temp["SessionToken"], region_name=s.region)
    identity = session.client("sts").get_caller_identity()
    assert identity["Account"] == s.account
    runtime = session.client("bedrock-agentcore")
    def direct():
        sid = secrets.token_hex(20)
        s.state.setdefault("runtime_sessions", []).append(sid)
        s.save()
        r = runtime.invoke_agent_runtime(agentRuntimeArn=s.state["runtime_arn"], runtimeSessionId=sid,
            payload=json.dumps({"a": 20, "b": 22}).encode(), contentType="application/json")
        data = json.loads(r["response"].read())
        assert data["sum"] == 42, data
        return {"temporaryCredentialsValid": True, "body": data, "requestId": r["ResponseMetadata"]["RequestId"]}
    s.test("gateway.outbound.caller_iam.direct_runtime_baseline", direct)
    http_id = next(x["id"] for x in s.state["resources"] if x["kind"] == "gateway" and x["id"].startswith(s.name + "-http"))
    gw = s.control.get_gateway(gatewayIdentifier=http_id)
    for name in ["runtime-role", "runtime-caller"]:
        def invoke(n=name):
            sid = secrets.token_hex(20)
            s.state.setdefault("runtime_sessions", []).append(sid)
            s.save()
            url = gw["gatewayUrl"].removesuffix("/mcp") + "/" + n + "/invocations"
            body = json.dumps({"a": 20, "b": 22})
            req = AWSRequest(method="POST", url=url, data=body, headers={"Content-Type": "application/json",
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": sid})
            SigV4Auth(Credentials(temp["AccessKeyId"], temp["SecretAccessKey"], temp["SessionToken"]), "bedrock-agentcore", s.region).add_auth(req)
            r = requests.post(url, data=body, headers=dict(req.headers), timeout=120)
            result = {"status": r.status_code, "body": r.text, "requestId": r.headers.get("x-amzn-requestid")}
            assert r.status_code == 200, result
            assert r.json()["sum"] == 42
            return result
        s.test("gateway.outbound.caller_iam" if name == "runtime-caller" else "gateway.outbound.caller_iam.gateway_role_baseline", invoke)
