"""Compare default signatures on a borrowed active session; creates no cloud resources."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_tests import connect
from retest_browser import live
from suite import ROOT


def run(s):
    original = json.loads((ROOT / "results/retest-livewait" / f"{s.region}-state.json").read_text())
    identity = original["sessions"][-1]
    session = s.runtime.get_browser_session(browserIdentifier=identity["browser"], sessionId=identity["id"])
    with sync_playwright() as pw:
        remote = connect(s, pw, session)
        try:
            page = next(p for p in remote.contexts[0].pages if p.locator("#name").count())
            s.test("browser.live_view.default_signature_control", lambda: live(s, pw, session, page))
        finally:
            remote.close()
