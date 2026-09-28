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
}


def sanitize(value):
    if isinstance(value, dict):
        return {k: "REDACTED" if k.lower() in SECRET_KEYS else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
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
        value = re.sub(r"(?i)((?:[?&]|&amp;)(?:code|state|request_uri|session_uri|access_token|refresh_token)=)"
                       r"[^&\s\"'<>\\]+", r"\1REDACTED", value)
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


def main():
    latest = load()
    functional = {
        region: {k: r for k, r in latest[region].items() if r["category"] == "functional"}
        for region in REGIONS
    }
    counts = {region: dict(collections.Counter(r["status"] for r in rows.values()))
              for region, rows in functional.items()}
    states = {region: json.loads((RESULTS / f"{region}-state.json").read_text()) for region in REGIONS}
    remaining = {region: [r for r in state["resources"] if not r.get("deleted")]
                 for region, state in states.items()}
    export = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profile": "china", "accountId": "209915754514",
        "countingRule": "Latest result per feature and region; gateway./browser. checks except .suite and "
                        + ", ".join(sorted(SETUP_CHECKS))
                        + ". Baselines are included. Counts are checks, not independent product features.",
        "functionalCounts": counts,
        "results": [r for region in REGIONS for _, r in sorted(latest[region].items())],
        "remainingResources": sanitize(remaining),
    }
    (RESULTS / "final-results.json").write_text(json.dumps(export, indent=2, ensure_ascii=False))
    with (RESULTS / "feature-matrix.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["feature", "region", "status", "time", "source", "sourceLine", "evidence"])
        for region in REGIONS:
            for feature, r in sorted(functional[region].items()):
                writer.writerow([feature, region, r["status"], r["time"], r["source"], r["sourceLine"],
                                 json.dumps(r["evidence"], ensure_ascii=False)])

    lines = [
        "# AgentCore Gateway and Browser — AWS China live test report",
        "",
        "Tested on **28 September 2026 UTC** using AWS profile **`china`**, account **`209915754514`**, "
        "in **Beijing (`cn-north-1`)** and **Ningxia (`cn-northwest-1`)**.",
        "",
        "Both regions produced the same final functional outcomes. Most tested capabilities worked. "
        "Four areas remain unresolved: Gateway caller-IAM forwarding, the tested Browser VPC proxy configuration, "
        "Playwright download retrieval, and DCV display connection. Authentication prerequisites and account "
        "networking availability prevented complete coverage of several other features.",
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
        "Counts use the **latest result for each named check in each region**. They include control-plane "
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
        "Elicitation used form mode with MCP 2026-07-28; sampling used a synthetic client response. "
        "Legacy/URL elicitation variants and real-model sampling were not separately exercised.",
        "",
        "Client environment: Python 3.12.13, boto3/botocore 1.43.103, Playwright 1.63.0, local headless "
        "Chromium 153.0.8010.12, and DCV Web SDK 1.14.1+build.0. The remote Browser reported Chromium "
        "148.0.7778.258 in both regions. [Complete client versions](results/client-versions.json). "
        "Client compatibility remains a possible contributor to the download-retrieval and DCV failures.",
        "",
        "## Passing coverage",
        "",
        "| Area | Verified behavior in both regions |",
        "| --- | --- |",
        "| Gateway lifecycle | Create/get/list/update, tags, target pagination, active target update followed by invocation, target idempotency; deletion is tracked separately under cleanup. |",
        "| Gateway inbound IAM | SigV4-authorized calls succeed; unsigned calls are rejected. |",
        "| Lambda targets | Inline and S3 schemas; addition, Unicode echo, and target error responses. |",
        "| OpenAPI and API Gateway targets | Inline/S3 schemas, IAM-authenticated backend calls, forwarded headers, REST stage filters and tool overrides. |",
        "| Smithy | Schema import and actual Lambda `GetFunctionConcurrency` invocation. |",
        "| MCP server targets | DEFAULT and DYNAMIC discovery, synchronization, refreshed schema, tools, prompts, resources, and resource templates. |",
        "| MCP protocol/session support | 2025-03-26, 2025-06-18, 2025-11-25, and 2026-07-28; initialize/initialized handshake and 2026 server discovery. |",
        "| MCP streaming and client requests | SSE results, progress/log notifications, form elicitation and synthetic sampling request/resume round trips. |",
        "| Gateway interceptors | Request interceptor changes tool arguments; response interceptor inserts a verified marker. |",
        "| Gateway encryption and authentication | Customer-managed KMS gateway plus tool invocation; outbound API key validated by backend; custom OAuth provider configuration. |",
        "| Gateway HTTP and Runtime | HTTP passthrough; Runtime target invocation using the Gateway IAM role; direct Runtime and Gateway-role calls also pass with the STS credentials used in the failed caller-IAM comparison. |",
        "| Gateway rate limits | Create/list/update/delete; zero-rate rule returns HTTP 429. |",
        "| Browser lifecycle | Managed/custom browsers, get/list, tags, pagination, session idempotency, viewport/timeout settings, stop; profile management and tags. |",
        "| Browser automation | CDP connection, HTTPS navigation, DOM extraction, forms, clicks, Unicode input, tabs, screenshots, upload, and download inside the remote browser. |",
        "| Browser OS actions | All eight InvokeBrowser actions: mouseMove, mouseClick, mouseDrag, mouseScroll, keyType, keyPress, keyShortcut, screenshot. Typed input verified in DOM. |",
        "| Browser state and access | Cookies/local storage; saved profile restores both; concurrent sessions remain isolated; automation disable rejects connections, re-enable permits reconnect. |",
        "| Browser customization | Extension executes; managed URL blocklist enforced; recommended enterprise policies appear in Chrome policy UI. |",
        "| Browser recording | Real S3 gzip NDJSON batches contain full snapshots; local rrweb replay reconstructs the test DOM. Beijing replay: 330 events; Ningxia: 467 events. |",
        "| Browser networking | VPC private HTTP access; private CA rejected by default and trusted after root certificate configuration; EFS file persists into a later session. |",
        "| Browser TTL | 60-second session timeout and automatic termination. |",
        "| Observability | Gateway application logs and Browser usage logs delivered to CloudWatch; service metrics and CloudTrail events observed for both services. |",
        "",
        "## Unresolved failures",
        "",
        "| Area | Observation and baseline | Scope / next investigation |",
        "| --- | --- | --- |",
        "| Gateway caller-IAM forwarding | `CALLER_IAM_CREDENTIALS` target creation succeeds. Invocation returns HTTP 403, `The security token included in the request is invalid`. Reproduced with profile keys and STS temporary credentials. The same STS credentials successfully invoke the same Runtime directly and through the Gateway-role target. | Investigate credential forwarding for HTTP Runtime targets in the China partition. Service-role invocation is a tested working alternative. |",
        "| Browser external proxy | Session API accepts the VPC proxy and Secrets Manager Basic credentials. HTTPS CONNECT fails with `ERR_TUNNEL_CONNECTION_FAILED`; bypass traffic returns Squid 403; a proxy-only HTTP hostname returns Squid DNS 503. A new Playwright context configured directly with the same private proxy and credentials successfully requests that HTTP hostname. | Three failed checks for this tested VPC proxy configuration. The HTTP baseline establishes fixture health; HTTPS CONNECT and bypass are not independently proven by that baseline. Do not generalize to every proxy deployment. |",
        "| Browser Playwright download retrieval | `download.save_as()` yields 0 bytes instead of the expected 21. The remote browser's downloaded file contains `agentcore-download-ok`, verified through a file URL. | Remote download passes; local Playwright retrieval fails in this client/connection configuration. |",
        "| Browser DCV live view | Presigned DCV authentication succeeds. Display connection fails before the first frame with `Failed to communicate with server`; the `/live-view/auth` WebSocket reports `Close received after close`. | Tested with AWS DCV Web SDK and local Chromium. Rendering and live-view input remain unverified. Root cause is unconfirmed; CDP and InvokeBrowser input pass independently. |",
        "",
        "Caller-IAM request IDs from the final STS comparison, around **05:14:48 UTC**:",
        "",
        "- Beijing: `0e842653-d009-4e91-84c3-9eefbf694e23`, `482c33e6-c640-477e-a0c6-2e938d3c7213`.",
        "- Ningxia: `d226bc60-fd43-485b-a0eb-d20b448c7a3d`, `581a7630-162f-4b1d-95a0-ff0a3427ce5e`.",
        "",
        "## Prerequisite gaps",
        "",
        "| Feature | Result in both regions | What remains |",
        "| --- | --- | --- |",
        "| CUSTOM_JWT inbound auth | PARTIAL: public Microsoft OIDC discovery configuration and invalid-token rejection pass. | Valid JWT invocation requires an approved test issuer and signing credentials/test identity. |",
        "| OAuth client credentials, authorization code, token exchange, JWT passthrough | BLOCKED for end-to-end flows; custom OAuth provider configuration passes. | Usable test provider and tokens/identity. The synthetic API Gateway fixture required AWS_IAM, which prevented serving the needed unauthenticated OIDC/Bearer endpoints. |",
        "| Gateway private target | BLOCKED: API returns `Private endpoint configuration requires VPC egress feature to be enabled for this account.` | Account enablement followed by an actual private target invocation. |",
        "| Gateway and Browser PrivateLink | NOT_AVAILABLE: EC2 endpoint-service catalog advertises no AgentCore service names in this account in either region. | Private endpoint ingress testing once services are exposed. Browser VPC egress passed separately. |",
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
        "",
        "## Cleanup",
        "",
    ]
    for region in REGIONS:
        inv = latest[region].get("cleanup.inventory", {})
        deleted = sum(bool(r.get("deleted")) for r in states[region]["resources"])
        lines += [f"**{region}:** inventory status `{inv.get('status', 'IN_PROGRESS')}`; "
                  f"{deleted}/{len(states[region]['resources'])} recorded resources marked deleted.", ""]
        if remaining[region]:
            lines += ["| Kind | Identifier | Remaining state |", "| --- | --- | --- |"]
            for r in remaining[region]:
                status = r.get("scheduledDeletion") or r.get("cleanupResult") or "Cleanup pending"
                ident = f"arn:aws-cn:kms:{region}:209915754514:key/{r['id']}" if r["kind"] == "kms" else r["id"]
                lines.append(f"| {r['kind']} | `{ident}` | {json.dumps(status).replace('|', '/')} |")
            lines.append("")
        else:
            lines += ["No recorded resources remain.", ""]
    lines += [
        "Resource deletion evidence is in each regional JSONL file under `cleanup.*`; exact inventories are in "
        "the regional state JSON files. KMS enforces a minimum seven-day deletion window. Service-owned "
        "credential secrets can also have service-managed deletion schedules; any such exceptions appear above.",
        "",
        "AWS [VPC documentation](docs/agentcore-vpc.md) states that AgentCore ENIs may persist for up to "
        "**eight hours** after deletion. Test security groups remain undeletable while those interfaces are attached. "
        "They are identified explicitly above when still present; no service interfaces were force-detached.",
        "",
    ]
    deferred_path = RESULTS / "deferred-cleanup.json"
    if deferred_path.exists():
        deferred = json.loads(deferred_path.read_text())
        lines += [
            f"Local deferred-cleanup worker status: **{deferred['status']}**, last updated "
            f"`{deferred['updatedAt']}`. [Worker status](results/deferred-cleanup.json). "
            "It retries only the recorded test security groups, then refreshes verification and this report. "
            "The workspace process must remain alive for this follow-up to run.",
            "",
        ]
    for region in REGIONS:
        verification_path = RESULTS / f"{region}-cleanup-verification.json"
        if verification_path.exists():
            verification = json.loads(verification_path.read_text())
            lines += [f"Independent read-only verification for `{region}`: **{verification['status']}** "
                      f"at `{verification['time']}`. [Details](results/{verification_path.name}).", ""]
            failed_kinds = {c["kind"] for c in verification["evidence"] if not c["ok"]}
            if failed_kinds == {"sg", "security-group-interfaces"}:
                lines += [
                    "The only verification failures are the retained test security group and its attached AgentCore "
                    "network interface. Test service resources, Lambda/API Gateway backends, EFS, S3 buckets, secrets, "
                    "and IAM roles are deleted; EC2 instances are terminated and no tagged EBS volumes remain. "
                    "The KMS key is confirmed `PendingDeletion`.",
                    "",
                ]
    lines += [
        "## Evidence and reproduction",
        "",
        "- [Final results JSON](results/final-results.json): latest evidence, classifications, counts, and cleanup inventory.",
        "- [Feature matrix CSV](results/feature-matrix.csv): one functional result per region/check, with source line references.",
        "- [Beijing chronological evidence](results/cn-north-1-results.jsonl) and [Ningxia chronological evidence](results/cn-northwest-1-results.jsonl).",
        "- [Beijing replay](results/cn-north-1-replay.html) and [Ningxia replay](results/cn-northwest-1-replay.html): self-contained rrweb artifacts.",
        "- [Beijing replay screenshot](results/cn-north-1-replay.png) and [Ningxia replay screenshot](results/cn-northwest-1-replay.png).",
        "- [Run notes and script map](README.md). Scripts preserve the investigation phases; a clean fresh run of all phases has not been validated.",
        "",
        "Credential-bearing query parameters and authorization values are redacted in exports. "
        "Resource ARNs, account ID, request IDs, and synthetic test content are retained for audit. "
        "Local generated signing keys and test-secret files are removed after cleanup; the AWS profile is unchanged.",
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
