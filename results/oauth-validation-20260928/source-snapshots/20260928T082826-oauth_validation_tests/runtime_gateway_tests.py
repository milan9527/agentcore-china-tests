import io
import json
import secrets
import zipfile
import requests
from gateway_tests import target

CODE = '''from http.server import BaseHTTPRequestHandler,HTTPServer
import json,os
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{"status":"Healthy"}')
 def do_POST(self):
  obj=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b'{}')
  body=json.dumps({"sum":obj.get("a",0)+obj.get("b",0),"runtime":"gateway-fixture","region":os.environ.get("AWS_REGION")}).encode()
  self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
HTTPServer(("0.0.0.0",8080),Handler).serve_forever()
'''


def run(s):
    c = s.control
    if "runtime_arn" not in s.state:
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("app.py", CODE)
        s.client("s3").put_object(Bucket=s.state["bucket"], Key="runtime.zip", Body=z.getvalue(), ContentType="application/zip")
        r = s.test("gateway.runtime.fixture_create", lambda: c.create_agent_runtime(agentRuntimeName=s.name.replace("-", "_"),
            agentRuntimeArtifact={"codeConfiguration": {"code": {"s3": {"bucket": s.state["bucket"], "prefix": "runtime.zip"}},
                "runtime": "PYTHON_3_12", "entryPoint": ["app.py"]}},
            roleArn=s.state["agentcore_role"], networkConfiguration={"networkMode": "PUBLIC"},
            protocolConfiguration={"serverProtocol": "HTTP"}, tags={"Purpose": s.name}))
        if not r:
            return
        s.state["runtime_arn"] = r["agentRuntimeArn"]
        s.state["runtime_id"] = r["agentRuntimeId"]
        s.resource("runtime", r["agentRuntimeId"])
    ready = s.test("gateway.runtime.fixture_ready", lambda: s.wait(lambda: c.get_agent_runtime(agentRuntimeId=s.state["runtime_id"]), timeout=600))
    if not ready:
        return
    s.client("iam").put_role_policy(RoleName=s.name + "-agentcore", PolicyName="invoke-runtime", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
            "Resource": [s.state["runtime_arn"], s.state["runtime_arn"] + "/*"]}]}))
    http_id = next(x["id"] for x in s.state["resources"] if x["kind"] == "gateway" and x["id"].startswith(s.name + "-http"))
    gw = c.get_gateway(gatewayIdentifier=http_id)
    old = s.state["gateway"]
    try:
        s.state["gateway"] = gw
        for credential, name in [("GATEWAY_IAM_ROLE", "runtime-role"), ("CALLER_IAM_CREDENTIALS", "runtime-caller")]:
            t = s.test("gateway.runtime." + name + ".target", lambda cr=credential, n=name: target(s, n,
                {"http": {"agentcoreRuntime": {"arn": s.state["runtime_arn"], "qualifier": "DEFAULT"}}},
                [{"credentialProviderType": cr}]))
            if not t:
                continue
            def invoke(n=name):
                url = gw["gatewayUrl"].removesuffix("/mcp") + "/" + n + "/invocations"
                body = json.dumps({"a": 20, "b": 22})
                session_id = secrets.token_hex(20)
                s.state.setdefault("runtime_sessions", []).append(session_id)
                s.save()
                headers = {"Content-Type": "application/json", "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id}
                if n == "runtime-caller":
                    from botocore.auth import SigV4Auth
                    from botocore.awsrequest import AWSRequest
                    from botocore.credentials import Credentials
                    temp = s.client("sts").get_session_token(DurationSeconds=900)["Credentials"]
                    creds = Credentials(temp["AccessKeyId"], temp["SecretAccessKey"], temp["SessionToken"])
                    request = AWSRequest(method="POST", url=url, data=body, headers=headers)
                    SigV4Auth(creds, "bedrock-agentcore", s.region).add_auth(request)
                    signed_headers = dict(request.headers)
                else:
                    signed_headers = s.signed_headers(url, "POST", body, headers=headers)
                r = requests.post(url, data=body, headers=signed_headers, timeout=120)
                assert r.status_code == 200, {"status": r.status_code, "body": r.text[:1500]}
                assert r.json()["sum"] == 42, r.text
                return {"status": r.status_code, "body": r.json()}
            s.test("gateway.outbound.caller_iam" if credential == "CALLER_IAM_CREDENTIALS" else "gateway.runtime.role_invocation", invoke)
    finally:
        s.state["gateway"] = old
        s.save()
