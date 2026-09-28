"""Live AgentCore China tests. State and evidence are persisted after each operation."""
import argparse
import base64
import concurrent.futures
import datetime as dt
import io
import json
import os
from pathlib import Path
import secrets
import time
import traceback
import zipfile

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.exceptions import ClientError
import requests
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
REGIONS = ["cn-north-1", "cn-northwest-1"]


def serial(value):
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    return str(value)


class Suite:
    def __init__(self, region, profile="china"):
        self.region = region
        self.session = boto3.Session(profile_name=profile, region_name=region)
        self.config = Config(connect_timeout=10, read_timeout=90, retries={"max_attempts": 2})
        self.clients = {}
        self.state_path = RESULTS / f"{region}-state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {
            "run": "ac-cn-" + dt.datetime.now(dt.timezone.utc).strftime("%m%d%H%M%S"),
            "region": region, "resources": [], "sessions": []}
        self.name = self.state["run"] + ("-bj" if region == REGIONS[0] else "-nx")
        self.control = self.client("bedrock-agentcore-control")
        self.runtime = self.client("bedrock-agentcore")
        self.account = self.client("sts").get_caller_identity()["Account"]
        self.save()

    def client(self, service):
        if service not in self.clients:
            self.clients[service] = self.session.client(service, config=self.config)
        return self.clients[service]

    def save(self):
        self.state_path.write_text(json.dumps(self.state, indent=2, default=serial))

    def resource(self, kind, identifier, **more):
        self.state["resources"].append({"kind": kind, "id": identifier, **more})
        self.save()

    def record(self, feature, status, evidence=None, started=None):
        row = {"time": dt.datetime.now(dt.timezone.utc).isoformat(), "region": self.region,
               "feature": feature, "status": status, "evidence": evidence}
        if started:
            row["seconds"] = round(time.monotonic() - started, 3)
        with (RESULTS / f"{self.region}-results.jsonl").open("a") as f:
            f.write(json.dumps(row, default=serial) + "\n")
        print(f"[{self.region}] {status}: {feature}" + (f" — {str(evidence)[:500]}" if status != "PASS" else ""), flush=True)
        return evidence

    def test(self, feature, fn):
        started = time.monotonic()
        try:
            result = fn()
            self.record(feature, "PASS", result, started)
            return result
        except Exception as e:
            evidence = {"type": type(e).__name__, "message": str(e)}
            if isinstance(e, ClientError):
                evidence["response"] = e.response
            else:
                evidence["traceback"] = traceback.format_exc()
            self.record(feature, "FAIL", evidence, started)
            return None

    def wait(self, getter, ready=("READY", "ACTIVE", "AVAILABLE"), timeout=180):
        deadline = time.monotonic() + timeout
        while True:
            r = getter()
            status = r.get("status", r.get("Status", r.get("State")))
            if status in ready:
                return r
            if status in ["FAILED", "CREATE_FAILED", "UPDATE_FAILED"]:
                raise RuntimeError(json.dumps(r, default=serial))
            if time.monotonic() > deadline:
                raise TimeoutError(json.dumps(r, default=serial))
            time.sleep(3)

    def signed_headers(self, url, method="GET", body=None, service="bedrock-agentcore", headers=None):
        req = AWSRequest(method=method, url=url.replace("wss://", "https://"), data=body, headers=headers or {})
        SigV4Auth(self.session.get_credentials().get_frozen_credentials(), service, self.region).add_auth(req)
        return dict(req.headers)

    def mcp(self, method, params=None, gateway=None, token=None, version="2025-03-26", extra_headers=None):
        gateway = gateway or self.state["gateway"]
        payload = {"jsonrpc": "2.0", "id": secrets.randbelow(1000000), "method": method}
        if method.startswith("notifications/"):
            payload.pop("id")
        if params is not None:
            payload["params"] = params
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": version, **(extra_headers or {})}
        if token:
            headers["Authorization"] = "Bearer " + token
        else:
            headers = self.signed_headers(gateway["gatewayUrl"], "POST", body, headers=headers)
        r = requests.post(gateway["gatewayUrl"], data=body, headers=headers, timeout=90)
        try:
            data = r.json()
        except ValueError:
            data = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
        return {"status": r.status_code, "headers": {k.lower(): v for k, v in r.headers.items()
                if k.lower() in ["mcp-session-id", "content-type", "x-amzn-requestid", "x-cn-test-interceptor"]}, "body": data}

    @staticmethod
    def require_mcp(result, contains=None, error=False):
        assert result["status"] == 200, result
        body = result["body"]
        if isinstance(body, list):
            body = body[-1]
        if not error:
            assert "error" not in body, result
            assert not body.get("result", {}).get("isError"), result
        if contains:
            assert contains in json.dumps(body), result
        return result

    def setup(self):
        iam = self.client("iam")
        for label, principals in [("lambda", ["lambda.amazonaws.com"]),
                                  ("agentcore", ["bedrock-agentcore.amazonaws.com"])]:
            if label + "_role" in self.state:
                continue
            name = self.name + "-" + label
            trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": principals},
                                                          "Action": "sts:AssumeRole"}]}
            r = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust), Tags=[{"Key": "Purpose", "Value": self.name}])
            self.resource("role", name)
            self.state[label + "_role"] = r["Role"]["Arn"]
            self.save()
        bucket = self.name + "-" + self.account
        if "bucket" not in self.state:
            self.client("s3").create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": self.region})
            self.resource("bucket", bucket)
            self.state["bucket"] = bucket
            self.save()
            self.client("s3").put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
                "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
            self.client("s3").put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": "Purpose", "Value": self.name}]})
        policy = {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
             "Resource": [f"arn:aws-cn:s3:::{bucket}", f"arn:aws-cn:s3:::{bucket}/*"]},
            {"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": f"arn:aws-cn:lambda:{self.region}:{self.account}:function:{self.name}*"},
            {"Effect": "Allow", "Action": ["execute-api:Invoke"], "Resource": f"arn:aws-cn:execute-api:{self.region}:{self.account}:*"},
            {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
             "Resource": [f"arn:aws-cn:logs:{self.region}:{self.account}:log-group:/aws/lambda/{self.name}*",
                          f"arn:aws-cn:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/*"]},
            {"Effect": "Allow", "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces",
                                          "ec2:DeleteNetworkInterface", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"],
             "Resource": "*"},
            {"Effect": "Allow", "Action": ["bedrock-agentcore:GetResourceApiKey", "bedrock-agentcore:GetResourceOauth2Token",
                                          "bedrock-agentcore:GetWorkloadAccessToken"],
             "Resource": f"arn:aws-cn:bedrock-agentcore:{self.region}:{self.account}:*"},
            {"Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"],
             "Resource": f"arn:aws-cn:secretsmanager:{self.region}:{self.account}:secret:{self.name}*"}]}
        for label in ["lambda", "agentcore"]:
            iam.put_role_policy(RoleName=self.name + "-" + label, PolicyName="synthetic-test",
                                PolicyDocument=json.dumps(policy if label == "agentcore" else {
                                    "Version": "2012-10-17", "Statement": [policy["Statement"][3]]}))
        key_path = RESULTS / f"{self.region}-private-key.pem"
        secret_path = RESULTS / f"{self.region}-secrets.json"
        if not key_path.exists():
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
            os.chmod(key_path, 0o600)
            secret_path.write_text(json.dumps({"test_secret": secrets.token_urlsafe(32)}))
            os.chmod(secret_path, 0o600)
        key = serialization.load_pem_private_key(key_path.read_bytes(), None)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update(kid="cn-test", use="sig", alg="RS256")
        self.secret = json.loads(secret_path.read_text())["test_secret"]
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("backend.py", (ROOT / "backend.py").read_bytes())
        if "lambda_arn" not in self.state:
            time.sleep(10)
            r = self.client("lambda").create_function(FunctionName=self.name, Runtime="python3.12",
                Role=self.state["lambda_role"], Handler="backend.handler", Code={"ZipFile": z.getvalue()},
                Timeout=30, MemorySize=128, Environment={"Variables": {"JWK": json.dumps(jwk), "TEST_SECRET": self.secret}},
                Tags={"Purpose": self.name})
            self.resource("lambda", self.name)
            self.state["lambda_arn"] = r["FunctionArn"]
            self.save()
            self.client("lambda").get_waiter("function_active_v2").wait(FunctionName=self.name)
        if "api_id" not in self.state:
            api = self.client("apigateway")
            r = api.create_rest_api(name=self.name, endpointConfiguration={"types": ["REGIONAL"]}, tags={"Purpose": self.name})
            self.state["api_id"] = r["id"]
            self.resource("api", r["id"])
            root = api.get_resources(restApiId=r["id"])["items"][0]["id"]
            for path, methods in [("{proxy+}", ["ANY"]), ("echo", ["GET"]), ("secure", ["GET"]), ("iam", ["GET"])]:
                rid = api.create_resource(restApiId=r["id"], parentId=root, pathPart=path)["id"]
                for method in methods:
                    api.put_method(restApiId=r["id"], resourceId=rid, httpMethod=method,
                        authorizationType="AWS_IAM" if path == "iam" else "NONE", operationName="get_" + path.replace("{proxy+}", "proxy"))
                    api.put_integration(restApiId=r["id"], resourceId=rid, httpMethod=method, type="AWS_PROXY",
                        integrationHttpMethod="POST",
                        uri=f"arn:aws-cn:apigateway:{self.region}:lambda:path/2015-03-31/functions/{self.state['lambda_arn']}/invocations")
            self.client("lambda").add_permission(FunctionName=self.name, StatementId="api", Action="lambda:InvokeFunction",
                Principal="apigateway.amazonaws.com", SourceArn=f"arn:aws-cn:execute-api:{self.region}:{self.account}:{r['id']}/*")
            api.create_deployment(restApiId=r["id"], stageName="test")
            self.state["api_url"] = f"https://{r['id']}.execute-api.{self.region}.amazonaws.com.cn/test"
            self.save()
        r = requests.get(self.state["api_url"] + "/echo", timeout=30)
        assert r.status_code == 200, r.text
        return {"backend": r.json(), "bucket": bucket, "roles": "created with scoped test permissions"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase")
    p.add_argument("--region", choices=REGIONS)
    p.add_argument("--profile", default="china")
    args = p.parse_args()
    def run(region):
        s = Suite(region, args.profile)
        if hasattr(s, args.phase):
            s.test(args.phase, getattr(s, args.phase))
        else:
            import importlib
            module = importlib.import_module(args.phase + "_tests")
            s.test(args.phase + ".suite", lambda: module.run(s))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(run, [args.region] if args.region else REGIONS))


if __name__ == "__main__":
    main()
