import json
import time
from playwright.sync_api import sync_playwright
from browser_tests import start, stop, connect
from browser_more_tests import live
from suite import RESULTS


def run(s):
    s.test("browser.enterprise.policies", lambda: policies(s))
    r = start(s)
    try:
        with sync_playwright() as pw:
            br = connect(s, pw, r)
            pg = br.contexts[0].new_page()
            pg.goto(s.state["page_url"])
            pg.locator("#name").fill("Live view China")
            pg.locator("#submit").click()
            s.test("browser.live_view.dcv_frame_and_input", lambda: live(s, pw, r, pg))
            br.close()
    finally:
        stop(s, r)


def policies(s):
    bucket = s.state["bucket"]
    s.client("s3").put_object(Bucket=bucket, Key="managed-fixed.json",
        Body=json.dumps({"URLBlocklist": ["blocked.agentcore.test"], "PasswordManagerEnabled": False}),
        ContentType="application/json")
    r = s.control.create_browser(name=s.name.replace("-", "_") + "_policy",
        executionRoleArn=s.state["agentcore_role"], networkConfiguration={"networkMode": "PUBLIC"},
        enterprisePolicies=[{"type": "MANAGED", "location": {"s3": {"bucket": bucket, "prefix": "managed-fixed.json"}}}])
    s.resource("browser", r["browserId"])
    s.wait(lambda: s.control.get_browser(browserId=r["browserId"]))
    session = start(s, r["browserId"], enterprisePolicies=[{"type": "RECOMMENDED",
        "location": {"s3": {"bucket": bucket, "prefix": "recommended.json"}}}])
    try:
        with sync_playwright() as pw:
            br = connect(s, pw, session)
            ctx = br.contexts[0]
            def page_policy():
                pg = ctx.new_page()
                try:
                    pg.goto("chrome://policy", timeout=20000)
                    text = pg.evaluate("""() => { const walk=n=>Array.from(n.querySelectorAll('*')).map(x=>(x.shadowRoot?walk(x.shadowRoot):'')+' '+(x.textContent||'')).join(' '); return walk(document); }""")
                    (RESULTS / f"{s.region}-chrome-policy.txt").write_text(text)
                    pg.screenshot(path=str(RESULTS / f"{s.region}-chrome-policy.png"))
                    assert all(x in text for x in ["URLBlocklist", "PasswordManagerEnabled", "BookmarkBarEnabled"]), text[:1500]
                    return {"managedAndRecommendedPresent": True}
                finally:
                    pg.close()
            s.test("browser.enterprise.recommended_loaded", page_policy)
            def enforced():
                pg = ctx.new_page()
                try:
                    try:
                        pg.goto("https://blocked.agentcore.test/page", timeout=20000)
                    except Exception as e:
                        assert "ERR_BLOCKED_BY_ADMINISTRATOR" in str(e), str(e)
                        return {"blockedByAdministrator": True}
                    raise AssertionError("URLBlocklist did not block the test domain")
                finally:
                    pg.close()
            s.test("browser.enterprise.managed_enforced", enforced)
            br.close()
    finally:
        stop(s, session)
    return {"browserId": r["browserId"]}
