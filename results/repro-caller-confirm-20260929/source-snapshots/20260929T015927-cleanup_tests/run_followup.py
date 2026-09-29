"""Execute the follow-up phases in a new inventory, retaining logs and cleaning up."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
from sanitize_evidence import redact_directory

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--results-dir",type=Path,required=True,help="New directory; existing regional state is rejected")
    args=p.parse_args()
    output=args.results_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    if list(output.glob("*-state.json")):
        p.error("Use a new results directory to avoid mixing resources from different runs")
    env={**os.environ,"RETEST_RESULTS_DIR":str(output),"VERIFY_RESULTS_DIR":str(output)}
    env.pop("RETEST_STATE_READ_ONLY",None)
    env.pop("PROXY_MODES",None)
    env.pop("STANDARD_PROXY_MODES",None)
    env.pop("PYTHONPATH",None)
    errors=[]
    def phase(name,extra=None):
        command=[sys.executable,str(ROOT/"retest.py"),name]
        run_env={**env,**(extra or {})}
        stamp=dt.datetime.now(dt.timezone.utc).isoformat()
        def record_command(event,**details):
            with (output/"phase-commands.jsonl").open("a") as log:
                log.write(json.dumps({"time":dt.datetime.now(dt.timezone.utc).isoformat(),
                    "startedAt":stamp,"event":event,"command":command,"cwd":str(ROOT),
                    "resultsDirectory":str(output),"extraEnvironment":extra,**details})+"\n")
        record_command("start")
        print("Starting",name,flush=True)
        with (output/f"phase-{name}.log").open("a") as log:
            result=subprocess.run(command,cwd=ROOT,env=run_env,stdout=log,stderr=subprocess.STDOUT)
        record_command("end",returncode=result.returncode)
        print(name,"process exit",result.returncode,flush=True)
        if result.returncode:raise RuntimeError("Phase process failed: "+name)
        for path in output.glob("*-results.jsonl"):
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            if any(row["time"]>=stamp and row["feature"]==name+".suite" and row["status"]=="FAIL" for row in rows):
                raise RuntimeError(f"Phase wrapper failed in {path.name}: {name}")
    try:
        subprocess.run(["node",str(ROOT/"retest-viewer/build.mjs")],cwd=ROOT,check=True)
        for name in ["retest_setup","retest_tunnels","retest_gateway","retest_authcode","retest_runtime",
                     "retest_proxy","retest_proxy_ports","retest_browser"]:
            phase(name)
        phase("retest_browser_deep",{"PYTHONPATH":str(ROOT/"retest-pw148")})
        phase("retest_download_binary")
        phase("retest_availability")
        phase("retest_conclusions")
    except Exception as error:
        errors.append(str(error))
    finally:
        # Attempt local cleanup even if cloud cleanup fails.
        if list(output.glob("*-state.json")):
            for name,extra in [("cleanup_tests",{"CLEANUP_SG_WAIT_SECONDS":"20"}),("retest_cleanup_local",None)]:
                try:phase(name,extra)
                except Exception as error:errors.append(str(error))
            try:
                subprocess.run([sys.executable,str(ROOT/"verify_cleanup.py")],cwd=ROOT,env=env,check=True)
                with (output/"deferred-cleanup.log").open("a") as log:
                    subprocess.Popen([sys.executable,str(ROOT/"deferred_cleanup.py")],cwd=ROOT,
                        env={**env,"DEFERRED_RESULTS_DIR":str(output)},stdout=log,stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,start_new_session=True)
            except Exception as error:errors.append(str(error))
        try:redact_directory(output)
        except Exception as error:errors.append(str(error))
    # Phase wrappers can pass with individual failures: retain and expose those actual verdicts.
    latest={}
    for path in output.glob("*-results.jsonl"):
        for raw in path.read_text().splitlines():
            row=json.loads(raw);latest[(row["region"],row["feature"])]=row
    (output/"latest-results.json").write_text(json.dumps(list(latest.values()),indent=2))
    failed=[r for r in latest.values() if r["status"]=="FAIL" and not r["feature"].endswith(".suite")
            and not r["feature"].startswith(("cleanup.","fixture."))]
    (output/"run-summary.json").write_text(json.dumps({
        "completedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"errors":errors,
        "latestFailedChecks":len(failed),"cleanupStatus":"See regional verification and deferred-cleanup.json",
    },indent=2))
    print(f"Finished; {len(failed)} latest failed checks. Read regional evidence; process exit is not the test verdict.")
    return 1 if errors else 2 if failed else 0


if __name__=="__main__":
    sys.exit(main())
