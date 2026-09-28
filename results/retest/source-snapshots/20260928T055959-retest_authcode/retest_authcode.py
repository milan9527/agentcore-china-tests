import json
import requests
import time
from urllib.parse import urlsplit,urljoin
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
    body=result["body"][-1] if isinstance(result["body"],list) else result["body"]
    requests_map=body["result"]["inputRequests"]
    url=requests_map["urlElicitation"]["params"]["url"]
    allowed={urlsplit(s.state["issuer"]).hostname,f"bedrock-agentcore.{s.region}.amazonaws.com.cn"}
    redirects=[]
    http=requests.Session()
    for _ in range(8):
        assert urlsplit(url).hostname in allowed,"Unexpected consent redirect host"
        response=http.get(url,allow_redirects=False,timeout=30)
        parts=urlsplit(url)
        redirects.append({"host":parts.hostname,"path":parts.path,"status":response.status_code})
        if response.is_redirect:
            url=urljoin(url,response.headers["Location"]);continue
        break
    s.record("gateway.oauth.authorization_code.redirects","INFO",{"redirects":redirects,
        "finalStatus":response.status_code,"finalBody":response.text[:1800]})
    params={"name":"authorization-code___secure","arguments":{},"_meta":meta,
            "inputResponses":{k:{"action":"accept"} for k in requests_map}}
    if "requestState" in body["result"]:params["requestState"]=body["result"]["requestState"]
    result=s.mcp("tools/call",params,token=token,version="2026-07-28",
        extra_headers={"Mcp-Method":"tools/call","Mcp-Name":"authorization-code___secure"})
    s.record("gateway.oauth.authorization_code.resumed","INFO",result)
    s.require_mcp(result,"authorization_code")
    s.record("gateway.outbound.oauth_authorization_code","PASS",{"redirects":redirects,"resumedToolCall":result})
    return result
