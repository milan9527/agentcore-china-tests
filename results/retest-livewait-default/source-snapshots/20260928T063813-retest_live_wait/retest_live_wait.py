"""Observe DCV for five minutes despite errors, then retry with a fresh signature."""
import datetime as dt
import functools
import importlib.metadata
import json
import os
from pathlib import Path
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from playwright.sync_api import sync_playwright

from browser_tests import connect, stop
from export_report import sanitize
from retest_browser import HTML, Quiet
from suite import ROOT, RESULTS


def clean_url(url):
    parts = urlsplit(url)
    return parts.scheme + "://" + parts.netloc + parts.path


def run(s):
    seconds = int(os.environ.get("LIVE_WAIT_SECONDS", "300"))
    expiry = int(os.environ.get("LIVE_SIGNATURE_SECONDS", "300"))
    assert 60 <= seconds <= 600, "Observe 60–600 seconds per attempt"
    assert 60 <= expiry <= 900, "Sign for 60–900 seconds"
    created = time.monotonic()
    session = s.runtime.start_browser_session(
        browserIdentifier="aws.browser.v1", name="live_view_extended_wait",
        sessionTimeoutSeconds=1800, viewPort={"width": 1280, "height": 720})
    s.state["sessions"].append({"browser": session["browserIdentifier"], "id": session["sessionId"]})
    s.save()
    server = ThreadingHTTPServer(("127.0.0.1", 0),
        functools.partial(Quiet, directory=str(ROOT / "retest-viewer")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    output = RESULTS / f"{s.region}-live-wait-events.jsonl"
    started = time.monotonic()
    attempt = "setup"

    def event(kind, **details):
        row = sanitize({"time": dt.datetime.now(dt.timezone.utc).isoformat(), "region": s.region,
            "sessionId": session["sessionId"], "attempt": attempt,
            "runElapsedSeconds": round(time.monotonic() - started, 3), "event": kind, **details})
        with output.open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    executable = os.environ.get("LOCAL_CHROMIUM_EXECUTABLE")
    if not executable:
        shells = list((Path.home() / ".cache/ms-playwright").glob(
            "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
        executable = str(max(shells, key=lambda p: int(p.parents[1].name.rsplit("-", 1)[-1]))) if shells else None
    try:
        with sync_playwright() as pw:
            remote_browser = connect(s, pw, session)
            remote = remote_browser.contexts[0].new_page()
            remote.set_content(HTML)
            remote.evaluate("""() => {
              const clock=document.createElement('p');
              clock.id='remote-clock'; clock.style='position:absolute;top:350px;font:32px sans-serif';
              document.body.append(clock);
              setInterval(()=>clock.textContent=new Date().toISOString(),1000);
            }""")
            remote.bring_to_front()
            local = pw.chromium.launch(headless=True,
                **({"executable_path": executable} if executable else {}))
            event("environment", playwright=importlib.metadata.version("playwright"),
                localChromium=local.version, remoteChromium=remote_browser.version,
                observationSecondsPerAttempt=seconds, sessionTimeoutSeconds=1800,
                signatureExpirySeconds=expiry, executable=executable)
            try:
                for attempt in ("initial_5min", "fresh_signature_retry_5min"):
                    context = local.new_context(viewport={"width": 1280, "height": 720})
                    viewer = context.new_page()
                    network = []
                    ws_counts = {"opened": 0, "closed": 0, "errors": 0, "receivedFrames": 0, "receivedBytes": 0}
                    def network_event(kind, **details):
                        item = {"event": kind, **details}
                        network.append(item)
                        event(kind, **details)
                    def websocket(ws):
                        url = clean_url(ws.url)
                        ws_counts["opened"] += 1
                        network_event("websocket.opened", url=url)
                        def received(payload):
                            ws_counts["receivedFrames"] += 1
                            ws_counts["receivedBytes"] += len(payload if isinstance(payload, bytes) else payload.encode())
                        def closed():
                            ws_counts["closed"] += 1
                            network_event("websocket.closed", url=url)
                        def error(message):
                            ws_counts["errors"] += 1
                            network_event("websocket.error", url=url, message=str(message))
                        ws.on("framereceived", received)
                        ws.on("close", closed)
                        ws.on("socketerror", error)
                    viewer.on("websocket", websocket)
                    viewer.on("pageerror", lambda error: network_event("page.error", message=str(error)[:500]))
                    viewer.on("requestfailed", lambda req: network_event(
                        "request.failed", url=clean_url(req.url), failure=req.failure))
                    cdp = context.new_cdp_session(viewer)
                    cdp.send("Network.enable")
                    cdp.on("Network.webSocketHandshakeResponseReceived", lambda data: network_event(
                        "websocket.handshake", status=data["response"]["status"],
                        requestId=data["requestId"]))
                    try:
                        remote.locator("#name").fill("")
                        remote.bring_to_front()
                        viewer.goto(f"http://127.0.0.1:{server.server_port}")
                        request = AWSRequest(method="GET", url=session["streams"]["liveViewStream"]["streamEndpoint"])
                        SigV4QueryAuth(s.session.get_credentials().get_frozen_credentials(),
                            "bedrock-agentcore", s.region, expires=expiry).add_auth(request)
                        begin = time.monotonic()
                        event("attempt.start", observationSeconds=seconds,
                            sessionAgeSeconds=round(begin - created, 3), signatureExpirySeconds=expiry)
                        viewer.evaluate("url=>renderLive(url)", request.url)
                        seen = 0
                        heartbeat = 0
                        input_checked = False
                        input_ok = False
                        health = []
                        # Deliberately do not stop when the SDK reports an error.
                        while True:
                            elapsed = time.monotonic() - begin
                            probe = viewer.evaluate("probe")
                            for entry in probe["events"][seen:]:
                                event("sdk.event", sdk=entry)
                            seen = len(probe["events"])
                            if elapsed >= heartbeat:
                                current = s.runtime.get_browser_session(
                                    browserIdentifier=session["browserIdentifier"], sessionId=session["sessionId"])
                                check = {"elapsedSeconds": round(elapsed, 3), "sessionStatus": current["status"],
                                    "remoteClock": remote.locator("#remote-clock").inner_text(),
                                    "authenticated": probe["authenticated"], "connected": probe["connected"],
                                    "firstFrame": probe["firstFrame"], "errors": probe["errors"],
                                    "websocket": dict(ws_counts)}
                                health.append(check)
                                event("heartbeat", **check)
                                print(f"[{s.region}] {attempt} {elapsed:.0f}s: "
                                    f"auth={probe['authenticated']} connected={probe['connected']} "
                                    f"firstFrame={probe['firstFrame']} session={current['status']}", flush=True)
                                heartbeat += 30
                            if probe["firstFrame"] and not input_checked:
                                input_checked = True
                                viewer.mouse.click(170, 105)
                                viewer.keyboard.type("dcv-extended-wait-ok", delay=40)
                                viewer.wait_for_timeout(1000)
                                value = remote.locator("#name").input_value()
                                input_ok = value == "dcv-extended-wait-ok"
                                event("input.verification", actual=value, passed=input_ok)
                            if elapsed >= seconds:
                                break
                            viewer.wait_for_timeout(min(1000, max(1, int((seconds - elapsed) * 1000))))
                        evidence = {"sessionId": session["sessionId"], "attempt": attempt,
                            "configuredObservationSeconds": seconds, "actualObservationSeconds": round(time.monotonic()-begin, 3),
                            "signatureExpirySeconds": expiry, "sessionTimeoutSeconds": 1800,
                            "sessionAgeAtStartSeconds": round(begin-created, 3),
                            "stoppedEarlyOnError": False, "probe": probe, "websocket": ws_counts,
                            "networkEvents": network, "heartbeats": health, "inputVerified": input_ok,
                            "eventsFile": str(output.relative_to(ROOT))}
                        viewer.screenshot(path=str(RESULTS / f"{s.region}-{attempt}-viewer.png"))
                        remote.screenshot(path=str(RESULTS / f"{s.region}-{attempt}-remote.png"))
                        (RESULTS / f"{s.region}-{attempt}.json").write_text(
                            json.dumps(sanitize(evidence), ensure_ascii=False, indent=2))
                        s.record("browser.live_view.extended_wait." + attempt,
                            "PASS" if probe["firstFrame"] and input_ok else "FAIL", evidence, begin)
                    finally:
                        context.close()
            finally:
                local.close()
                remote_browser.close()
    finally:
        server.shutdown()
        server.server_close()
        result = stop(s, session)
        current = s.runtime.get_browser_session(
            browserIdentifier=session["browserIdentifier"], sessionId=session["sessionId"])
        s.record("cleanup.live_wait_session", "PASS" if current["status"] in
            ("TERMINATED", "STOPPED", "TIMED_OUT") else "FAIL",
            {"sessionId": session["sessionId"], "status": current["status"],
             "requestId": result.get("ResponseMetadata", {}).get("RequestId")})
