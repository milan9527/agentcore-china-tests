"""Stop only local fixture processes recorded by the follow-up run."""
import json
import os
from pathlib import Path
import signal


def run(s):
    stopped=[]
    for pid in s.state.get("local_processes",[]):
        path=Path(f"/proc/{pid}/cmdline")
        if not path.exists():continue
        argv=path.read_bytes().replace(b"\0",b" ").decode()
        if ("retest_issuer_server.py" in argv or "cloudflared" in argv) and str(Path(__file__).parent) in argv:
            os.kill(pid,signal.SIGTERM);stopped.append(pid)
        else:
            raise RuntimeError("Recorded PID no longer belongs to a test fixture")
    for suffix in ["private-key.pem","secrets.json"]:
        path=Path(s.state_path).parent/f"{s.region}-{suffix}"
        path.unlink(missing_ok=True)
    s.record("cleanup.local_fixtures","PASS",{"stoppedPids":stopped,"generatedSecretsRemoved":True})
