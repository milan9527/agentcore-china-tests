"""Execute the follow-up phases in a new inventory, retaining logs and cleaning up."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

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
    def phase(name,extra=None):
        command=[sys.executable,str(ROOT/"retest.py"),name]
        run_env={**env,**(extra or {})}
        stamp=dt.datetime.now(dt.timezone.utc).isoformat()
        with (output/f"phase-{name}.log").open("a") as log:
            result=subprocess.run(command,cwd=ROOT,env=run_env,stdout=log,stderr=subprocess.STDOUT)
        with (output/"phase-commands.jsonl").open("a") as log:
            log.write(json.dumps({"time":stamp,"command":command,"extraEnvironment":extra,"returncode":result.returncode})+"\n")
        print(name,"process exit",result.returncode,flush=True)
        if result.returncode:raise RuntimeError("Phase process failed: "+name)
    try:
        subprocess.run(["node",str(ROOT/"retest-viewer/build.mjs")],cwd=ROOT,check=True)
        for name in ["retest_setup","retest_tunnels","retest_gateway","retest_authcode","retest_runtime",
                     "retest_proxy","retest_proxy_ports","retest_browser"]:
            phase(name)
        phase("retest_browser_deep",{"PYTHONPATH":str(ROOT/"retest-pw148")})
        phase("retest_download_binary")
        phase("retest_availability")
    finally:
        phase("cleanup_tests",{"CLEANUP_SG_WAIT_SECONDS":"20"})
        phase("retest_cleanup_local")
        subprocess.run([sys.executable,str(ROOT/"verify_cleanup.py")],cwd=ROOT,env=env,check=True)
        with (output/"deferred-cleanup.log").open("a") as log:
            subprocess.Popen([sys.executable,str(ROOT/"deferred_cleanup.py")],cwd=ROOT,
                env={**env,"DEFERRED_RESULTS_DIR":str(output)},stdout=log,stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,start_new_session=True)
    # Phase wrappers can pass with individual failures: retain and expose those actual verdicts.
    latest={}
    for path in output.glob("*-results.jsonl"):
        for raw in path.read_text().splitlines():
            row=json.loads(raw);latest[(row["region"],row["feature"])]=row
    (output/"latest-results.json").write_text(json.dumps(list(latest.values()),indent=2))
    failed=[r for r in latest.values() if r["status"]=="FAIL" and not r["feature"].endswith(".suite")
            and not r["feature"].startswith(("cleanup.","fixture."))]
    print(f"Finished; {len(failed)} latest failed checks. Read regional evidence; process exit is not the test verdict.")
    return 2 if failed else 0


if __name__=="__main__":
    sys.exit(main())
