import json
import secrets
import time
import requests
import boto3
from botocore.credentials import Credentials
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
from retest_gateway import gw
from gateway_tests import target
import runtime_gateway_tests


def run(s):
    gw(s,"http",mcp=False)
    runtime_gateway_tests.run(s)
    principal=s.client("sts").get_caller_identity()["Arn"]
    caller_name=s.name+"-caller"
    if "caller_role" not in s.state:
        role=s.client("iam").create_role(RoleName=caller_name,AssumeRolePolicyDocument=json.dumps({
            "Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":principal},"Action":"sts:AssumeRole"}]}))
        s.state["caller_role"]=role["Role"]["Arn"];s.resource("role",caller_name)
    s.client("iam").put_role_policy(RoleName=caller_name,PolicyName="test",PolicyDocument=json.dumps({
        "Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock-agentcore:InvokeGateway","bedrock-agentcore:InvokeAgentRuntime"],
            "Resource":f"arn:aws-cn:bedrock-agentcore:{s.region}:{s.account}:*"}]}))
    time.sleep(10)
    temp=s.client("sts").assume_role(RoleArn=s.state["caller_role"],RoleSessionName="cn-followup",DurationSeconds=900)["Credentials"]
    assumed=Credentials(temp["AccessKeyId"],temp["SecretAccessKey"],temp["SessionToken"])
    runtime=boto3.Session(aws_access_key_id=temp["AccessKeyId"],aws_secret_access_key=temp["SecretAccessKey"],
                         aws_session_token=temp["SessionToken"],region_name=s.region).client("bedrock-agentcore")
    def direct():
        sid=secrets.token_hex(20);s.state.setdefault("runtime_sessions",[]).append(sid);s.save()
        response=runtime.invoke_agent_runtime(agentRuntimeArn=s.state["runtime_arn"],runtimeSessionId=sid,
            payload=b'{"a":20,"b":22}',contentType="application/json")
        body=json.loads(response["response"].read());assert body["sum"]==42,body
        return {"body":body,"requestId":response["ResponseMetadata"]["RequestId"],"credentials":"AssumeRole"}
    s.test("gateway.caller_iam.assumed_role.direct",direct)
    for auth,label in [("AWS_IAM","http"),("AUTHENTICATE_ONLY","authenticate-only")]:
        gateway=s.test("gateway.caller_iam."+auth+".configuration",lambda a=auth,l=label:gw(s,l,auth=a,mcp=False))
        if not gateway:continue
        for credential,name in [("GATEWAY_IAM_ROLE","runtime-role"),("CALLER_IAM_CREDENTIALS","runtime-caller")]:
            target(s,name,{"http":{"agentcoreRuntime":{"arn":s.state["runtime_arn"],"qualifier":"DEFAULT"}}},
                   [{"credentialProviderType":credential}])
            def invoke(n=name):
                sid=secrets.token_hex(20);s.state["runtime_sessions"].append(sid);s.save()
                url=gateway["gatewayUrl"].removesuffix("/mcp")+"/"+n+"/invocations";body='{"a":20,"b":22}'
                req=AWSRequest(method="POST",url=url,data=body,headers={"Content-Type":"application/json",
                    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id":sid})
                SigV4Auth(assumed,"bedrock-agentcore",s.region).add_auth(req)
                response=requests.post(url,data=body,headers=dict(req.headers),timeout=120)
                evidence={"status":response.status_code,"body":response.text,"requestId":response.headers.get("x-amzn-requestid"),
                          "credentials":"AssumeRole","inbound":auth,"outbound":n}
                assert response.status_code==200,evidence
                assert response.json()["sum"]==42,evidence
                return evidence
            s.test("gateway.caller_iam."+auth+"."+name,invoke)
