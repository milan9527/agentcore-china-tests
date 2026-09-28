"""Start dedicated short-lived synthetic HTTPS issuer fixtures."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import requests
from suite import ROOT, RESULTS


def run(s):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    logpath=RESULTS/f"{s.region}-issuer.log"
    with logpath.open("a") as log:
        server=subprocess.Popen([sys.executable,str(ROOT/"retest_issuer_server.py"),s.region,str(port)],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    tunnel_log=RESULTS/f"{s.region}-tunnel.log"
    with tunnel_log.open("w") as log:
        tunnel=subprocess.Popen([str(ROOT/"results/retest/cloudflared"),"tunnel","--url",f"http://127.0.0.1:{port}",
            "--no-autoupdate","--protocol","http2"],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    s.state["local_processes"]=[server.pid,tunnel.pid];s.save()
    deadline=time.monotonic()+90
    url=None
    while time.monotonic()<deadline:
        match=re.search(r"https://[a-z0-9-]+\.trycloudflare\.com",tunnel_log.read_text())
        if match:url=match.group();break
        if tunnel.poll() is not None:raise RuntimeError("HTTPS tunnel failed; see local tunnel log")
        time.sleep(2)
    assert url,"No HTTPS tunnel URL"
    sec=json.loads((RESULTS/f"{s.region}-secrets.json").read_text())
    issuer=url+"/test/"+sec["pathKey"]
    s.state.update(issuer=issuer,api_url=issuer)
    s.save()
    response=None
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        try:
            response=requests.get(issuer+"/.well-known/openid-configuration",timeout=15)
            if response.status_code==200:break
        except requests.RequestException:pass
        time.sleep(2)
    assert response is not None and response.status_code==200,{"status":response.status_code if response is not None else "no response"}
    assert response.json()["issuer"]==issuer,response.json()
    s.record("fixture.oidc.public_discovery","PASS",{"publicTrustedTlsDiscovery":True,"host":url})
    response=requests.post(issuer+"/token",auth=("cn-retest",sec["clientSecret"]),
                          data={"grant_type":"client_credentials","scope":"test"},timeout=30)
    assert response.status_code==200,{"status":response.status_code}
    secure=requests.get(issuer+"/secure",headers={"Authorization":"Bearer "+response.json()["access_token"]},timeout=30)
    assert secure.status_code==200,{"status":secure.status_code}
    s.record("fixture.oidc.client_credentials","PASS",secure.json())
