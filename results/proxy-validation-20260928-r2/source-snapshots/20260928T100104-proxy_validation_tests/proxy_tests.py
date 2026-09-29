from browser_tests import start, stop, connect
from playwright.sync_api import sync_playwright


def run(s):
    inst = s.client("ec2").describe_instances(InstanceIds=[s.state["instance"]])["Reservations"][0]["Instances"][0]
    ip = s.state["private_ip"]
    dns = inst["PrivateDnsName"]
    proxy = {"proxies": [{"externalProxy": {"server": ip, "port": 3128,
                    "credentials": {"basicAuth": {"secretArn": s.state["proxy_secret"]}}}}],
             "bypass": {"domainPatterns": [dns, ".compute.internal"]}}
    certs = [{"location": {"secretsManager": {"secretArn": s.state["ca_secret"]}}}]
    r = start(s, s.state["vpc_browser"], proxyConfiguration=proxy, certificates=certs)
    try:
        with sync_playwright() as pw:
            br = connect(s, pw, r)
            def route():
                pg = br.contexts[0].new_page()
                try:
                    response = pg.goto(f"https://{ip}:8443", timeout=30000)
                    text = pg.locator("body").inner_text()
                    assert response.status == 200 and "private-network-ok" in text, {"httpStatus": response.status, "body": text[:1000]}
                    return {"httpsViaAuthenticatedConnect": True, "httpStatus": response.status}
                finally:
                    pg.close()
            s.test("browser.proxy.authenticated_routing", route)
            def bypass():
                pg = br.contexts[0].new_page()
                try:
                    response = pg.goto(f"http://{dns}:8000", timeout=30000)
                    text = pg.locator("body").inner_text()
                    assert "private-network-ok" in text, {"httpStatus": response.status, "body": text[:1000], "dns": dns}
                    return {"privateDnsBypassedProxy": True, "httpStatus": response.status}
                finally:
                    pg.close()
            s.test("browser.proxy.bypass", bypass)
            def http_proxy():
                pg = br.contexts[0].new_page()
                try:
                    response = pg.goto("http://proxy-only.agentcore.test", timeout=30000)
                    text = pg.locator("body").inner_text()
                    assert response.status == 200 and "authenticated-proxy-ok" in text, {"httpStatus": response.status, "body": text[:1000]}
                    return {"httpViaAuthenticatedProxy": True}
                finally:
                    pg.close()
            s.test("browser.proxy.http_routing", http_proxy)
            br.close()
    finally:
        stop(s, r)
    r = start(s, s.state["vpc_browser"], certificates=certs)
    try:
        def baseline():
            import json
            credentials = json.loads(s.client("secretsmanager").get_secret_value(SecretId=s.state["proxy_secret"])["SecretString"])
            with sync_playwright() as pw:
                br = connect(s, pw, r)
                ctx = br.new_context(proxy={"server": f"http://{ip}:3128", **credentials})
                pg = ctx.new_page()
                response = pg.goto("http://proxy-only.agentcore.test", timeout=30000)
                text = pg.locator("body").inner_text()
                assert response.status == 200 and "authenticated-proxy-ok" in text, {"httpStatus": response.status, "body": text[:1000]}
                ctx.close()
                br.close()
                return {"proxyFixtureAcceptsCorrectCredentials": True}
        s.test("browser.proxy.fixture_baseline", baseline)
    finally:
        stop(s, r)
