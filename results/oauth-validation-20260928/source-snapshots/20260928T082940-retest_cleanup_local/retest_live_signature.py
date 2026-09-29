"""Compare default signatures in a separate managed Browser session."""
from playwright.sync_api import sync_playwright
from browser_tests import connect, stop
from retest_browser import live, HTML


def run(s):
    session = s.runtime.start_browser_session(browserIdentifier="aws.browser.v1",
        name="live_signature_control", sessionTimeoutSeconds=900, viewPort={"width":1280,"height":720})
    s.state["sessions"].append({"browser":session["browserIdentifier"],"id":session["sessionId"]})
    s.save()
    try:
        with sync_playwright() as pw:
            remote = connect(s, pw, session)
            try:
                page = remote.contexts[0].new_page()
                page.set_content(HTML)
                page.bring_to_front()
                s.test("browser.live_view.default_signature_control", lambda: live(s, pw, session, page))
            finally:
                remote.close()
    finally:
        stop(s, session)
