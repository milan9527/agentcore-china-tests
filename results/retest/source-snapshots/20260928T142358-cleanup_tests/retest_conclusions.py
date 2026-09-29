"""Record explicit product conclusions with references to the actual configuration checks."""
import json
from pathlib import Path


def run(s):
    records=[json.loads(line) for line in (Path(s.state_path).parent/f"{s.region}-results.jsonl").read_text().splitlines()]
    latest={r["feature"]:r for r in records}
    gate=latest["gateway.outbound.oauth_token_exchange"]
    evidence=gate["evidence"]
    if gate["status"] != "BLOCKED" and "Token Exchange is not available for this account" in json.dumps(evidence):
        s.record("gateway.outbound.oauth_token_exchange","BLOCKED",{
            "reason":"Gateway explicitly rejects Token Exchange for this account",
            "originalAttemptTime":gate["time"],"response":evidence.get("response",evidence)})
    for feature,checks in {
        "browser.proxy.authenticated_routing":["browser.proxy.standard.default-auth.http",
                                             "browser.proxy.standard.default-auth.https",
                                             "browser.proxy.standard.explicit-auth.https"],
        "browser.proxy.bypass":["browser.proxy.standard.bypass"],
        "browser.proxy.http_routing":["browser.proxy.standard.explicit-auth.synthetic_dns",
                                     "browser.proxy.standard.explicit-no-auth.synthetic_dns"],
    }.items():
        assert all(latest[k]["status"]=="PASS" for k in checks),checks
        s.record(feature,"PASS",{"supportedConfiguration":{"httpPort":80,"httpsPort":443,
            "domainPatterns":"Explicit target domains when DNS is only known to the upstream proxy",
            "bypass":"Tested in a separate session to avoid matching the routed endpoint's reverse DNS"},
            "verifiedChecks":[{"feature":k,"time":latest[k]["time"]} for k in checks],
            "limits":"8000/8443 rejected by the built-in proxy in this test; upstream-only DNS without domainPatterns returned 503",
            "previousFailuresRetained":True})
