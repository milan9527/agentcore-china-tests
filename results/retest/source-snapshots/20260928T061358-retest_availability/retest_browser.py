import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4QueryAuth
from suite import ROOT, RESULTS
from browser_tests import connect, stop

HTML = """<html><head><title>Retest China</title></head><body style="margin:0">
<input id="name" autofocus style="position:absolute;left:40px;top:80px;width:500px;height:50px;font:24px sans-serif">
<h1 style="position:absolute;top:180px">AgentCore live-view retest 中国区</h1>
<a style="position:absolute;top:250px" id="download" download="retest.txt" href="data:text/plain,agentcore-download-ok">Download</a>
</body></html>"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def run(s):
    session = s.runtime.start_browser_session(browserIdentifier="aws.browser.v1", name="followup",
        sessionTimeoutSeconds=900, viewPort={"width":1280,"height":720})
    s.state["sessions"].append({"browser": "aws.browser.v1", "id": session["sessionId"]})
    s.save()
    try:
        with sync_playwright() as pw:
            browser = connect(s,pw,session)
            for context_mode in ["default","new"]:
                context = browser.contexts[0] if context_mode=="default" else browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_content(HTML)
                def download():
                    with page.expect_download() as pending:
                        page.locator("#download").click()
                    item = pending.value
                    dest = RESULTS/f"{s.region}-download-{context_mode}.txt"
                    item.save_as(str(dest))
                    evidence = {"bytes":len(dest.read_bytes()),"failure":item.failure(),"suggestedFilename":item.suggested_filename,
                                "remoteBrowser":browser.version,"context":context_mode}
                    assert dest.read_bytes()==b"agentcore-download-ok", evidence
                    return evidence
                s.test("browser.download.save_as."+context_mode,download)
                page.close()
                if context_mode=="new":context.close()
            page=browser.contexts[0].new_page()
            page.set_content(HTML)
            page.bring_to_front()
            s.test("browser.live_view.official_component",lambda:live(s,pw,session,page))
            browser.close()
            local=pw.chromium.launch(headless=True)
            pg=local.new_page(accept_downloads=True);pg.set_content(HTML)
            def baseline():
                with pg.expect_download() as pending:pg.locator("#download").click()
                dest=RESULTS/f"{s.region}-download-local.txt";pending.value.save_as(str(dest))
                assert dest.read_bytes()==b"agentcore-download-ok"
                return {"bytes":dest.stat().st_size,"localBrowser":local.version}
            s.test("browser.download.local_baseline",baseline)
            local.close()
    finally:
        stop(s,session)


def live(s,pw,session,remote):
    server=ThreadingHTTPServer(("127.0.0.1",0),functools.partial(Quiet,directory=str(ROOT/"retest-viewer")))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    local=pw.chromium.launch(headless=True,executable_path="/home/ec2-user/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell")
    viewer=local.new_page(viewport={"width":1280,"height":720})
    errors=[]
    def safe(url):
        p=urlsplit(url);return p.scheme+"://"+p.netloc+p.path
    viewer.on("pageerror",lambda e:errors.append(str(e)[:400]))
    viewer.on("websocket",lambda ws:ws.on("socketerror",lambda e:errors.append({"url":safe(ws.url),"error":str(e)})))
    try:
        viewer.goto(f"http://127.0.0.1:{server.server_port}")
        endpoint=session["streams"]["liveViewStream"]["streamEndpoint"]
        req=AWSRequest(method="GET",url=endpoint)
        SigV4QueryAuth(s.session.get_credentials().get_frozen_credentials(),"bedrock-agentcore",s.region,expires=300).add_auth(req)
        viewer.evaluate("url=>renderLive(url)",req.url)
        try:viewer.wait_for_function("probe.firstFrame || probe.errors.length>0",timeout=45000)
        except Exception:pass
        evidence=viewer.evaluate("probe");evidence["clientErrors"]=errors
        if evidence["firstFrame"]:
            remote.locator("#name").focus()
            viewer.mouse.click(170,105)
            viewer.keyboard.type("dcv-official-input-ok",delay=30)
            remote.wait_for_timeout(1000)
            evidence["remoteInput"]=remote.locator("#name").input_value()
            viewer.screenshot(path=str(RESULTS/f"{s.region}-official-live.png"))
            assert evidence["remoteInput"]=="dcv-official-input-ok",evidence
        assert evidence["firstFrame"],evidence
        return evidence
    finally:
        local.close();server.shutdown()
