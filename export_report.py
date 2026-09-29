"""Build the report and credential-redacted exports from local evidence only."""
import collections
import csv
import datetime as dt
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
REGIONS = ("cn-north-1", "cn-northwest-1")
FOLLOWUP_DIRS = ("retest", "retest-browser", "retest-livewait",
                "retest-live-signature", "retest-livewait-default", "repro-caller-confirm-20260928",
                "repro-caller-confirm-20260929")
SETUP_CHECKS = {
    "gateway.fixture.update", "gateway.runtime.fixture_create", "gateway.runtime.fixture_ready",
}
SECRET_KEYS = {
    "authorization", "proxy-authorization", "x-amz-security-token",
    "x-amz-credential", "x-amz-signature", "accesskeyid", "secretaccesskey",
    "sessiontoken", "clientsecret", "password", "test_secret", "apikey",
    "accesstoken", "refreshtoken", "access_token", "refresh_token", "authToken".lower(),
    "secretstring", "secretbinary", "client_secret", "rsa_key", "userdata", "zipfile",
    "usertoken", "workloadidentitytoken", "workloadaccesstoken", "authorizationcode",
    "codeverifier", "code_verifier", "subject_token", "actor_token", "authorizationurl", "sessionuri", "cookie", "set-cookie",
    "authcode", "pathkey", "path_key",
    "assertion", "client_assertion", "requeststate",
}


def sanitize(value):
    if isinstance(value, dict):
        return {k: "REDACTED" if k.lower() in SECRET_KEYS else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        # Some API results contain JSON serialized inside a string.
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except ValueError:
                pass
            else:
                cleaned = sanitize(parsed)
                if cleaned != parsed:
                    value = json.dumps(cleaned, ensure_ascii=False)
        # Handle both normal and percent-encoded query strings inside error text.
        value = re.sub(
            r"(?i)(X-Amz-(?:Signature|Credential|Security-Token)(?:=|%3D))"
            r"(?:(?!%26)[^&\s\"'<>\\])+",
            r"\1REDACTED", value,
        )
        value = re.sub(
            r"(?i)\b(?:AWS4-HMAC-SHA256)\s+Credential=[^\r\n\"'<>]+",
            "REDACTED_SIGV4_AUTHORIZATION", value,
        )
        value = re.sub(r"\b(Bearer|Basic) [A-Za-z0-9_+/=.~-]+", r"\1 REDACTED", value)
        value = re.sub(r"(?i)((?:[?&]|&amp;|%3F|%26)(?:code|state|request_uri|session_uri|session_id|access_token|refresh_token)(?:=|%3D))"
                       r"(?:(?!%26)[^&\s\"'<>\\])+", r"\1REDACTED", value)
        value = re.sub(r"(/test/)[a-f0-9]{32}(?=/|[?\"'\s]|$)", r"\1REDACTED_PATH_KEY", value)
        # JWTs embedded in tracebacks and JSON encoded as string values.
        value = re.sub(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
                       "REDACTED_JWT", value)
    return value


def category(feature):
    if feature.startswith("cleanup."):
        return "cleanup"
    if feature.startswith("china_exclusion."):
        return "documented_exclusion"
    if feature.startswith(("gateway.", "browser.")) and not feature.endswith(".suite") and feature not in SETUP_CHECKS:
        return "functional"
    return "setup_or_phase_wrapper"


def load():
    latest = {}
    for region in REGIONS:
        path = RESULTS / f"{region}-results.jsonl"
        regional = {}
        for line, raw in enumerate(path.read_text().splitlines(), 1):
            row = sanitize(json.loads(raw))
            row.update(category=category(row["feature"]), source=f"results/{path.name}", sourceLine=line)
            regional[row["feature"]] = row
        latest[region] = regional
    return latest


def load_current(initial):
    """Keep the initial check population; update matching checks from actual later rows."""
    latest = {region: dict(rows) for region, rows in initial.items()}
    for folder in FOLLOWUP_DIRS:
        for region in REGIONS:
            path = RESULTS / folder / f"{region}-results.jsonl"
            if not path.exists():
                continue
            for line, raw in enumerate(path.read_text().splitlines(), 1):
                row = sanitize(json.loads(raw))
                feature = row["feature"]
                if feature not in initial[region] or category(feature) != "functional":
                    continue
                if row["time"] <= latest[region][feature]["time"]:
                    continue
                row.update(category=category(feature), source=str(path.relative_to(ROOT)), sourceLine=line,
                    initialResult={k: initial[region][feature][k] for k in ("status", "time", "source", "sourceLine")})
                latest[region][feature] = row
    return latest


def write_matrix(path, functional):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["feature", "region", "status", "time", "source", "sourceLine", "evidence"])
        for region in REGIONS:
            for feature, row in sorted(functional[region].items()):
                writer.writerow([feature, region, row["status"], row["time"], row["source"], row["sourceLine"],
                                 json.dumps(row["evidence"], ensure_ascii=False)])


def live_view_section():
    lines = [
        "## Live View correction: display and input pass", "",
        "The earlier test exited when `probe.errors.length > 0`. At about two seconds, the "
        "`/live-view/auth` WebSocket reported `Close received after close` and an authentication "
        "error callback reported `Failed to communicate with server.` Authentication had already "
        "succeeded and the display connection was still being established. The test stopped too early; "
        "this was not evidence that display connection had failed.", "",
        "Keeping the default 300-second SigV4 URL and waiting for the actual first frame yielded "
        "the following results. Each region was observed for five minutes, then reconnected to the "
        "same Browser session with a fresh signature and observed for another five minutes. "
        "Browser session timeout was 1800 seconds.", "",
        "| Region | Attempt | Authentication success (s) | Auth close error (s) | Display connected (s) | First frame (s) | Observation (s) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for region in REGIONS:
        for attempt, label in (("initial_5min", "Initial"), ("fresh_signature_retry_5min", "Fresh-signature reconnect")):
            evidence = json.loads((RESULTS / "retest-livewait-default" / f"{region}-{attempt}.json").read_text())
            times = {event["event"]: event["elapsedSeconds"] for event in evidence["probe"]["events"]}
            lines.append(f"| {region} | {label} | " + " | ".join(f"{times[key]:.3f}" for key in
                ("authenticate.success", "authenticate.error", "connect.success", "display.firstFrame")) +
                f" | {evidence['actualObservationSeconds']:.3f} |")
    lines += [
        "", "Incoming WebSocket bytes increased at every 30-second observation and the remote clock "
        "continued changing. These counters include protocol messages, so they are not video-frame counts. "
        "This demonstrates the tested ten-minute viewing sequence, not long-duration or load certification.", "",
        "A separate mouse/keyboard check passed in both regions after correcting the click coordinate "
        "for the browser toolbar: the full window was 719 pixels high and content was 632 pixels high, "
        "a difference of 87 pixels. Text typed through Live View was read back from the remote DOM as "
        "`dcv-official-input-ok`. [Beijing screenshot](results/retest-live-signature/cn-north-1-official-live.png) "
        "and [Ningxia screenshot](results/retest-live-signature/cn-northwest-1-official-live.png).", "",
        "The extended-observation combined display/input checks remain FAIL in the historical log because "
        "they used incorrect click coordinates. Separate display evidence and the corrected input checks support "
        "the appended PASS verdicts. The official SDK connection logic was unchanged; the test now "
        "waits up to 120 seconds for the first frame without treating every auth-socket error as terminal.", "",
        "Increasing the URL signature lifetime to 900 seconds caused an auth WebSocket 403 in both "
        "regions; restoring the default 300 seconds allowed authentication. Signature lifetime and "
        "first-frame observation timeout are separate settings. The auth close error's internal cause "
        "remains unconfirmed, but it did not prevent display or input in these tests.", "",
        "The SDK URL generator hardcodes `.amazonaws.com`; tests signed the actual service-returned "
        "`.amazonaws.com.cn` endpoint. [Full timing, evidence and reproduction](LIVEVIEW.zh-CN.md).", "",
        "## Proxy configuration boundaries", "",
        "A fresh proxy matrix used separate origin and proxy EC2 instances in each region: "
        "**95 checks per region, 60 PASS / 35 FAIL**, with all failures reproduced twice "
        "(260 observations overall). Managed HTTP 8000/8081 requests returned `squid/6.13` "
        "and `ERR_ACCESS_DENIED 0` before reaching the external proxy; HTTPS 8443 also failed "
        "before it. Direct and explicit Playwright-proxy controls passed on all five destination "
        "ports. Standard-port IP/hostname/suffix bypass, bad/missing credential controls, and "
        "specific/default multi-proxy selection passed. The precise internal Squid ACL remains "
        "unreadable. These scenario counts are separate from the original 159-check population. "
        "[Full evidence](results/proxy-validation-20260928-r2/REPORT.md) · "
        "[中文结论](PROXY-VALIDATION.zh-CN.md).", "",
        "Basic-auth and no-auth external proxies pass HTTP 80, HTTPS CONNECT 443, explicit domain "
        "routing and an independently tested bypass rule. For upstream-only DNS, place "
        "`domainPatterns` inside `externalProxy`. Use a bare host/IP for `server`, without `http://`. "
        "Test route and bypass assertions separately if reverse DNS could make both match the same host.", "",
        "HTTP 8000 and HTTPS 8443 failed through the built-in proxy; upstream-only DNS without explicit "
        "domain patterns returned Squid DNS 503. These failed configurations remain in the evidence. "
        "The proxy PASS verdict is limited to the verified combinations. Server logs verify actual "
        "GET/CONNECT traffic and successful credential checks.", "",
    ]
    return lines


def main():
    initial = load()
    initial_functional = {region: {key: row for key, row in initial[region].items()
                                  if row["category"] == "functional"} for region in REGIONS}
    initial_counts = {region: dict(collections.Counter(row["status"] for row in rows.values()))
                      for region, rows in initial_functional.items()}
    (RESULTS / "initial-results.json").write_text(json.dumps({
        "scope": "Initial run only; later corrections are in final-results.json",
        "profile": "china", "accountId": "209915754514", "functionalCounts": initial_counts,
        "results": [row for region in REGIONS for _, row in sorted(initial[region].items())],
    }, indent=2, ensure_ascii=False))
    write_matrix(RESULTS / "initial-feature-matrix.csv", initial_functional)
    latest = load_current(initial)
    functional = {
        region: {k: r for k, r in latest[region].items() if r["category"] == "functional"}
        for region in REGIONS
    }
    counts = {region: dict(collections.Counter(r["status"] for r in rows.values()))
              for region, rows in functional.items()}
    inventories = []
    remaining = {region: [] for region in REGIONS}
    for folder in (RESULTS, *(RESULTS / name for name in FOLLOWUP_DIRS)):
        for region in REGIONS:
            path = folder / f"{region}-state.json"
            if not path.exists():
                continue
            state = json.loads(path.read_text())
            item = {"directory": str(folder.relative_to(ROOT)), "region": region,
                    "recordedResources": len(state["resources"]),
                    "deletedResources": sum(bool(r.get("deleted")) for r in state["resources"])}
            verification_path = folder / f"{region}-cleanup-verification.json"
            if verification_path.exists():
                item["verification"] = json.loads(verification_path.read_text())
            inventories.append(item)
            remaining[region].extend({**r, "directory": str(folder.relative_to(ROOT))}
                                     for r in state["resources"] if not r.get("deleted"))
    export = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profile": "china", "accountId": "209915754514",
        "countingRule": "Fixed initial check population, updated by the latest matching functional check "
                        "across the recorded follow-up directories. gateway./browser. checks except .suite and "
                        + ", ".join(sorted(SETUP_CHECKS))
                        + ". Baselines are included. Counts are checks, not independent product features.",
        "functionalCounts": counts,
        "initialFunctionalCounts": initial_counts,
        "followupDirectories": list(FOLLOWUP_DIRS),
        "results": [r for region in REGIONS for _, r in sorted(latest[region].items())],
        "remainingResources": sanitize(remaining),
        "cleanupInventories": sanitize(inventories),
    }
    (RESULTS / "final-results.json").write_text(json.dumps(export, indent=2, ensure_ascii=False))
    write_matrix(RESULTS / "feature-matrix.csv", functional)

    lines = [
        "# AgentCore Gateway and Browser — AWS China live test report",
        "",
        "Tested on **28 September 2026 UTC**, with caller-IAM retested on **29 September**, "
        "using AWS profile **`china`**, account **`209915754514`**, "
        "in **Beijing (`cn-north-1`)** and **Ningxia (`cn-northwest-1`)**.",
        "",
        "**Updated consolidated report:** includes authentication, proxy, download and extended Live View "
        "follow-up tests. [Chinese summary](SUMMARY.zh-CN.md), [detailed follow-up](FOLLOWUP.zh-CN.md), "
        "and [reproduction guide](REPRODUCE.zh-CN.md). The [initial report](REPORT.initial.md) is retained as history.",
        "",
        "**Latest update — 29 September 2026:** Gateway caller-IAM forwarding passes in Beijing and Ningxia, "
        "with all 8/8 selected checks passing per region. The invalid-token 403 no longer occurs in the tested "
        "paths. Consolidated counts are now 154 PASS, 1 FAIL, 2 BLOCKED and 2 NOT_AVAILABLE per region. "
        "[Full retest evidence](results/repro-caller-confirm-20260929/REPORT.md).",
        "",
        "**Outbound OAuth validation, 28 September 2026, 08:27–08:29 UTC:** 2LO (Basic and POST client authentication) "
        "and complete 3LO, repeat authorized access, and user isolation pass in both regions. "
        "Four OBO provider configurations are accepted, but 16 Gateway target creation attempts return "
        "the explicit account-gating 403. The separate 8 PASS / 4 BLOCKED checks per region do not change "
        "the 159-check population below. [Full English evidence and reproduction]"
        "(results/oauth-validation-20260928/REPORT.md) · "
        "[中文报告](results/oauth-validation-20260928/REPORT.zh-CN.md).",
        "",
        "**OAuth provider scope:** this run uses a self-hosted synthetic IdP through `CustomOauth2`, "
        "with OAuth client `cn-retest` and a random client secret per region. Microsoft Entra ID, Google, "
        "Okta, and other third-party IdPs were not used. Passing 2LO/3LO results apply to this test IdP; "
        "third-party compatibility and Microsoft OBO remain untested. OBO client configuration succeeded, "
        "but Gateway target creation was account-gated before any Gateway token exchange.",
        "",
        "**Both regions pass Live View display and mouse/keyboard input.** The previous DCV failure verdict "
        "was caused by the test exiting on an authentication-socket close error before the first frame. "
        "JWT, OAuth client credentials, OAuth authorization code and JWT passthrough also pass. "
        "Browser proxy routing passes with the tested standard ports and configuration. "
        "Caller-IAM forwarding now passes the unchanged reproduction in both regions on 29 September. "
        "The remaining failure in the original 159-check population is Playwright `download.save_as()` "
        "retrieval; a verified remote-file retrieval alternative is available.",
        "",
        "## Results and scope",
        "",
        "| Region | Checks | PASS | FAIL | BLOCKED | PARTIAL | NOT_AVAILABLE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for region in REGIONS:
        c = counts[region]
        lines.append(f"| {region} | {len(functional[region])} | " +
                     " | ".join(str(c.get(status, 0)) for status in
                                ("PASS", "FAIL", "BLOCKED", "PARTIAL", "NOT_AVAILABLE")) + " |")
    lines += [
        "",
        "Counts retain the **159 initial named checks per region**, replacing matching checks with their "
        "latest follow-up result. Newly added diagnostic checks are listed separately in the "
        "[follow-up matrix](results/followup-matrix.csv), so they do not inflate this comparison. "
        "The initial count was 145 PASS, 6 FAIL, 5 BLOCKED, 1 PARTIAL and 2 NOT_AVAILABLE per region. "
        "Nine checks now pass: JWT, three OAuth/passthrough checks, three proxy checks, Live View, "
        "and caller-IAM forwarding. "
        "Counts include control-plane "
        "checks and diagnostic baselines. They exclude setup/phase wrappers, cleanup, documented negative checks, "
        "and `gateway.fixture.update`, `gateway.runtime.fixture_create`, `gateway.runtime.fixture_ready`. "
        "One product feature can have several checks; these totals are not a count of independent features. "
        "Earlier fixture failures and corrected attempts remain in the chronological JSONL evidence.",
        "",
        "**PASS** means the named assertion succeeded; configuration-only checks are identified as such. "
        "**FAIL** means the attempted behavior failed in this test, without automatically attributing it to "
        "an AWS defect. **BLOCKED** means an account or identity prerequisite prevented execution. "
        "**PARTIAL** means only part of the feature was verified. **NOT_AVAILABLE** refers to the service "
        "catalog visible in this account and region.",
        "",
        "This is feature-based API and browser integration coverage. It does not certify every configuration, "
        "protocol permutation, console workflow, quota boundary, performance characteristic, or third-party integration. "
        "Elicitation used form mode and an actual URL authorization-code round trip with MCP 2026-07-28; "
        "sampling used a synthetic client response. Other elicitation variants and real-model sampling "
        "were not separately exercised. A proxy PASS applies to the explicitly verified configuration; "
        "nonstandard-port and upstream-only DNS failures remain recorded.",
        "",
        "Client environment: Python 3.12.13, boto3/botocore 1.43.103, Playwright 1.63.0, local headless "
        "Chromium 153.0.8010.12, and DCV Web SDK 1.14.1+build.0. The remote Browser reported Chromium "
        "148.0.7778.258 in both regions. [Complete client versions](results/client-versions.json). "
        "Follow-up used the official `bedrock-agentcore` TypeScript SDK 0.4.4 BrowserLiveView component "
        "and its bundled DCV client. Playwright 1.60.0 was also tested against the Chromium 148 series: "
        "`save_as()` still returned zero bytes. Live View passes after fixing the test's early-exit condition.",
        "",
        "## Passing coverage",
        "",
        "| Area | Verified behavior in both regions |",
        "| --- | --- |",
        "| Gateway lifecycle | Create/get/list/update, tags, target pagination, active target update followed by invocation, target idempotency; deletion is tracked separately under cleanup. |",
        "| Gateway inbound IAM | SigV4-authorized calls succeed; unsigned calls are rejected. |",
        "| Gateway JWT and OAuth | Valid RS256 JWT invokes a Lambda tool; incorrect audience/client/scope and expired tokens are rejected. Client credentials and authorization code flows invoke protected backends with the expected grant. JWT passthrough preserves the token SHA-256. |",
        "| Lambda targets | Inline and S3 schemas; addition, Unicode echo, and target error responses. |",
        "| OpenAPI and API Gateway targets | Inline/S3 schemas, IAM-authenticated backend calls, forwarded headers, REST stage filters and tool overrides. |",
        "| Smithy | Schema import and actual Lambda `GetFunctionConcurrency` invocation. |",
        "| MCP server targets | DEFAULT and DYNAMIC discovery, synchronization, refreshed schema, tools, prompts, resources, and resource templates. |",
        "| MCP protocol/session support | 2025-03-26, 2025-06-18, 2025-11-25, and 2026-07-28; initialize/initialized handshake and 2026 server discovery. |",
        "| MCP streaming and client requests | SSE results, progress/log notifications, form elicitation, URL elicitation with OAuth callback/session binding/resumption, and synthetic sampling request/resume round trips. |",
        "| Gateway interceptors | Request interceptor changes tool arguments; response interceptor inserts a verified marker. |",
        "| Gateway encryption and authentication | Customer-managed KMS gateway plus tool invocation; outbound API key validated by backend; custom OAuth provider configuration. |",
        "| Gateway HTTP and Runtime | HTTP passthrough; Runtime target invocation using the Gateway IAM role; caller-IAM forwarding now passes using STS GetSessionToken and AssumeRole, including AWS_IAM and AUTHENTICATE_ONLY inbound. The same credentials pass direct Runtime and Gateway-role controls. |",
        "| Gateway rate limits | Create/list/update/delete; zero-rate rule returns HTTP 429. |",
        "| Browser lifecycle | Managed/custom browsers, get/list, tags, pagination, session idempotency, viewport/timeout settings, stop; profile management and tags. |",
        "| Browser automation | CDP connection, HTTPS navigation, DOM extraction, forms, clicks, Unicode input, tabs, screenshots, upload, and download inside the remote browser. |",
        "| Browser OS actions | All eight InvokeBrowser actions: mouseMove, mouseClick, mouseDrag, mouseScroll, keyType, keyPress, keyShortcut, screenshot. Typed input verified in DOM. |",
        "| Browser state and access | Cookies/local storage; saved profile restores both; concurrent sessions remain isolated; automation disable rejects connections, re-enable permits reconnect. |",
        "| Browser customization | Extension executes; managed URL blocklist enforced; recommended enterprise policies appear in Chrome policy UI. |",
        "| Browser recording | Real S3 gzip NDJSON batches contain full snapshots; local rrweb replay reconstructs the test DOM. Beijing replay: 330 events; Ningxia: 467 events. |",
        "| Browser networking | VPC private HTTP access; private CA rejected by default and trusted after root certificate configuration; EFS file persists into a later session. |",
        "| Browser proxy | Basic-auth and no-auth routing pass on HTTP 80 and HTTPS CONNECT 443; explicit `externalProxy.domainPatterns` resolves upstream-only hostnames; bypass passes in a separate session. |",
        "| Browser Live View | Official component renders frames and transmits mouse/keyboard input. Initial connection and fresh-signature reconnect each observed for 300 seconds per region, with incoming bytes increasing throughout. |",
        "| Browser remote file retrieval alternative | CDP `DOM.setFileInputFiles` plus `File.arrayBuffer()` retrieves exact 21-byte text and 8192-byte binary files; byte equality and SHA-256 verified in both regions. |",
        "| Browser TTL | 60-second session timeout and automatic termination. |",
        "| Observability | Gateway application logs and Browser usage logs delivered to CloudWatch; service metrics and CloudTrail events observed for both services. |",
        "",
        "## Unresolved failures",
        "",
        "| Area | Observation and baseline | Scope / next investigation |",
        "| --- | --- | --- |",
        "| Browser Playwright download retrieval | `download.save_as()` returns zero bytes in Playwright 1.63.0 and 1.60.0. The returned file path exists with correct contents in the remote browser but not on the client. Local Chromium baseline passes. | Failure is in remote-file retrieval in this CDP setup. [download_remote_file.py](download_remote_file.py) is a verified alternative for the tested text and binary files; large files were not benchmarked. |",
        "",
        "## Caller-IAM forwarding: original error resolved in the tested paths",
        "",
        "On **29 September 2026, 01:58–01:59 UTC**, fresh environments passed all eight selected "
        "checks per region. All three caller-forwarding combinations returned HTTP 200 and sum=42 "
        "(AssumeRole with AWS_IAM, AssumeRole with AUTHENTICATE_ONLY, and GetSessionToken); "
        "all five same-credential direct/role controls passed. Core invocation scripts and SDK versions "
        "match the 28 September run. The earlier invalid-token 403 is no longer reproduced in these paths. "
        "This establishes the observed behavior, not an AWS deployment time or an internal root cause. "
        "[Current report](results/repro-caller-confirm-20260929/REPORT.md), "
        "[console](results/repro-caller-confirm-20260929/console.log), "
        "[responses/request IDs](results/repro-caller-confirm-20260929/invocation-results.csv).",
        "",
        "| Caller credentials / inbound mode | Beijing | Ningxia |",
        "| --- | --- | --- |",
        "| AssumeRole + AWS_IAM | HTTP 200, sum=42 | HTTP 200, sum=42 |",
        "| AssumeRole + AUTHENTICATE_ONLY | HTTP 200, sum=42 | HTTP 200, sum=42 |",
        "| GetSessionToken + AWS_IAM | HTTP 200, sum=42 | HTTP 200, sum=42 |",
        "",
        "All resources created for this retest were cleaned up, with independent read-only verification "
        "passing in both regions. Other features were not retested on 29 September.",
        "",
        "The **28 September 07:53 UTC** run had five passing controls and three failing caller paths "
        "per region; its [report and evidence](results/repro-caller-confirm-20260928/REPORT.zh-CN.md) "
        "remain unchanged. Earlier failing AssumeRole request IDs are retained below:",
        "",
        "| Region | AWS_IAM inbound | AUTHENTICATE_ONLY inbound |",
        "| --- | --- | --- |",
        "| Beijing | `b3752ba3-ad3b-4baf-ba50-f456443ceb33`, `e1e08000-7b81-47f6-9507-b4bb68f16e90` | `4b462c3a-38f7-42d0-8941-9734c6b6355e`, `100bbec5-c396-4a8d-a994-4ffc7ad7d593` |",
        "| Ningxia | `3ed694a0-36cf-4bbb-8341-1773d8e3a05f`, `f70990fb-f44e-44b9-8a1b-b05589029139` | `780aea03-3c6a-4dd3-a1e3-0673c76f24df`, `693f6dbf-bebd-4fd6-8ade-332b50a8aaeb` |",
        "",
        "## Prerequisite gaps",
        "",
        "| Feature | Result in both regions | What remains |",
        "| --- | --- | --- |",
        "| OAuth Token Exchange | BLOCKED: provider configuration succeeds, but target creation explicitly returns `Token Exchange is not available for this account`. | Account enablement by AWS; a usable synthetic issuer was already supplied. |",
        "| Gateway private target | BLOCKED: API returns `Private endpoint configuration requires VPC egress feature to be enabled for this account.` | Account enablement followed by an actual private target invocation. |",
        "| Gateway and Browser PrivateLink | NOT_AVAILABLE: EC2 endpoint-service catalog advertises no AgentCore service names in this account in either region. | Private endpoint ingress testing once services are exposed. Browser VPC egress passed separately. |",
        "",
        "These availability results apply to the tested account and regions at test time. JWT, client credentials, "
        "authorization code and JWT passthrough no longer have missing-issuer prerequisites: a temporary "
        "synthetic HTTPS OIDC/OAuth provider completed those tests and has been shut down.",
        "",
        "## Documented China exclusions",
        "",
        "The [AWS China service differences page](https://docs.amazonaws.cn/en_us/aws/latest/userguide/bedrock-agentcore.html) "
        "excludes Gateway semantic search, Cognito authorizers, NONE inbound authorization, inference targets, "
        "the console connector catalog, WAF integration, Gateway rules, and ConfigBundle A/B testing. "
        "Browser Web Bot Auth and S3 Files mounts are also excluded. Private identity providers and the listed "
        "built-in OAuth providers are unavailable. These are not counted as failed supported features.",
        "",
        "Live creation attempts confirmed rejection of **NONE inbound auth** and **semantic search** in both regions. "
        "The remaining exclusions are based on the documentation, without separate negative API tests. "
        "EFS mounting was tested successfully and is distinct from S3 Files mounting.",
        "The China overview lists AWS_IAM and CUSTOM_JWT inbound authorization. In this account, "
        "AUTHENTICATE_ONLY Gateway creation was also accepted in both regions, and Gateway-role outbound "
        "invocation passed with that inbound mode. The report retains this observed documentation difference.",
        "",
        "## Cleanup",
        "",
    ]
    position = lines.index("## Unresolved failures")
    lines[position:position] = live_view_section()
    lines += [
        "This is a summary of saved inventories and read-only verification; report generation makes no AWS calls. "
        "The Live View follow-up sessions have been stopped and all three Live View test directories have "
        "passing cleanup verification in both regions. Earlier test compute and service resources are deleted. "
        "Any remaining recorded resources across the initial and follow-up runs are listed below.", "",
        "| Region | Run directory | Kind | Identifier | Recorded state |",
        "| --- | --- | --- | --- | --- |",
    ]
    for region in REGIONS:
        for resource in remaining[region]:
            verification = next((item.get("verification", {}) for item in inventories
                if item["region"] == region and item["directory"] == resource["directory"]), {})
            check = next((item for item in verification.get("evidence", [])
                if item.get("id") == resource["id"]), {})
            status = check.get("status", "Cleanup pending")
            if check.get("deletionDate"):
                status += "; deletion " + check["deletionDate"]
            lines.append(f"| {region} | `{resource['directory']}` | {resource['kind']} | "
                         f"`{resource['id']}` | {status} |")
    lines += [
        "", "KMS has a minimum seven-day deletion window; the two initial-run keys are scheduled for "
        "5 October 2026. AWS [VPC documentation](docs/agentcore-vpc.md) says service-owned ENIs may "
        "persist for up to eight hours. Security groups cannot be deleted while those ENIs remain attached. "
        "No service interfaces were force-detached.", "",
        "[All-run cleanup inventory](results/followup-cleanup.json). Local deferred-cleanup workers retry "
        "the recorded security groups for a bounded period and depend on the workspace processes remaining alive:", "",
    ]
    for folder in (RESULTS, RESULTS / "retest"):
        path = folder / "deferred-cleanup.json"
        if path.exists():
            deferred = json.loads(path.read_text())
            lines.append(f"- [{folder.relative_to(ROOT)} worker]({path.relative_to(ROOT)}): "
                         f"`{deferred['status']}`, last recorded update `{deferred['updatedAt']}`.")
    lines += ["", "| Run directory | Region | Saved cleanup verification | Verified at (UTC) |",
              "| --- | --- | --- | --- |"]
    for item in inventories:
        verification = item.get("verification", {})
        link = item["directory"] + "/" + item["region"] + "-cleanup-verification.json"
        lines.append(f"| `{item['directory']}` | {item['region']} | "
                     f"[{verification.get('status', 'NOT_RECORDED')}]({link}) | "
                     f"{verification.get('time', '')} |")
    lines.append("")
    lines += [
        "## Evidence and reproduction",
        "",
        "- [Final results JSON](results/final-results.json): latest evidence, classifications, counts, and cleanup inventory.",
        "- [Feature matrix CSV](results/feature-matrix.csv): one functional result per region/check, with source line references.",
        "- [Initial results JSON](results/initial-results.json) and [initial matrix](results/initial-feature-matrix.csv): unchanged initial functional outcomes.",
        "- [Full chronology](results/followup-history.jsonl) and [follow-up matrix](results/followup-matrix.csv): failed configurations, diagnostics, corrections, and added checks.",
        "- [Beijing chronological evidence](results/cn-north-1-results.jsonl) and [Ningxia chronological evidence](results/cn-northwest-1-results.jsonl).",
        "- [Beijing replay](results/cn-north-1-replay.html) and [Ningxia replay](results/cn-northwest-1-replay.html): self-contained rrweb artifacts.",
        "- [Beijing replay screenshot](results/cn-north-1-replay.png) and [Ningxia replay screenshot](results/cn-northwest-1-replay.png).",
        "- [Run notes and script map](README.md). Scripts preserve the investigation phases; a clean fresh run of all phases has not been validated.",
        "",
        "Credential-bearing query parameters and authorization values are redacted in exports. "
        "Resource ARNs, account ID, request IDs, and synthetic test content are retained for audit. "
        "Local generated signing keys and test-secret files are removed after cleanup; the AWS profile is unchanged.",
        "Per-request auditing and phase source snapshots were added during the follow-up. Earlier missing raw "
        "requests were not reconstructed. Audit coverage includes registered SDK clients and traced requests, "
        "not every CDP/DCV message or a complete network capture.",
        "",
        "Sources consulted: [China availability/differences](docs/bedrock-agentcore.md), "
        "[Gateway features](docs/gateway-features.md), [Gateway outbound auth](docs/gateway-outbound-auth.md), "
        "[MCP targets](docs/gateway-target-MCPservers.md), [Browser features](docs/browser-features.md), "
        "[Browser tool](docs/browser-tool.md), and the API/service-model snapshots in `docs/`. "
        "China-specific documentation takes precedence over globally described capabilities.",
        "",
        "## Detailed functional matrix",
        "",
        "Each identifier matches the `feature` field in the JSON and CSV evidence. The latest row's exact "
        "source file and line are included in those exports.",
        "",
        "| Check | Beijing | Ningxia |",
        "| --- | --- | --- |",
    ]
    for feature in sorted(set().union(*(set(x) for x in functional.values()))):
        lines.append(f"| `{feature}` | " +
                     " | ".join(functional[r].get(feature, {}).get("status", "NOT_TESTED") for r in REGIONS) + " |")
    (ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"counts": counts, "report": str(ROOT / "REPORT.md")}, indent=2))


if __name__ == "__main__":
    main()
