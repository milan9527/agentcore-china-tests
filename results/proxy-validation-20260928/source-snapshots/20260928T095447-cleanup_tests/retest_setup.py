import io
import json
import secrets
import time
import zipfile
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
from suite import ROOT, RESULTS


def run(s):
    iam = s.client("iam")
    for label, principal in [("lambda", "lambda.amazonaws.com"), ("agentcore", "bedrock-agentcore.amazonaws.com")]:
        if label + "_role" not in s.state:
            role = iam.create_role(RoleName=s.name + "-" + label, AssumeRolePolicyDocument=json.dumps({
                "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": principal},
                                                      "Action": "sts:AssumeRole"}]}), Tags=[{"Key": "Purpose", "Value": s.name}])
            s.state[label + "_role"] = role["Role"]["Arn"]
            s.resource("role", s.name + "-" + label)
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": f"arn:aws-cn:logs:{s.region}:{s.account}:log-group:/aws/lambda/{s.name}*"}]}
    iam.put_role_policy(RoleName=s.name+"-lambda", PolicyName="synthetic-test", PolicyDocument=json.dumps(policy))
    if "bucket" not in s.state:
        bucket = s.name + "-" + s.account
        s.client("s3").create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": s.region})
        s.state["bucket"] = bucket
        s.resource("bucket", bucket)
        s.client("s3").put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    resources = f"arn:aws-cn:bedrock-agentcore:{s.region}:{s.account}:*"
    statements = [
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
         "Resource": [f"arn:aws-cn:s3:::{s.state['bucket']}", f"arn:aws-cn:s3:::{s.state['bucket']}/*"]},
        {"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": f"arn:aws-cn:lambda:{s.region}:{s.account}:function:{s.name}"},
        {"Effect": "Allow", "Action": ["bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:InvokeGateway",
                                     "bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetResourceOauth2Token"],
         "Resource": resources},
        {"Effect": "Allow", "Action": "secretsmanager:GetSecretValue",
         "Resource": [f"arn:aws-cn:secretsmanager:{s.region}:{s.account}:secret:{s.name}*",
                      f"arn:aws-cn:secretsmanager:{s.region}:{s.account}:secret:bedrock-agentcore-identity!*{s.name}*"]},
        {"Effect": "Allow", "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface",
                                     "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"], "Resource": "*"}]
    iam.put_role_policy(RoleName=s.name+"-agentcore", PolicyName="synthetic-test",
                        PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": statements}))
    private = RESULTS / f"{s.region}-private-key.pem"
    secrets_file = RESULTS / f"{s.region}-secrets.json"
    if not private.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        private.chmod(0o600)
        secrets_file.write_text(json.dumps({"clientSecret": secrets.token_hex(24), "pathKey": secrets.token_hex(16)}))
        secrets_file.chmod(0o600)
    key = serialization.load_pem_private_key(private.read_bytes(), None)
    sec = json.loads(secrets_file.read_text())
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="retest", use="sig", alg="RS256")
    numbers = key.private_numbers()
    env = {"CLIENT_SECRET": sec["clientSecret"], "PATH_KEY": sec["pathKey"], "JWK": json.dumps(jwk),
           "RSA_KEY": json.dumps({"n": numbers.public_numbers.n, "d": numbers.d})}
    code = io.BytesIO()
    with zipfile.ZipFile(code, "w") as archive:
        archive.writestr("retest_backend.py", (ROOT/"retest_backend.py").read_bytes())
    if "lambda_arn" not in s.state:
        time.sleep(10)
        created = s.client("lambda").create_function(FunctionName=s.name, Runtime="python3.12",
            Role=s.state["lambda_role"], Handler="retest_backend.handler", Code={"ZipFile": code.getvalue()},
            Timeout=30, Environment={"Variables": env}, Tags={"Purpose": s.name})
        s.state["lambda_arn"] = created["FunctionArn"]
        s.resource("lambda", s.name)
        s.client("lambda").get_waiter("function_active_v2").wait(FunctionName=s.name)
    api = s.client("apigateway")
    if "api_id" not in s.state:
        created = api.create_rest_api(name=s.name, endpointConfiguration={"types": ["REGIONAL"]}, tags={"Purpose": s.name})
        aid = created["id"]
        s.state["api_id"] = aid
        s.resource("api", aid)
        integration = f"arn:aws-cn:apigateway:{s.region}:lambda:path/2015-03-31/functions/{s.state['lambda_arn']}/invocations"
        auth = api.create_authorizer(restApiId=aid, name="synthetic-path-authorizer", type="REQUEST",
            authorizerUri=integration, authorizerResultTtlInSeconds=0)
        root = api.get_resources(restApiId=aid)["items"][0]["id"]
        rid = api.create_resource(restApiId=aid, parentId=root, pathPart="{proxy+}")["id"]
        api.put_method(restApiId=aid, resourceId=rid, httpMethod="ANY", authorizationType="CUSTOM", authorizerId=auth["id"])
        api.put_integration(restApiId=aid, resourceId=rid, httpMethod="ANY", type="AWS_PROXY",
                            integrationHttpMethod="POST", uri=integration)
        s.client("lambda").add_permission(FunctionName=s.name, StatementId="test-api", Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com", SourceArn=f"arn:aws-cn:execute-api:{s.region}:{s.account}:{aid}/*")
        api.create_deployment(restApiId=aid, stageName="test")
    issuer = f"https://{s.state['api_id']}.execute-api.{s.region}.amazonaws.com.cn/test/{sec['pathKey']}"
    s.state.update(api_url=issuer, issuer=issuer)
    s.save()
    def discovery():
        response = requests.get(issuer+"/.well-known/openid-configuration", timeout=30)
        assert response.status_code == 200, {"status": response.status_code, "body": response.text}
        assert response.json()["issuer"] == issuer
        return {"publicTrustedTlsDiscovery": True, "requestId": response.headers.get("x-amzn-requestid")}
    s.test("fixture.oidc.public_discovery", discovery)
    def token():
        response = requests.post(issuer+"/token", auth=("cn-retest",sec["clientSecret"]),
                                 data={"grant_type":"client_credentials","scope":"test"},timeout=30)
        assert response.status_code==200, {"status":response.status_code,"body":response.text}
        token=response.json()["access_token"]
        claims=jwt.decode(token,key.public_key(),algorithms=["RS256"],audience="cn-retest",issuer=issuer)
        return {"tokenSignatureAndClaimsValidated":True,"grant":claims["grant"]}
    s.test("fixture.oidc.client_credentials", token)
