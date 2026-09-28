from playwright.sync_api import sync_playwright
from browser_tests import start, stop, connect
from browser_more_tests import live


def run(s):
    r = start(s)
    try:
        with sync_playwright() as pw:
            br = connect(s, pw, r)
            pg = br.contexts[0].new_page()
            pg.goto(s.state["page_url"])
            pg.locator("#name").fill("Live view China")
            pg.locator("#submit").click()
            pg.bring_to_front()
            s.test("browser.live_view.dcv_frame_and_input", lambda: live(s, pw, r, pg))
            br.close()
    finally:
        stop(s, r)
