import base64
import io
import json
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright
from suite import RESULTS


def start(s, browser="aws.browser.v1", **kw):
    from botocore.auth import SigV4QueryAuth
    from botocore.awsrequest import AWSRequest
    req = AWSRequest(method="GET", url=s.state["api_url"] + "/page")
    SigV4QueryAuth(s.session.get_credentials().get_frozen_credentials(), "execute-api", s.region, expires=300).add_auth(req)
    s.state["page_url"] = req.url
    r = s.runtime.start_browser_session(browserIdentifier=browser, name=s.name.replace("-", "_"),
        sessionTimeoutSeconds=900, viewPort={"width": 1280, "height": 720}, **kw)
    s.state["sessions"].append({"browser": browser, "id": r["sessionId"]})
    s.save()
    return r


def stop(s, r):
    return s.runtime.stop_browser_session(browserIdentifier=r["browserIdentifier"], sessionId=r["sessionId"])


def connect(s, pw, session):
    endpoint = session["streams"]["automationStream"]["streamEndpoint"]
    return pw.chromium.connect_over_cdp(endpoint, headers=s.signed_headers(endpoint), timeout=60000)


def run(s):
    c, rt = s.control, s.runtime
    s.test("browser.list", lambda: c.list_browsers(maxResults=1))
    initial = s.test("browser.managed.start_viewport_timeout", lambda: start(s))
    if not initial:
        return
    url = s.state["page_url"]
    ident = {"browserIdentifier": initial["browserIdentifier"], "sessionId": initial["sessionId"]}
    s.test("browser.session.get", lambda: rt.get_browser_session(**ident))
    s.test("browser.session.list", lambda: rt.list_browser_sessions(browserIdentifier="aws.browser.v1", maxResults=1))
    with sync_playwright() as pw:
        browser = s.test("browser.cdp.connect", lambda: connect(s, pw, initial))
        if not browser:
            s.test("browser.managed.stop", lambda: stop(s, initial))
            return
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)

        def navigate():
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            assert response.status == 200
            assert page.title() == "AgentCore China feature test"
            return {"status": response.status, "title": page.title(), "viewport": page.evaluate("({width:innerWidth,height:innerHeight})")}
        s.test("browser.navigation_https_dom", navigate)

        def form():
            page.locator("#name").fill("Beijing 北京 / Ningxia 宁夏")
            page.locator("#submit").click()
            text = page.locator("#result").inner_text()
            assert text == "Hello Beijing 北京 / Ningxia 宁夏", text
            return text
        s.test("browser.forms_click_unicode_extract", form)
        def screenshot():
            p = RESULTS / f"{s.region}-browser.png"
            raw = page.screenshot(path=str(p), full_page=True)
            assert raw[:8] == b"\x89PNG\r\n\x1a\n"
            return {"path": str(p), "bytes": len(raw)}
        s.test("browser.cdp.screenshot", screenshot)
        def upload():
            page.locator("#upload").set_input_files({"name": "synthetic.txt", "mimeType": "text/plain", "buffer": b"upload-ok"})
            assert page.locator("#file").inner_text() == "synthetic.txt"
            return "synthetic.txt"
        s.test("browser.file_upload", upload)
        def download():
            with page.expect_download() as event:
                page.locator("#download").click()
            d = event.value
            path = RESULTS / f"{s.region}-download.txt"
            d.save_as(str(path))
            assert path.read_text() == "agentcore-download-ok"
            return {"file": d.suggested_filename, "content": path.read_text()}
        s.test("browser.file_download", download)
        def tabs():
            tab = context.new_page()
            tab.goto(url)
            assert tab.title() == page.title()
            count = len(context.pages)
            tab.close()
            page.bring_to_front()
            return {"tabs": count}
        s.test("browser.multiple_tabs", tabs)
        def storage():
            context.add_cookies([{"name": "cn_test", "value": "persist-ok", "url": url, "expires": time.time() + 86400}])
            page.evaluate("localStorage.setItem('cn_test','local-ok')")
            assert any(x["name"] == "cn_test" for x in context.cookies())
            return {"cookie": "persist-ok", "localStorage": page.evaluate("localStorage.getItem('cn_test')")}
        s.test("browser.cookies_local_storage", storage)

        def os_action(action):
            r = rt.invoke_browser(**ident, action=action)
            for v in r.get("result", {}).values():
                if isinstance(v, dict):
                    assert v.get("status", "SUCCESS") == "SUCCESS", r
            return r
        s.test("browser.os.mouseMove", lambda: os_action({"mouseMove": {"x": 200, "y": 200}}))
        s.test("browser.os.mouseClick", lambda: os_action({"mouseClick": {"x": 200, "y": 200, "button": "LEFT"}}))
        page.locator("#name").focus()
        s.test("browser.os.keyShortcut", lambda: os_action({"keyShortcut": {"keys": ["ctrl", "a"]}}))
        s.test("browser.os.keyType", lambda: os_action({"keyType": {"text": "os-input-ok"}}))
        s.test("browser.os.keyPress", lambda: os_action({"keyPress": {"key": "tab"}}))
        s.test("browser.os.mouseDrag", lambda: os_action({"mouseDrag": {"startX": 100, "startY": 200, "endX": 300, "endY": 200}}))
        s.test("browser.os.mouseScroll", lambda: os_action({"mouseScroll": {"x": 500, "y": 500, "deltaY": -400}}))
        def os_screenshot():
            r = os_action({"screenshot": {"format": "PNG"}})
            # Preserve binary content in an artifact, keeping JSON evidence small.
            def extract(x):
                if isinstance(x, dict):
                    for k, v in list(x.items()):
                        if isinstance(v, bytes) and len(v) > 100:
                            p = RESULTS / f"{s.region}-browser-os.png"
                            p.write_bytes(v)
                            x[k] = {"bytes": len(v), "path": str(p)}
                        elif isinstance(v, str) and len(v) > 10000:
                            try:
                                raw = base64.b64decode(v)
                                p = RESULTS / f"{s.region}-browser-os.png"
                                p.write_bytes(raw)
                                x[k] = {"bytes": len(raw), "path": str(p)}
                            except Exception:
                                pass
                        else:
                            extract(v)
            extract(r)
            return r
        s.test("browser.os.screenshot", os_screenshot)
        s.test("browser.os.input_effect", lambda: assert_value(page.locator("#name").input_value(), "os-input-ok"))

        def live_view():
            from botocore.auth import SigV4QueryAuth
            from botocore.awsrequest import AWSRequest
            endpoint = initial["streams"]["liveViewStream"]["streamEndpoint"]
            req = AWSRequest(method="GET", url=endpoint)
            SigV4QueryAuth(s.session.get_credentials().get_frozen_credentials(), "bedrock-agentcore", s.region, expires=60).add_auth(req)
            r = requests.get(req.url, timeout=30)
            assert r.status_code in (200, 101), {"status": r.status_code, "body": r.text[:1000]}
            return {"httpStatus": r.status_code, "contentType": r.headers.get("content-type"), "bodyPrefix": r.text[:200],
                    "scope": "authenticated endpoint; visual DCV rendering requires separate client"}
        s.test("browser.live_view.presigned_access", live_view)

        profile = s.test("browser.profile.create", lambda: c.create_browser_profile(name=s.name.replace("-", "_") + "_profile",
                            description="Synthetic browser profile", tags={"Purpose": s.name}))
        if profile:
            pid = profile["profileId"]
            s.resource("profile", pid)
            s.test("browser.profile.get", lambda: c.get_browser_profile(profileId=pid))
            s.test("browser.profile.list", lambda: c.list_browser_profiles(maxResults=1))
            s.test("browser.profile.save", lambda: rt.save_browser_session_profile(profileIdentifier=pid, **ident))
            restored = s.test("browser.profile.restore_start", lambda: start(s, profileConfiguration={"profileIdentifier": pid}))
            if restored:
                def check_restored():
                    br = connect(s, pw, restored)
                    ctx = br.contexts[0]
                    pg = ctx.new_page()
                    pg.goto(url)
                    cookies = ctx.cookies()
                    assert any(x["name"] == "cn_test" and x["value"] == "persist-ok" for x in cookies), cookies
                    value = pg.evaluate("localStorage.getItem('cn_test')")
                    assert value == "local-ok", value
                    br.close()
                    return {"cookieRestored": True, "localStorageRestored": True}
                s.test("browser.profile.cookies_local_storage_restored", check_restored)
                s.test("browser.profile.session_stop", lambda: stop(s, restored))
        fresh = s.test("browser.isolation.concurrent_start", lambda: start(s))
        if fresh:
            def isolation():
                br = connect(s, pw, fresh)
                ctx = br.contexts[0]
                pg = ctx.new_page()
                pg.goto(url)
                assert not any(x["name"] == "cn_test" for x in ctx.cookies())
                assert pg.evaluate("localStorage.getItem('cn_test')") is None
                br.close()
                return {"cookiesIsolated": True, "localStorageIsolated": True}
            s.test("browser.isolation.cookies_local_storage", isolation)
            s.test("browser.isolation.stop", lambda: stop(s, fresh))
        browser.close()
        s.test("browser.stream.disable", lambda: rt.update_browser_stream(**ident, streamUpdate={"automationStreamUpdate": {"streamStatus": "DISABLED"}}))
        def disabled():
            try:
                br = connect(s, pw, initial)
            except Exception as e:
                assert any(x in str(e) for x in ["403", "409", "423", "disabled", "DISABLED"]), str(e)
                return {"rejected": True, "error": str(e)[:500]}
            br.close()
            raise AssertionError("CDP accepted a connection while automation disabled")
        s.test("browser.stream.disabled_enforced", disabled)
        s.test("browser.stream.enable", lambda: rt.update_browser_stream(**ident, streamUpdate={"automationStreamUpdate": {"streamStatus": "ENABLED"}}))
        def enabled():
            br = connect(s, pw, initial)
            br.close()
            return "CDP reconnected"
        s.test("browser.stream.reenabled_connect", enabled)
        s.test("browser.managed.stop", lambda: stop(s, initial))
        s.test("browser.session.stopped_status", lambda: rt.get_browser_session(**ident))

    custom(s)


def assert_value(actual, expected):
    assert actual == expected, {"actual": actual, "expected": expected}
    return actual


def custom(s):
    c = s.control
    bucket = s.state["bucket"]
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("manifest.json", json.dumps({"manifest_version": 3, "name": "China Test Extension", "version": "1.0",
            "content_scripts": [{"matches": ["https://*/*"], "js": ["content.js"]}]}))
        f.writestr("content.js", "document.documentElement.setAttribute('data-cn-extension','loaded');")
    s.client("s3").put_object(Bucket=bucket, Key="extension.zip", Body=z.getvalue(), ContentType="application/zip")
    s.client("s3").put_object(Bucket=bucket, Key="managed.json", Body=json.dumps({"URLBlocklist": ["*://blocked.agentcore.test/*"],
                                        "PasswordManagerEnabled": False}), ContentType="application/json")
    s.client("s3").put_object(Bucket=bucket, Key="recommended.json", Body=json.dumps({"BookmarkBarEnabled": True}), ContentType="application/json")
    custom = c.get_browser(browserId=s.state["custom_browser"]) if "custom_browser" in s.state else s.test("browser.custom.create_recording_managed_policies", lambda: c.create_browser(
        name=s.name.replace("-", "_") + "_custom", executionRoleArn=s.state["agentcore_role"],
        networkConfiguration={"networkMode": "PUBLIC"}, recording={"enabled": True, "s3Location": {"bucket": bucket, "prefix": "recordings/"}},
        enterprisePolicies=[{"type": "MANAGED", "location": {"s3": {"bucket": bucket, "prefix": "managed.json"}}}],
        tags={"Purpose": s.name}))
    if not custom:
        return
    bid = custom["browserId"]
    if not any(x["kind"] == "browser" and x["id"] == bid for x in s.state["resources"]):
        s.resource("browser", bid)
    s.state["custom_browser"] = bid
    s.save()
    s.test("browser.custom.get_ready", lambda: s.wait(lambda: c.get_browser(browserId=bid)))
    arn = custom["browserArn"]
    s.test("browser.tags.add", lambda: c.tag_resource(resourceArn=arn, tags={"Feature": "browser"}))
    s.test("browser.tags.list", lambda: c.list_tags_for_resource(resourceArn=arn))
    s.test("browser.tags.remove", lambda: c.untag_resource(resourceArn=arn, tagKeys=["Feature"]))
    r = s.test("browser.custom.start_extensions_recommended_policy", lambda: start(s, bid,
        extensions=[{"location": {"s3": {"bucket": bucket, "prefix": "extension.zip"}}}],
        enterprisePolicies=[{"type": "RECOMMENDED", "location": {"s3": {"bucket": bucket, "prefix": "recommended.json"}}}]))
    if not r:
        return
    with sync_playwright() as pw:
        br = connect(s, pw, r)
        pg = br.contexts[0].new_page()
        pg.goto(s.state["page_url"], timeout=60000)
        s.test("browser.extensions.executed", lambda: assert_value(pg.locator("html").get_attribute("data-cn-extension"), "loaded"))
        pg.locator("#name").fill("recorded-session")
        pg.locator("#submit").click()
        def managed():
            try:
                pg.goto("https://blocked.agentcore.test/page", timeout=15000)
            except Exception as e:
                assert "ERR_BLOCKED_BY_ADMINISTRATOR" in str(e), str(e)
                return {"blockedByPolicy": True}
            raise AssertionError("Managed URLBlocklist not enforced")
        s.test("browser.enterprise.managed_enforced", managed)
        def policies():
            pg.goto("chrome://policy")
            text = pg.locator("body").inner_text()
            # Chromium policy UI uses shadow DOM; Playwright's text locators pierce it.
            all_text = pg.evaluate("""() => { const walk=n=>Array.from(n.querySelectorAll('*')).map(x=>(x.shadowRoot?walk(x.shadowRoot):'')+' '+(x.textContent||'')).join(' '); return walk(document); }""")
            assert "BookmarkBarEnabled" in all_text and "PasswordManagerEnabled" in all_text, all_text[:1000]
            return {"managedAndRecommendedPresent": True}
        s.test("browser.enterprise.recommended_loaded", policies)
        br.close()
    s.test("browser.custom.stop", lambda: stop(s, r))
    def recording():
        deadline = time.monotonic() + 120
        while True:
            objects = s.client("s3").list_objects_v2(Bucket=bucket, Prefix="recordings/").get("Contents", [])
            if objects:
                return [{"key": x["Key"], "bytes": x["Size"]} for x in objects]
            if time.monotonic() > deadline:
                raise AssertionError("No recording objects delivered to S3 within 120 seconds")
            time.sleep(5)
    s.test("browser.recording.s3_delivery", recording)
