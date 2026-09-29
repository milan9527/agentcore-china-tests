import base64
import hashlib
import secrets
from playwright.sync_api import sync_playwright
from browser_tests import connect,stop
from download_remote_file import read_remote_file
from suite import RESULTS


def run(s):
    session=s.runtime.start_browser_session(browserIdentifier="aws.browser.v1",name="binary_download_followup",
        sessionTimeoutSeconds=300)
    s.state["sessions"].append({"browser":session["browserIdentifier"],"id":session["sessionId"]});s.save()
    try:
        with sync_playwright() as pw:
            browser=connect(s,pw,session);context=browser.contexts[0];page=context.new_page()
            for name,data in [("text.txt",b"agentcore-download-ok"),("binary.bin",bytes(range(256))*32)]:
                def test(filename=name,expected=data):
                    directory="/tmp/cn-binary-"+secrets.token_hex(6)
                    cdp=context.new_cdp_session(page)
                    cdp.send("Browser.setDownloadBehavior",{"behavior":"allow","downloadPath":directory,"eventsEnabled":True})
                    page.set_content('<a id="save" download="'+filename+'" href="data:application/octet-stream;base64,'+
                                     base64.b64encode(expected).decode()+'">Download</a>')
                    page.locator("#save").click();page.wait_for_timeout(1500)
                    actual=read_remote_file(context,directory+"/"+filename)
                    dest=RESULTS/f"{s.region}-retrieved-{filename}";dest.write_bytes(actual)
                    assert actual==expected,{"expectedBytes":len(expected),"actualBytes":len(actual)}
                    return {"bytes":len(actual),"sha256":hashlib.sha256(actual).hexdigest(),"savedFile":str(dest),
                            "method":"DOM.setFileInputFiles + File.arrayBuffer over CDP"}
                s.test("browser.download.remote_file_retrieval."+name,test)
            browser.close()
    finally:stop(s,session)
