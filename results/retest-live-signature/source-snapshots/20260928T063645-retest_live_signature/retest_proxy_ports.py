import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_tests import connect,stop
from network_tests import infra
from retest_proxy import navigate


def run(s):
    ec2=s.client("ec2")
    if not s.state.get("standard_port_fixture"):
        old=s.state["instance"]
        ec2.terminate_instances(InstanceIds=[old])
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[old],WaiterConfig={"Delay":5,"MaxAttempts":60})
        for r in s.state["resources"]:
            if r["kind"]=="instance" and r["id"]==old:r["deleted"]=True
        s.save()
        infra(s)
        for port in [80,443]:
            ec2.authorize_security_group_ingress(GroupId=s.state["sg"],IpPermissions=[{
                "IpProtocol":"tcp","FromPort":port,"ToPort":port,"UserIdGroupPairs":[{"GroupId":s.state["sg"]}]}])
        s.state["standard_port_fixture"]=True;s.save()
    ip=s.state["private_ip"]
    dns=ec2.describe_instances(InstanceIds=[s.state["instance"]])["Reservations"][0]["Instances"][0]["PrivateDnsName"]
    certs=[{"location":{"secretsManager":{"secretArn":s.state["ca_secret"]}}}]
    def start(**extra):
        r=s.runtime.start_browser_session(browserIdentifier=s.state["vpc_browser"],name="standard_port_proxy",
            sessionTimeoutSeconds=900,certificates=certs,**extra)
        s.state["sessions"].append({"browser":r["browserIdentifier"],"id":r["sessionId"]});s.save();return r
    credentials=json.loads(s.client("secretsmanager").get_secret_value(SecretId=s.state["proxy_secret"])["SecretString"])
    with sync_playwright() as pw:
        for mode in os.environ.get("STANDARD_PROXY_MODES","baseline,default-auth,explicit-auth,default-no-auth,explicit-no-auth").split(","):
            external={"server":ip,"port":3129 if "no-auth" in mode else 3128}
            if "no-auth" not in mode:external["credentials"]={"basicAuth":{"secretArn":s.state["proxy_secret"]}}
            if mode.startswith("explicit"):external["domainPatterns"]=[ip,"proxy-only.agentcore.test"]
            config={"proxies":[{"externalProxy":external}]}
            r=start(**({} if mode=="baseline" else {"proxyConfiguration":config}))
            try:
                browser=connect(s,pw,r);ctx=browser.contexts[0];page=ctx.new_page()
                if mode=="baseline":
                    s.test("browser.proxy.standard.private_http_baseline",lambda:navigate(page,f"http://{ip}/baseline","private-network-ok"))
                    s.test("browser.proxy.standard.private_https_baseline",lambda:navigate(page,f"https://{ip}/baseline","private-network-ok"))
                    extra=browser.new_context(proxy={"server":f"http://{ip}:3128",**credentials})
                    pg=extra.new_page()
                    s.test("browser.proxy.standard.explicit_context_https",lambda:navigate(pg,f"https://{ip}/explicit-context","private-network-ok"))
                    extra.close()
                else:
                    s.test("browser.proxy.standard."+mode+".http",lambda:navigate(page,f"http://{ip}/case-{mode}","authenticated-proxy-ok"))
                    s.test("browser.proxy.standard."+mode+".https",lambda:navigate(page,f"https://{ip}/case-{mode}","private-network-ok"))
                    s.test("browser.proxy.standard."+mode+".synthetic_dns",lambda:navigate(page,"http://proxy-only.agentcore.test","authenticated-proxy-ok"))
                browser.close()
            finally:stop(s,r)
        r=start(proxyConfiguration={"proxies":[{"externalProxy":{"server":ip,"port":3128,
            "credentials":{"basicAuth":{"secretArn":s.state["proxy_secret"]}}}}],
            "bypass":{"domainPatterns":[dns,".compute.internal"]}})
        try:
            browser=connect(s,pw,r);page=browser.contexts[0].new_page()
            s.test("browser.proxy.standard.bypass",lambda:navigate(page,f"http://{dns}/isolated-bypass","private-network-ok"))
            browser.close()
        finally:stop(s,r)
        r=start()
        try:
            browser=connect(s,pw,r);page=browser.contexts[0].new_page();page.goto(f"http://{ip}/stats")
            events=json.loads(page.locator("body").inner_text())
            s.record("browser.proxy.standard.server_log","PASS",events)
            (Path(s.state_path).parent/f"{s.region}-proxy-access.json").write_text(json.dumps(events,indent=2))
            browser.close()
        finally:stop(s,r)
