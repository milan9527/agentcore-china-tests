import json
import os
from playwright.sync_api import sync_playwright
from botocore.exceptions import ClientError
from browser_tests import connect,stop
from network_tests import infra


def run(s):
    if "instance" not in s.state:infra(s)
    try:
        s.client("ec2").authorize_security_group_ingress(GroupId=s.state["sg"],IpPermissions=[{
            "IpProtocol":"tcp","FromPort":3129,"ToPort":3129,"UserIdGroupPairs":[{"GroupId":s.state["sg"]}]}])
    except ClientError as e:
        if e.response["Error"]["Code"]!="InvalidPermission.Duplicate":raise
    if "vpc_browser" not in s.state:
        r=s.control.create_browser(name=s.name.replace("-","_")+"_proxy",executionRoleArn=s.state["agentcore_role"],
            networkConfiguration={"networkMode":"VPC","vpcConfig":{"subnets":[s.state["subnet"]],
                "securityGroups":[s.state["sg"]],"requireServiceS3Endpoint":False}},tags={"Purpose":s.name})
        s.state["vpc_browser"]=r["browserId"];s.resource("browser",r["browserId"])
    s.wait(lambda:s.control.get_browser(browserId=s.state["vpc_browser"]),timeout=600)
    ip=s.state["private_ip"];certs=[{"location":{"secretsManager":{"secretArn":s.state["ca_secret"]}}}]
    def start(**extra):
        r=s.runtime.start_browser_session(browserIdentifier=s.state["vpc_browser"],name="proxy_followup",
            sessionTimeoutSeconds=900,certificates=certs,**extra)
        s.state["sessions"].append({"browser":r["browserIdentifier"],"id":r["sessionId"]});s.save();return r
    credentials=json.loads(s.client("secretsmanager").get_secret_value(SecretId=s.state["proxy_secret"])["SecretString"])
    with sync_playwright() as pw:
        for mode in os.environ.get("PROXY_MODES","baseline,no-auth,auth,scheme,explicit-domains").split(","):
            proxy={"server":("http://" if mode=="scheme" else "")+ip,"port":3129 if mode=="no-auth" else 3128}
            if mode!="no-auth":proxy["credentials"]={"basicAuth":{"secretArn":s.state["proxy_secret"]}}
            item={"externalProxy":proxy}
            if mode=="explicit-domains":item["domainPatterns"]=["proxy-only.agentcore.test",ip]
            config={"proxies":[item],"bypass":{"domainPatterns":["bypass.agentcore.test"]}}
            try:
                session=start(**({} if mode=="baseline" else {"proxyConfiguration":config}))
            except ClientError as e:
                if mode=="scheme" and e.response["Error"]["Code"]=="ValidationException":
                    s.record("browser.proxy.scheme_validation","PASS",{"schemePrefixRejected":True,"response":e.response})
                    continue
                raise
            try:
                browser=connect(s,pw,session);context=browser.contexts[0]
                pg=context.new_page()
                def version():
                    pg.goto("chrome://version");text=pg.locator("body").inner_text()
                    return {"proxyFlags":[part for part in text.split() if part.startswith("--proxy")],
                            "remoteVersion":browser.version}
                s.test("browser.proxy."+mode+".startup_flags",version)
                if mode=="baseline":
                    s.test("browser.proxy.private_endpoint_baseline",lambda:navigate(pg,f"https://{ip}:8443","private-network-ok"))
                    ctx=browser.new_context(proxy={"server":f"http://{ip}:3128",**credentials},ignore_https_errors=False)
                    p=ctx.new_page()
                    s.test("browser.proxy.explicit_context.http",lambda:navigate(p,"http://proxy-only.agentcore.test","authenticated-proxy-ok"))
                    s.test("browser.proxy.explicit_context.https",lambda:navigate(p,f"https://{ip}:8443","private-network-ok"))
                    ctx.close()
                    pg.goto(f"http://{ip}:8000/stats")
                    s.record("browser.proxy.baseline_access_log","PASS",json.loads(pg.locator("body").inner_text()))
                else:
                    s.test("browser.proxy."+mode+".http",lambda:navigate(pg,"http://proxy-only.agentcore.test","authenticated-proxy-ok"))
                    s.test("browser.proxy."+mode+".https",lambda:navigate(pg,f"https://{ip}:8443","private-network-ok"))
                    # The bypass hostname resolves to the private IP through nip.io.
                    # Use the actual EC2 private hostname, configured on a separate session below.
                pg.close();browser.close()
            finally:stop(s,session)
        inst=s.client("ec2").describe_instances(InstanceIds=[s.state["instance"]])["Reservations"][0]["Instances"][0]
        dns=inst["PrivateDnsName"]
        session=start(proxyConfiguration={"proxies":[{"externalProxy":{"server":ip,"port":3128,
            "credentials":{"basicAuth":{"secretArn":s.state["proxy_secret"]}}}}],"bypass":{"domainPatterns":[dns,".compute.internal"]}})
        try:
            browser=connect(s,pw,session);pg=browser.contexts[0].new_page()
            s.test("browser.proxy.bypass",lambda:navigate(pg,f"http://{dns}:8000/bypass-marker","private-network-ok"))
            browser.close()
        finally:stop(s,session)
        session=start()
        try:
            browser=connect(s,pw,session);pg=browser.contexts[0].new_page()
            pg.goto(f"http://{ip}:8000/stats");events=json.loads(pg.locator("body").inner_text())
            s.record("browser.proxy.server_access_log","PASS",events)
            browser.close()
        finally:stop(s,session)
    # Account availability is checked against a real test VPC.
    from retest_gateway import gw
    from gateway_tests import target,openapi
    gw(s,"private-probe")
    schema=openapi(s);schema["servers"]=[{"url":f"https://{ip}:8443"}]
    try:
        result=target(s,"private",{"mcp":{"openApiSchema":{"inlinePayload":json.dumps(schema)}}},
            privateEndpoint={"managedVpcResource":{"vpcIdentifier":s.state["vpc"],"subnetIds":[s.state["subnet"]],
                "securityGroupIds":[s.state["sg"]],"endpointIpAddressType":"IPV4"}})
        s.record("gateway.private_target","PARTIAL",result)
    except ClientError as e:
        s.record("gateway.private_target","BLOCKED",e.response)


def navigate(page,url,marker):
    response=page.goto(url,timeout=20000)
    body=page.locator("body").inner_text()
    evidence={"status":response.status,"body":body[:900]}
    assert response.status==200 and marker in body,evidence
    return evidence
