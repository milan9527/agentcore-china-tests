import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path
import secrets
from playwright.sync_api import sync_playwright
from browser_tests import connect,stop
from retest_browser import HTML,live
from suite import RESULTS


def run(s):
    session=s.runtime.start_browser_session(browserIdentifier="aws.browser.v1",name="browser_deep",
        sessionTimeoutSeconds=900,viewPort={"width":1280,"height":720})
    s.state["sessions"].append({"browser":session["browserIdentifier"],"id":session["sessionId"]});s.save()
    try:
        with sync_playwright() as pw:
            browser=connect(s,pw,session);context=browser.contexts[0];page=context.new_page()
            page.set_content(HTML)
            def retrieve():
                with page.expect_download() as pending:page.locator("#download").click()
                d=pending.value
                path=Path(d.path());dest=RESULTS/f"{s.region}-deep-download.txt";d.save_as(str(dest))
                evidence={"playwright":importlib.metadata.version("playwright"),"remoteChromium":browser.version,
                    "downloadFailure":d.failure(),"localArtifactExists":path.exists(),
                    "localArtifactBytes":path.stat().st_size if path.exists() else None,"savedBytes":dest.stat().st_size,
                    "artifactPath":str(path)}
                check=context.new_page()
                try:
                    check.goto(path.as_uri());evidence["remoteArtifactContent"]=check.locator("body").inner_text()
                except Exception as e:evidence["remoteArtifactReadError"]=str(e)[:350]
                finally:check.close()
                s.record("browser.download.artifact_diagnostics","INFO",evidence)
                assert dest.read_bytes()==b"agentcore-download-ok",evidence
                return evidence
            s.test("browser.download.compatible_playwright",retrieve)
            def cdp_retrieve():
                destination="/tmp/cn-retest-"+secrets.token_hex(8)
                cdp=context.new_cdp_session(page)
                cdp.send("Browser.setDownloadBehavior",{"behavior":"allow","downloadPath":destination,"eventsEnabled":True})
                page.locator("#download").click();page.wait_for_timeout(1500)
                check=context.new_page()
                # CDP network resource retrieval transfers bytes over the existing authenticated browser connection.
                sid=context.new_cdp_session(check)
                sid.send("Page.enable");sid.send("Network.enable")
                check.goto("file://"+destination+"/retest.txt")
                tree=sid.send("Page.getFrameTree")
                # Page.getResourceContent supports file URLs and returns raw bytes/base64 for binary files.
                result=sid.send("Page.getResourceContent",{"frameId":tree["frameTree"]["frame"]["id"],
                    "url":"file://"+destination+"/retest.txt"})
                raw=base64.b64decode(result["content"]) if result.get("base64Encoded") else result["content"].encode()
                dest=RESULTS/f"{s.region}-cdp-retrieved.txt";dest.write_bytes(raw)
                check.close()
                assert raw==b"agentcore-download-ok",{"bytes":len(raw)}
                return {"downloadedBytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
                        "method":"Page.getResourceContent",
                        "savedFile":str(dest)}
            s.test("browser.download.cdp_file_retrieval",cdp_retrieve)
            page.bring_to_front()
            s.test("browser.live_view.official_component",lambda:live(s,pw,session,page))
            browser.close()
    finally:stop(s,session)
