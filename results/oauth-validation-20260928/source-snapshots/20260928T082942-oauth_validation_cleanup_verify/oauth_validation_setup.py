"""Create only the IAM role and synthetic key material needed by OAuth validation."""
import json
import secrets
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from suite import RESULTS


def run(s):
    iam = s.client("iam")
    name = s.name + "-agentcore"
    role = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    }), Tags=[{"Key": "Purpose", "Value": s.name}])
    s.state["agentcore_role"] = role["Role"]["Arn"]
    s.resource("role", name)
    iam.put_role_policy(RoleName=name, PolicyName="synthetic-oauth", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": [
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                "bedrock-agentcore:GetResourceOauth2Token"],
             "Resource": f"arn:aws-cn:bedrock-agentcore:{s.region}:{s.account}:*"},
            {"Effect": "Allow", "Action": "secretsmanager:GetSecretValue",
             "Resource": f"arn:aws-cn:secretsmanager:{s.region}:{s.account}:secret:bedrock-agentcore-identity!*{s.name}*"}
        ]}))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    files = {
        "private-key.pem": key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        "secrets.json": json.dumps({"clientSecret": secrets.token_hex(24),
                                   "pathKey": secrets.token_hex(16)}).encode()
    }
    for suffix, data in files.items():
        path = RESULTS / f"{s.region}-{suffix}"
        path.touch(mode=0o600, exist_ok=False)
        path.write_bytes(data)
    s.record("oauth.environment", "PASS", {
        "profile": "china", "account": s.account, "region": s.region,
        "caller": s.client("sts").get_caller_identity(),
        "controlEndpoint": s.control.meta.endpoint_url, "syntheticIdentitiesOnly": True})
    time.sleep(10)
