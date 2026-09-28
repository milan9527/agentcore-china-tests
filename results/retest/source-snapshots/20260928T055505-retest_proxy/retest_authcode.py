import json
import requests
import time
from retest_gateway import gw,jwt_config,user_token


def run(s):
    gateway=gw(s,"jwt",auth="CUSTOM_JWT",authorizerConfiguration=jwt_config(s))
    s.control.update_gateway(gatewayIdentifier=gateway["gatewayId"],name=gateway["name"],
        roleArn=s.state["agentcore_role"],protocolType="MCP",authorizerType="CUSTOM_JWT",
        authorizerConfiguration=jwt_config(s),exceptionLevel="DEBUG",protocolConfiguration={"mcp":{
            "supportedVersions":["2025-03-26","2025-11-25","2026-07-28"],
            "sessionConfiguration":{"sessionTimeoutInSeconds":900},
            "streamingConfiguration":{"enableResponseStreaming":True}}})
    s.wait(lambda:s.control.get_gateway(gatewayIdentifier=gateway["gatewayId"]))
    name=gateway["workloadIdentityDetails"]["workloadIdentityArn"].rsplit("/",1)[-1]
    s.client("iam").put_role_policy(RoleName=s.name+"-agentcore",PolicyName="user-oauth",PolicyDocument=json.dumps({
        "Version":"2012-10-17","Statement":[{"Effect":"Allow",
            "Action":["bedrock-agentcore:GetWorkloadAccessTokenForJWT","bedrock-agentcore:GetWorkloadAccessTokenForUserId"],
            "Resource":f"arn:aws-cn:bedrock-agentcore:{s.region}:{s.account}:workload-identity-directory/*"}]}))
    time.sleep(10)
    s.control.update_workload_identity(name=name,allowedResourceOauth2ReturnUrls=[s.state["issuer"]+"/callback"])
    token=user_token(s)
    meta={"io.modelcontextprotocol/protocolVersion":"2026-07-28",
          "io.modelcontextprotocol/clientInfo":{"name":"cn-followup","version":"1"},
          "io.modelcontextprotocol/clientCapabilities":{"elicitation":{"url":{}}}}
    result=s.mcp("tools/call",{"name":"authorization-code___secure","arguments":{},"_meta":meta},
        token=token,version="2026-07-28",extra_headers={"Mcp-Method":"tools/call","Mcp-Name":"authorization-code___secure"})
    s.record("gateway.oauth.authorization_code.initial","INFO",result)
    return result
