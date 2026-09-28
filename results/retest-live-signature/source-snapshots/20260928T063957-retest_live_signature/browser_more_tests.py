import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from browser_tests import start, stop, connect, custom
from suite import ROOT, RESULTS


def run(s):
    s.test("browser.custom.features", lambda: custom(s))
    r = start(s)
    try:
        with sync_playwright() as pw:
            br = connect(s, pw, r)
            ctx = br.contexts[0]
            pg = ctx.new_page()
            pg.goto(s.state["page_url"])
            pg.locator("#name").fill("Live view China")
            pg.locator("#submit").click()
            def download_remote():
                cdp = ctx.new_cdp_session(pg)
                cdp.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": "/tmp/cn-downloads", "eventsEnabled": True})
                events = []
                cdp.on("Browser.downloadProgress", lambda x: events.append(x))
                pg.locator("#download").click()
                pg.wait_for_timeout(2000)
                check = ctx.new_page()
                check.goto("file:///tmp/cn-downloads/agentcore-test.txt")
                text = check.locator("body").inner_text()
                assert text == "agentcore-download-ok", {"content": text}
                check.close()
                return {"remoteContent": text, "progress": events}
            s.test("browser.file_download", download_remote)
            def download_retrieve():
                with pg.expect_download() as event:
                    pg.locator("#download").click()
                d = event.value
                p = RESULTS / f"{s.region}-download-save-as.txt"
                d.save_as(str(p))
                raw = p.read_bytes()
                assert raw == b"agentcore-download-ok", {"downloadedBytes": len(raw), "expectedBytes": 21, "name": d.suggested_filename}
                return {"downloadedBytes": len(raw)}
            s.test("browser.download.playwright_save_as", download_retrieve)
            pg.bring_to_front()
            s.test("browser.live_view.dcv_frame_and_input", lambda: live(s, pw, r, pg))
            br.close()
    finally:
        stop(s, r)
    def ttl():
        r = s.runtime.start_browser_session(browserIdentifier="aws.browser.v1", name="ttl_test", sessionTimeoutSeconds=60)
        s.state["sessions"].append({"browser": "aws.browser.v1", "id": r["sessionId"]})
        s.save()
        s.state["ttl_session"] = {"id": r["sessionId"], "started": time.time()}
        s.save()
        return {"sessionId": r["sessionId"], "timeoutSeconds": 60}
    s.test("browser.ttl.short_session", ttl)


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def live(s, pw, session, remote_page):
    handler = functools.partial(Quiet, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    local = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    viewer = local.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    network_errors = []
    viewer.on("pageerror", lambda e: errors.append(str(e)[:500]))
    from urllib.parse import urlsplit
    def safe_url(url):
        u = urlsplit(url)
        return u.scheme + "://" + u.netloc + u.path
    viewer.on("requestfailed", lambda r: network_errors.append({"url": safe_url(r.url), "error": r.failure}))
    viewer.on("response", lambda r: network_errors.append({"url": safe_url(r.url), "status": r.status}) if r.status >= 400 else None)
    viewer.on("websocket", lambda ws: ws.on("socketerror", lambda e: network_errors.append({"url": safe_url(ws.url), "error": str(e)})))
    try:
        viewer.goto(f"http://127.0.0.1:{server.server_port}/dcv/README.md")
        viewer.set_content('<html><body style="margin:0"><div id="dcv-display" style="width:1280px;height:720px"></div></body></html>')
        viewer.add_script_tag(url=f"http://127.0.0.1:{server.server_port}/dcv/dcv.js")
        endpoint = session["streams"]["liveViewStream"]["streamEndpoint"]
        req = AWSRequest(method="GET", url=endpoint)
        SigV4QueryAuth(s.session.get_credentials().get_frozen_credentials(), "bedrock-agentcore", s.region, expires=300).add_auth(req)
        viewer.evaluate("""url => {
          window.cnDcv = {firstFrame:false, connected:false, errors:[]};
          const params = () => new URL(url).searchParams;
          dcv.setLogLevel(dcv.LogLevel.ERROR);
          dcv.authenticate(url, {
            promptCredentials: () => cnDcv.errors.push("Unexpected credential challenge"),
            error: (_,e) => cnDcv.errors.push(String(e.message || e)),
            httpExtraSearchParams: params,
            success: (_,result) => {
              cnDcv.authenticated = true;
              cnDcv.authResultKeys = Object.keys(result[0] || {});
              dcv.connect({
                url:new URL(url).origin+new URL(url).pathname, sessionId:result[0].sessionId, authToken:result[0].authToken, divId:"dcv-display",
                callbacks:{firstFrame:()=>cnDcv.firstFrame=true, httpExtraSearchParams:params}
              }).then(conn => { window.cnConnection=conn; cnDcv.connected=true; })
                .catch(e=>cnDcv.errors.push(String(e.message || e)));
            }
          });
        }""", req.url)
        try:
            viewer.wait_for_function("cnDcv.firstFrame || cnDcv.errors.length > 0", timeout=60000)
        except Exception:
            pass
        evidence = viewer.evaluate("cnDcv")
        evidence["pageErrors"] = errors
        evidence["networkErrors"] = network_errors
        if evidence.get("authenticated"):
            s.record("browser.live_view.presigned_access", "PASS", {"dcvAuthenticated": True})
        assert evidence["firstFrame"], evidence
        p = RESULTS / f"{s.region}-live-view.png"
        viewer.screenshot(path=str(p))
        # Exercise human input through DCV, then inspect the remote DOM through CDP.
        viewer.mouse.click(100, 111)
        viewer.keyboard.press("Control+a")
        viewer.keyboard.type("dcv-input-ok", delay=30)
        remote_page.wait_for_timeout(1000)
        evidence["inputValue"] = remote_page.locator("#name").input_value()
        evidence["screenshot"] = str(p)
        evidence["inputVerified"] = evidence["inputValue"] == "dcv-input-ok"
        s.record("browser.live_view.presigned_access", "PASS", {"dcvAuthenticated": True, "firstFrame": True})
        s.record("browser.live_view.input", "PASS" if evidence["inputVerified"] else "FAIL", {"actual": evidence["inputValue"]})
        return evidence
    finally:
        local.close()
        server.shutdown()
