import hashlib
import json
import secrets
import time
import requests
import jwt
from cryptography.hazmat.primitives import serialization
from suite import RESULTS
from gateway_tests import target,call,TOOLS,openapi


def gw(s,label,auth="AWS_IAM",mcp=True,**extra):
    if label in s.state:
        result=s.control.get_gateway(gatewayIdentifier=s.state[label])
    else:
        result=s.control.create_gateway(name=s.name+"-"+label,roleArn=s.state["agentcore_role"],
            authorizerType=auth,exceptionLevel="DEBUG",tags={"Purpose":s.name},
            **({"protocolType":"MCP"} if mcp else {}),**extra)
        s.state[label]=result["gatewayId"];s.resource("gateway",result["gatewayId"])
    result=s.wait(lambda:s.control.get_gateway(gatewayIdentifier=result["gatewayId"]),timeout=300)
    s.state["gateway"]=result;s.save()
    return result


def keys(s):
    secret=json.loads((RESULTS/f"{s.region}-secrets.json").read_text())
    key=serialization.load_pem_private_key((RESULTS/f"{s.region}-private-key.pem").read_bytes(),None)
    return secret,key


def user_token(s,**overrides):
    _,key=keys(s)
    claims={"iss":s.state["issuer"],"aud":"cn-retest","client_id":"cn-retest","sub":"synthetic-user","scope":"test",
            "iat":int(time.time()),"exp":int(time.time())+900,**overrides}
    return jwt.encode(claims,key,algorithm="RS256",headers={"kid":"retest"})


def jwt_config(s):
    return {"customJWTAuthorizer":{"discoveryUrl":s.state["issuer"]+"/.well-known/openid-configuration",
                                  "allowedAudience":["cn-retest"],"allowedClients":["cn-retest"],"allowedScopes":["test"]}}


def run(s):
    sec,key=keys(s);issuer=s.state["issuer"]
    response=requests.get(issuer+"/.well-known/openid-configuration",timeout=30)
    assert response.status_code==200,response.status_code
    s.record("fixture.oidc.public_discovery","PASS",{"trustedHttps":True,"issuer":issuer})
    response=requests.post(issuer+"/token",auth=("cn-retest",sec["clientSecret"]),
        data={"grant_type":"client_credentials","scope":"test"},timeout=30)
    assert response.status_code==200,response.status_code
    jwt.decode(response.json()["access_token"],key.public_key(),algorithms=["RS256"],audience="cn-retest",issuer=issuer)
    s.record("fixture.oidc.client_credentials","PASS",{"signatureAndClaimsVerified":True})
    def inbound():
        gw(s,"jwt",auth="CUSTOM_JWT",authorizerConfiguration=jwt_config(s))
        target(s,"add",{"mcp":{"lambda":{"lambdaArn":s.state["lambda_arn"],"toolSchema":{"inlinePayload":[TOOLS[0]]}}}},
               [{"credentialProviderType":"GATEWAY_IAM_ROLE"}])
        good=call(s,"add___add",{"a":20,"b":22},"42",token=user_token(s))
        negatives={}
        for label,changes in [("wrongAudience",{"aud":"wrong"}),("wrongClient",{"client_id":"wrong"}),
                              ("expired",{"exp":int(time.time())-600}),("wrongScope",{"scope":"wrong"})]:
            result=s.mcp("tools/list",{},token=user_token(s,**changes))
            assert result["status"] in (401,403),{label:result}
            negatives[label]=result["status"]
        return {"validJwtInvocation":good,"negativeClaims":negatives}
    s.test("gateway.jwt",inbound)
    def passthrough():
        gateway=gw(s,"jwt-http",auth="CUSTOM_JWT",mcp=False,authorizerConfiguration=jwt_config(s))
        target(s,"secure",{"http":{"passthrough":{"endpoint":issuer,"protocolType":"CUSTOM"}}},
               [{"credentialProviderType":"JWT_PASSTHROUGH"}])
        value=user_token(s);url=gateway["gatewayUrl"].removesuffix("/mcp")+"/secure/secure"
        result=requests.get(url,headers={"Authorization":"Bearer "+value},timeout=60)
        assert result.status_code==200,{"status":result.status_code,"body":result.text}
        body=result.json();assert body["tokenSha256"]==hashlib.sha256(value.encode()).hexdigest(),body
        invalid=requests.get(url,headers={"Authorization":"Bearer "+user_token(s,aud="bad")},timeout=30)
        assert invalid.status_code in (401,403),invalid.status_code
        return {"unchangedTokenHashVerified":True,"backend":body,"invalidTokenRejected":invalid.status_code,
                "requestId":result.headers.get("x-amzn-requestid")}
    s.test("gateway.outbound.jwt_passthrough",passthrough)
    gw(s,"jwt",auth="CUSTOM_JWT",authorizerConfiguration=jwt_config(s))
    for grant,label in [("CLIENT_CREDENTIALS","client_credentials"),("TOKEN_EXCHANGE","token_exchange"),
                        ("AUTHORIZATION_CODE","authorization_code")]:
        def oauth(gr=grant,lab=label):
            provider_name=s.name+"-"+lab.replace("_","-")
            if not any(x["kind"]=="oauth-provider" and x["id"]==provider_name for x in s.state["resources"]):
                conf={"clientId":"cn-retest","clientSecret":sec["clientSecret"],
                    "clientAuthenticationMethod":"CLIENT_SECRET_BASIC",
                    "oauthDiscovery":{"discoveryUrl":issuer+"/.well-known/openid-configuration"}}
                if gr=="TOKEN_EXCHANGE":
                    conf["onBehalfOfTokenExchangeConfig"]={"grantType":"TOKEN_EXCHANGE","tokenExchangeGrantTypeConfig":{"actorTokenContent":"NONE"}}
                provider=s.control.create_oauth2_credential_provider(name=provider_name,credentialProviderVendor="CustomOauth2",
                    oauth2ProviderConfigInput={"customOauth2ProviderConfig":conf})
                s.resource("oauth-provider",provider_name)
            provider=s.control.get_oauth2_credential_provider(name=provider_name)
            schema=openapi(s,path="/secure",name="secure")
            credentials={"providerArn":provider["credentialProviderArn"],"scopes":["test"],"grantType":gr}
            if gr=="AUTHORIZATION_CODE":credentials["defaultReturnUrl"]=issuer+"/callback"
            target(s,lab.replace("_","-"),{"mcp":{"openApiSchema":{"inlinePayload":json.dumps(schema)}}},
                   [{"credentialProviderType":"OAUTH","credentialProvider":{"oauthCredentialProvider":credentials}}])
            result=s.mcp("tools/call",{"name":lab.replace("_","-")+"___secure","arguments":{}},token=user_token(s))
            if gr=="AUTHORIZATION_CODE":
                s.record("gateway.oauth.authorization_code.initial","INFO",result)
                return {"targetConfigured":True,"continuationPhase":"retest_authcode"}
            s.require_mcp(result,"true")
            body=result["body"][-1] if isinstance(result["body"],list) else result["body"]
            text=json.dumps(body)
            expected="client_credentials" if gr=="CLIENT_CREDENTIALS" else "urn:ietf:params:oauth:grant-type:token-exchange"
            assert expected in text,result
            return result
        feature="gateway.outbound.oauth_"+label+(".configuration" if grant=="AUTHORIZATION_CODE" else "")
        if grant=="TOKEN_EXCHANGE":
            from botocore.exceptions import ClientError
            try:
                value=oauth()
                s.record(feature,"PASS",value)
            except ClientError as e:
                s.record(feature,"BLOCKED" if "not available for this account" in str(e) else "FAIL",e.response)
        else:
            s.test(feature,oauth)
