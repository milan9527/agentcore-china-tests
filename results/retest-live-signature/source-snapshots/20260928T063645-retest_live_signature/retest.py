"""Isolated follow-up run. Original inventories remain owned by their cleanup worker."""
import argparse
import concurrent.futures
import importlib
import os
import datetime as dt
import hashlib
import json
import shutil
import threading
import requests
from urllib.parse import parse_qs
from pathlib import Path
import suite
from export_report import sanitize, SECRET_KEYS

SECRET_KEYS.update({"secretstring","secretbinary","client_secret","rsa_key","userdata","zipfile",
    "usertoken","workloadidentitytoken","workloadaccesstoken","authorizationcode","codeverifier",
    "code_verifier","subject_token","actor_token","authorizationurl","sessionuri","authcode"})

suite.RESULTS = Path(os.environ.get("RETEST_RESULTS_DIR", str(Path(__file__).parent / "results" / "retest")))
suite.RESULTS.mkdir(parents=True, exist_ok=True)
AUDIT_CONTEXT=threading.local()
ORIGINAL_SEND=requests.sessions.Session.send


def traced_send(session,request,**kwargs):
    callback=getattr(AUDIT_CONTEXT,"callback",None)
    body=request.body
    if isinstance(body,bytes):
        try:body=body.decode()
        except UnicodeDecodeError:body={"bytes":len(body)}
    if isinstance(body,str):
        try:body=json.loads(body)
        except ValueError:
            if "application/x-www-form-urlencoded" in request.headers.get("Content-Type",""):
                body={k:("REDACTED" if k in {"code","state"} else v[0]) for k,v in parse_qs(body).items()}
    if callback:callback({"event":"http_request","method":request.method,"url":request.url,
        "headers":dict(request.headers),"body":body})
    response=ORIGINAL_SEND(session,request,**kwargs)
    if callback:
        parsed=None
        if not kwargs.get("stream"):
            try:parsed=response.json()
            except ValueError:parsed=response.text[:1500]
        callback({"event":"http_response","url":response.url,"status":response.status_code,
                  "headers":{k:v for k,v in response.headers.items() if k.lower() in
                             ["content-type","x-amzn-requestid","location"]},"body":parsed})
    return response


class Retest(suite.Suite):
    def save(self):
        if os.environ.get("RETEST_STATE_READ_ONLY") != "1":
            super().save()

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.audit_lock=threading.Lock()
        def before_call(model,params,**_):
            body=params.get("body")
            if isinstance(body,bytes):
                try:body=json.loads(body)
                except (ValueError,UnicodeDecodeError):body={"bytes":len(body)}
            elif not isinstance(body,(dict,list,str,int,float,type(None))):
                body={"type":type(body).__name__}
            self.audit({"event":"request","service":model.service_model.service_name,"operation":model.name,
                        "body":body,"url":params.get("url")})
        def after_call(model,http_response,parsed,**_):
            self.audit({"event":"response","service":model.service_model.service_name,"operation":model.name,
                        "status":http_response.status_code,"parsed":parsed})
        self.session.events.register("before-call.*.*",before_call)
        self.session.events.register("after-call.*.*",after_call)
        # Already-created control/runtime/STS clients predate the session event registration.
        for client in self.clients.values():
            client.meta.events.register("before-call.*.*",before_call)
            client.meta.events.register("after-call.*.*",after_call)

    def audit(self,entry):
        row={"time":dt.datetime.now(dt.timezone.utc).isoformat(),"region":self.region,**entry}
        with self.audit_lock,(suite.RESULTS/f"{self.region}-api-audit.jsonl").open("a") as stream:
            stream.write(json.dumps(sanitize(row),default=suite.serial)+"\n")

    def record(self, feature, status, evidence=None, started=None):
        return super().record(feature, status, sanitize(evidence), started)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase")
    p.add_argument("--region", choices=suite.REGIONS)
    args = p.parse_args()
    requests.sessions.Session.send=traced_send
    stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+args.phase
    snapshot=suite.RESULTS/"source-snapshots"/stamp
    snapshot.mkdir(parents=True,exist_ok=True)
    manifest={}
    root=Path(__file__).parent
    files=list(root.glob("*.py"))+[root/"requirements.txt",root/"requirements-followup.lock.txt",
          root/"requirements-pw148.lock.txt",root/"retest-viewer/package-lock.json",root/"retest-viewer/package.json",
          root/"retest-viewer/index.html",root/"retest-viewer/main.jsx",root/"retest-viewer/build.mjs",root/"retest-viewer/dcv-probe.js"]
    for source in files:
        if source.exists():
            relative=source.relative_to(root);dest=snapshot/relative
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
            manifest[str(relative)]=hashlib.sha256(source.read_bytes()).hexdigest()
    (snapshot/"manifest.json").write_text(json.dumps({"phase":args.phase,"region":args.region,
        "environment":{k:os.environ.get(k) for k in ["RETEST_RESULTS_DIR","RETEST_STATE_READ_ONLY","PYTHONPATH","PROXY_MODES",
            "STANDARD_PROXY_MODES","LOCAL_CHROMIUM_EXECUTABLE","CLEANUP_SG_WAIT_SECONDS","LIVE_WAIT_SECONDS"]},
        "python":os.sys.version,"files":manifest},indent=2))
    module = importlib.import_module(args.phase)
    def run(region):
        s = Retest(region)
        AUDIT_CONTEXT.callback=s.audit
        s.test(args.phase + ".suite", lambda: module.run(s))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [args.region] if args.region else suite.REGIONS))


if __name__ == "__main__":
    main()
