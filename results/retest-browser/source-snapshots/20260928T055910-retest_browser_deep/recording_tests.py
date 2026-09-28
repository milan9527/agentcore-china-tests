import functools
import gzip
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
from playwright.sync_api import sync_playwright
from suite import ROOT, RESULTS


def sanitize(value):
    if isinstance(value, dict):
        return {k: ("REDACTED" if k.lower() in ["authorization", "proxy-authorization", "x-amz-security-token"] else sanitize(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(X-Amz-(?:Signature|Credential|Security-Token)=)[^&\s\"'<>]+", r"\1REDACTED", value)
    return value


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def run(s):
    s3 = s.client("s3")
    objects = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=s.state["bucket"], Prefix="recordings/"):
        objects.extend(page.get("Contents", []))
    batches = [x for x in objects if x["Key"].endswith(".ndjson.gz")]
    assert batches, "No recorded event batches"
    sessions = sorted({x["Key"].split("/")[1] for x in batches}, reverse=True)
    chosen = None
    for session in sessions:
        events = []
        for obj in sorted([x for x in batches if x["Key"].split("/")[1] == session], key=lambda x: x["Key"]):
            raw = s3.get_object(Bucket=s.state["bucket"], Key=obj["Key"])["Body"].read()
            events.extend(json.loads(line) for line in gzip.decompress(raw).decode().splitlines() if line)
        events.sort(key=lambda x: x["timestamp"])
        snapshots = [x for x in events if x.get("type") == 2 and "AgentCore China feature test" in json.dumps(x)]
        if snapshots:
            chosen = session, events, snapshots[0]
            break
    assert chosen, {"recordedSessions": sessions, "fullSnapshotOfTestPage": False}
    session, events, snapshot = chosen
    s.record("browser.recording.s3_delivery", "PASS", {"recordedSession": session,
        "batchCount": len(batches), "eventCount": len(events), "snapshotCount": sum(x["type"] == 2 for x in events)})
    events = sanitize(events)
    offset = snapshot["timestamp"] - events[0]["timestamp"] + 10
    payload = json.dumps(events).replace("</script", "<\\/script")
    vendor = (ROOT / "docs/rrweb-all.js").read_text()
    vendor = vendor.rsplit("export {", 1)[0] + "\nwindow.rrweb={Replayer};"
    title = "Beijing" if s.region == "cn-north-1" else "Ningxia"
    html = """<!doctype html><html><head><meta charset="utf-8"><title>AgentCore session replay — REGION</title>
<style>body{font:14px system-ui;margin:16px;background:#edf1f5}button{margin-right:8px;padding:8px 16px}#view{background:white;margin-top:15px;width:1280px;overflow:hidden}input{width:700px}.replayer-wrapper{position:relative}.replayer-mouse{display:none}.replayer-mouse-tail{display:none!important}</style></head>
<body><h2>AgentCore Browser session replay — REGION</h2><button id="play">Play</button><button id="pause">Pause</button>
<input id="seek" type="range" min="0" value="0"><span id="time"></span><div id="view"></div>
<script>VENDOR</script><script>
const events=EVENTS;
window.replayer=new rrweb.Replayer(events,{root:document.querySelector('#view'),showWarning:false,skipInactive:true});
const seek=document.querySelector('#seek');seek.max=replayer.getMetaData().totalTime;
seek.value=OFFSET;replayer.pause(OFFSET);
seek.oninput=()=>{replayer.pause(Number(seek.value));document.querySelector('#time').textContent=(seek.value/1000).toFixed(1)+'s';};
document.querySelector('#play').onclick=()=>replayer.play(Number(seek.value));
document.querySelector('#pause').onclick=()=>replayer.pause();
</script></body></html>"""
    html = html.replace("REGION", title).replace("VENDOR", vendor).replace("EVENTS", payload).replace("OFFSET", str(offset))
    artifact = RESULTS / f"{s.region}-replay.html"
    artifact.write_text(html)
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(RESULTS)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            pg = br.new_page(viewport={"width": 1320, "height": 900})
            pg.route("**/*", lambda route: route.continue_() if route.request.url.startswith("http://127.0.0.1:") else route.abort())
            pg.goto(f"http://127.0.0.1:{server.server_port}/{artifact.name}", wait_until="domcontentloaded")
            pg.wait_for_timeout(2000)
            texts = [f.locator("body").inner_text() for f in pg.frames]
            assert any("AgentCore China feature test" in text for text in texts[1:]), {"replayFrames": len(pg.frames)}
            pg.screenshot(path=str(RESULTS / f"{s.region}-replay.png"))
            br.close()
    finally:
        server.shutdown()
    s.record("browser.recording.replay", "PASS", {"artifact": str(artifact), "eventCount": len(events), "replayedTestPage": True})
