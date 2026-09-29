"""Execute both-region proxy diagnostics, retain all evidence, and clean resources."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from sanitize_evidence import redact_directory

ROOT = Path(__file__).resolve().parent
REGIONS = ("cn-north-1", "cn-northwest-1")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.results_dir.resolve()
    output.relative_to(ROOT)
    if output.exists() and any(output.iterdir()):
        parser.error("Use a new empty results directory")
    output.mkdir(parents=True)
    env = {**os.environ, "RETEST_RESULTS_DIR": str(output), "VERIFY_RESULTS_DIR": str(output),
           "RETEST_VERBOSE": "1", "PYTHONUNBUFFERED": "1", "CLEANUP_SG_WAIT_SECONDS": "20"}
    for key in ("RETEST_STATE_READ_ONLY", "PYTHONPATH"):
        env.pop(key, None)
    started = now()
    errors = []
    (output/"environment.json").write_text(json.dumps({
        "time": started, "profile": "china", "regions": REGIONS, "python": sys.version,
        "command": sys.argv, "cwd": str(ROOT),
        "dependencies": subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines(),
        "fixtureSourceSha256": hashlib.sha256((ROOT/"proxy_validation_fixture.py").read_bytes()).hexdigest(),
    }, indent=2) + "\n")

    def execute(command, label, extra=None, check=True):
        details = {"time": now(), "event": "start", "command": command, "cwd": str(ROOT),
                   "environment": {k: env[k] for k in ("RETEST_RESULTS_DIR", "VERIFY_RESULTS_DIR",
                       "RETEST_VERBOSE", "PYTHONUNBUFFERED", "CLEANUP_SG_WAIT_SECONDS")}}
        with (output/"phase-commands.jsonl").open("a") as log:
            log.write(json.dumps(details) + "\n")
        print(json.dumps(details), flush=True)
        with (output/(label+".log")).open("a") as log, (output/"console.log").open("a") as combined:
            combined.write(json.dumps(details) + "\n")
            proc = subprocess.Popen(command, cwd=ROOT, env={**env, **(extra or {})}, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            try:
                for line in proc.stdout:
                    print(line, end="", flush=True)
                    log.write(line)
                    log.flush()
                    combined.write(line)
                    combined.flush()
                code = proc.wait()
            except BaseException:
                proc.terminate()
                proc.wait(timeout=30)
                raise
        with (output/"phase-commands.jsonl").open("a") as log:
            log.write(json.dumps({"event": "end", "time": now(), "label": label, "returncode": code}) + "\n")
        if check:
            assert code == 0, (label, code)
            if command[1] == str(ROOT/"retest.py"):
                for region in REGIONS:
                    rows = [json.loads(line) for line in (output/f"{region}-results.jsonl").read_text().splitlines()]
                    phases = [row for row in rows if row["feature"] == label+".suite"]
                    assert phases and phases[-1]["status"] == "PASS", (region, label)

    def phase(label):
        execute([sys.executable, str(ROOT/"retest.py"), label], label)

    try:
        phase("proxy_validation_setup")
        phase("proxy_validation_tests")
    except Exception as error:
        errors.append(str(error))
        print("EXECUTION ERROR:", error, flush=True)
    finally:
        try:
            phase("cleanup_tests")
        except Exception as error:
            errors.append(str(error))
        try:
            execute([sys.executable, str(ROOT/"verify_cleanup.py")], "verify_cleanup")
        except Exception as error:
            errors.append(str(error))
        print(json.dumps(redact_directory(output)), flush=True)
    pending = []
    for region in REGIONS:
        state_path = output/f"{region}-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            pending.extend({"region": region, **item} for item in state["resources"] if not item.get("deleted"))
    if pending and all(item["kind"] == "sg" for item in pending):
        with (output/"deferred-cleanup.log").open("a") as log:
            worker = subprocess.Popen([sys.executable, str(ROOT/"deferred_cleanup.py")], cwd=ROOT,
                env={**env, "DEFERRED_RESULTS_DIR": str(output)}, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        (output/"deferred-worker.json").write_text(json.dumps({
            "pid": worker.pid, "startedAt": now(), "resources": pending,
            "command": [sys.executable, str(ROOT/"deferred_cleanup.py")],
            "environment": {"DEFERRED_RESULTS_DIR": str(output)}, "maxHours": 8.5}, indent=2) + "\n")
    status = {"startedAt": started, "completedAt": now(), "errors": errors,
              "pendingResources": pending, "profile": "china", "regions": REGIONS}
    (output/"run-summary.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2), flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
