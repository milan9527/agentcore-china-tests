"""Compare managed proxy routing with direct/Playwright paths using origin logs."""
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from browser_tests import connect, stop

PORTS = [("http", 80), ("http", 8000), ("http", 8081), ("https", 443), ("https", 8443)]


def run(s):
    output = Path(s.state_path).parent
    origin = s.state["private_ip"]
    proxy = s.state["proxy_ip"]
    dns = s.state["target_dns"]
    creds = json.loads(s.client("secretsmanager").get_secret_value(SecretId=s.state["proxy_secret"])["SecretString"])
    certs = [{"location": {"secretsManager": {"secretArn": s.state["ca_secret"]}}}]
    observations = []

    def start(label, config=None, certificate=True):
        params = {"browserIdentifier": s.state["vpc_browser"], "name": label.replace("-", "_"),
                  "sessionTimeoutSeconds": 1800}
        if certificate:
            params["certificates"] = certs
        if config is not None:
            params["proxyConfiguration"] = config
        response = s.runtime.start_browser_session(**params)
        s.state["sessions"].append({"browser": response["browserIdentifier"], "id": response["sessionId"]})
        s.save()
        s.record("proxy.session." + label, "INFO", {"configuration": params,
                    "sessionId": response["sessionId"], "requestId": response["ResponseMetadata"]["RequestId"]})
        return response

    def managed(port=3128, explicit=False, credential="good", bypass=None):
        external = {"server": proxy, "port": port}
        if port != 3129 and credential != "missing":
            external["credentials"] = {"basicAuth": {"secretArn":
                s.state["bad_proxy_secret"] if credential == "bad" else s.state["proxy_secret"]}}
        if explicit:
            external["domainPatterns"] = [origin, dns, "proxy-only.agentcore.test"]
        conf = {"proxies": [{"externalProxy": external}]}
        if bypass:
            conf["bypass"] = {"domainPatterns": bypass}
        return conf

    control_info = start("observer")
    with sync_playwright() as pw:
        control = connect(s, pw, control_info)
        ctx = control.contexts[0]
        proxy_observer, origin_observer = ctx.new_page(), ctx.new_page()
        deadline = time.monotonic() + 180
        for page, ip in [(proxy_observer, proxy), (origin_observer, origin)]:
            while True:
                try:
                    response = page.goto(f"http://{ip}/health", timeout=10000)
                    assert response.status == 200
                    assert json.loads(page.locator("body").inner_text())["ready"]
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(3)
        s.record("proxy.fixture.ready", "PASS", {"separateOriginAndProxyIps": origin != proxy,
                 "browserVersion": control.version, "originIp": origin, "proxyIp": proxy})

        def logs(page):
            return page.evaluate("async () => {const r=await fetch('/stats',{cache:'no-store'});return await r.json()}")

        def write_logs():
            for role, page in [("proxy", proxy_observer), ("origin", origin_observer)]:
                (output/f"{s.region}-{role}-access.json").write_text(json.dumps(logs(page), indent=2) + "\n")

        def visit(browser, context, label, scheme, port, host, expected, session_id, attempt=1):
            marker = uuid.uuid4().hex
            url = f"{scheme}://{host}:{port}/probe/{marker}"
            before_proxy = logs(proxy_observer)
            before_origin = logs(origin_observer)
            page = context.new_page()
            started = time.monotonic()
            evidence = {"label": label, "url": url, "scheme": scheme, "port": port,
                        "host": host, "expectedRoute": expected, "attempt": attempt, "marker": marker,
                        "sessionId": session_id, "browserVersion": browser.version}
            try:
                response = page.goto(url, timeout=12000, wait_until="domcontentloaded")
                text = page.locator("body").inner_text(timeout=3000)
                evidence.update(httpStatus=response.status, responseHeaders={
                    k: v for k, v in response.headers.items() if k.lower() in
                    ("server", "via", "x-squid-error", "content-type", "x-cache", "x-cache-lookup")},
                    responseText=text[:1600])
                try:
                    evidence["originResponse"] = json.loads(text)
                except ValueError:
                    pass
            except Exception as error:
                evidence.update(errorType=type(error).__name__, error=str(error)[:1800])
            finally:
                page.close()
            proxy_events = [row for row in logs(proxy_observer) if row["seq"] > len(before_proxy)]
            origin_events = [row for row in logs(origin_observer) if row["seq"] > len(before_origin)]
            related_proxy = [row for row in proxy_events if marker in row.get("path", "") or
                             (row.get("method") == "CONNECT" and row.get("path") == f"{host}:{port}") or
                             row.get("destination") == f"{host}:{port}"]
            related_origin = [row for row in origin_events if marker in row.get("path", "")]
            matched = evidence.get("originResponse", {}).get("path") == f"/probe/{marker}"
            success = evidence.get("httpStatus") == 200 and matched and len(related_origin) == 1
            is_proxy = bool(related_origin) and all(row["peerIp"] == proxy for row in related_origin)
            direct = bool(related_origin) and all(row["peerIp"] != proxy for row in related_origin)
            if expected == "proxy":
                ok = success and is_proxy and any(row.get("authAccepted") for row in related_proxy)
            elif expected == "direct":
                ok = success and direct and not related_proxy
            elif expected == "auth-denied":
                ok = not success and not related_origin and any(
                    row.get("authRequired") and not row.get("authAccepted") for row in related_proxy)
            elif expected == "tls-denied":
                ok = not success and "ERR_CERT_AUTHORITY_INVALID" in evidence.get("error", "")
            else:
                raise ValueError(expected)
            evidence.update(proxyEvents=related_proxy, originEvents=related_origin,
                externalProxyContacted=bool(related_proxy), originReached=bool(related_origin),
                actualRoute="proxy" if is_proxy else "direct" if direct else "not-reached",
                seconds=round(time.monotonic()-started, 3))
            feature = f"proxy.case.{label}.{scheme}_{port}"
            status = "PASS" if ok else "FAIL"
            s.record(feature, status, evidence)
            observations.append({"region": s.region, "feature": feature, "status": status, **evidence})
            (output/f"{s.region}-observations.json").write_text(json.dumps(observations, indent=2) + "\n")
            return ok

        def cases(browser, context, label, ports=PORTS, host=None, expected="proxy", session_id=None, retry=True):
            for scheme, port in ports:
                passed = visit(browser, context, label, scheme, port, host or origin, expected, session_id)
                if not passed and retry:
                    visit(browser, context, label, scheme, port, host or origin, expected, session_id, 2)
            write_logs()

        try:
            cases(control, ctx, "direct-baseline", expected="direct", session_id=control_info["sessionId"])
            for port in (3128, 8080, 3129):
                config = {"server": f"http://{proxy}:{port}", **(creds if port != 3129 else {})}
                extra = control.new_context(proxy=config, ignore_https_errors=False)
                try:
                    cases(control, extra, f"playwright-proxy-{port}", session_id=control_info["sessionId"])
                finally:
                    extra.close()
            # Diagnostics retain only allow-listed, non-credential Squid directives.
            diagnostic = ctx.new_page()
            try:
                diagnostic.goto("file:///etc/squid/squid.conf", timeout=8000)
                text = diagnostic.locator("body").inner_text(timeout=3000)
                selected = [{"line": i, "directive": line} for i, line in enumerate(text.splitlines(), 1)
                    if re.match(r"^\s*(acl\s+\S+\s+(port|method)\s|http_access\s|always_direct\s|never_direct\s)", line)]
                s.record("proxy.diagnostic.squid_config", "INFO", {
                    "readable": bool(selected), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "directives": selected, "rawConfigurationSaved": False})
            except Exception as error:
                s.record("proxy.diagnostic.squid_config", "INFO", {"readable": False,
                    "errorType": type(error).__name__, "message": str(error)[:500]})
            finally:
                diagnostic.close()

            scenarios = []
            for port in (3128, 8080, 3129):
                for explicit in (False, True):
                    scenarios.append((f"managed-{port}-{'explicit' if explicit else 'default'}",
                                      managed(port, explicit), PORTS, origin, "proxy"))
            for label, pattern, host in [
                ("ip", origin, origin), ("hostname", dns, dns), ("suffix", ".compute.internal", dns)]:
                scenarios.append((f"bypass-{label}", managed(bypass=[pattern]), PORTS, host, "direct"))
            scenarios += [
                ("bypass-ip-bad-credentials", managed(credential="bad", bypass=[origin]), PORTS, origin, "direct"),
                ("bypass-and-route-ip", managed(explicit=True, bypass=[origin]), PORTS, origin, "direct"),
                ("hostname-route", managed(explicit=True), [("http", 80), ("https", 443)], dns, "proxy"),
                ("proxy-only-dns-default", managed(), [("http", 80), ("https", 443)],
                 "proxy-only.agentcore.test", "proxy"),
                ("proxy-only-dns-explicit", managed(explicit=True), [("http", 80), ("https", 443)],
                 "proxy-only.agentcore.test", "proxy"),
                ("bad-credentials", managed(explicit=True, credential="bad"),
                 [("http", 80), ("https", 443)], origin, "auth-denied"),
                ("missing-credentials", managed(explicit=True, credential="missing"),
                 [("http", 80), ("https", 443)], origin, "auth-denied"),
            ]
            for label, config, ports, host, expected in scenarios:
                session = start(label, config)
                browser = None
                try:
                    browser = connect(s, pw, session)
                    native = browser.contexts[0]
                    page = native.new_page()
                    try:
                        page.goto("chrome://version", timeout=10000)
                        flags = [word for word in page.locator("body").inner_text().split() if word.startswith("--proxy")]
                        s.record("proxy.flags."+label, "INFO", {"flags": flags, "sessionId": session["sessionId"]})
                    finally:
                        page.close()
                    cases(browser, native, label, ports, host, expected, session["sessionId"])
                finally:
                    if browser:
                        browser.close()
                    stop(s, session)
            session = start("untrusted-control", certificate=False)
            browser = None
            try:
                browser = connect(s, pw, session)
                cases(browser, browser.contexts[0], "untrusted-control", [("https", 443)],
                      expected="tls-denied", session_id=session["sessionId"], retry=False)
            finally:
                if browser:
                    browser.close()
                stop(s, session)
            cases(control, ctx, "direct-final-control", expected="direct", session_id=control_info["sessionId"])
        finally:
            write_logs()
            control.close()
            stop(s, control_info)
    return {"attempts": len(observations), "observations": str(output/f"{s.region}-observations.json")}
