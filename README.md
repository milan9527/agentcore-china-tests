# AgentCore Gateway and Browser tests in AWS China

**Latest update — 29 September 2026:** Caller-IAM forwarding passed the unchanged reproduction in both regions: all eight selected checks per region passed, including all three previously failing caller paths. Cleanup verification passed. [中文报告](results/repro-caller-confirm-20260929/REPORT.zh-CN.md) · [English report](results/repro-caller-confirm-20260929/REPORT.md) · [responses/request IDs](results/repro-caller-confirm-20260929/invocation-results.csv).

Browser proxy follow-up: [中文结论](PROXY-VALIDATION.zh-CN.md) · [full English matrix](results/proxy-validation-20260928-r2/REPORT.md). Each region ran 95 checks (60 PASS, 35 FAIL), with every failure reproduced twice. Separate origin/proxy hosts confirm managed Squid denies HTTP 8000/8081 before the external proxy; HTTPS 8443 also fails before it. Standard-port routing, bypass, authentication controls, and multi-proxy selection pass. [Gateway China description wording](GATEWAY-DESCRIPTION.zh-CN.md).

Focused OAuth validation (28 September 2026, 08:27–08:29 UTC): [中文过程与结果](results/oauth-validation-20260928/REPORT.zh-CN.md) · [English report](results/oauth-validation-20260928/REPORT.md). In both regions, 2LO (Basic and POST client authentication) and the complete 3LO flow pass. Four OBO configurations remain blocked at Gateway target creation by the current account gate, confirmed by 16 HTTP 403 responses. [One-command reproduction](run_oauth_validation.py) · [request ID index](results/oauth-validation-20260928/request-index.csv).

OAuth scope: the tests use a self-hosted synthetic IdP through `CustomOauth2`, with OAuth client `cn-retest` and a random secret per region. Microsoft Entra ID, Google, Okta, and other third-party IdPs were not used. Passing 2LO/3LO results apply to this fixture; third-party compatibility and Microsoft OBO remain untested.

Latest follow-up: [中文版补测结论](FOLLOWUP.zh-CN.md) · [Live View 更正：画面和输入通过](LIVEVIEW.zh-CN.md) · [复现步骤](REPRODUCE.zh-CN.md) · [完整过程说明](WORKLOG.zh-CN.md).

For caller-IAM regression checks and the remaining zero-byte download issue, see [focused reproduction steps](REPRODUCE-ISSUES.zh-CN.md), including prerequisites, commands, comparison checks and cleanup.

Live integration investigation performed on 28 September 2026, with caller-IAM retested on 29 September, using AWS profile `china` in Beijing (`cn-north-1`) and Ningxia (`cn-northwest-1`).

Read the current [English report](REPORT.md) or [Chinese summary](SUMMARY.zh-CN.md), with detailed investigations in [FOLLOWUP.zh-CN.md](FOLLOWUP.zh-CN.md). Both main reports retain the initial 159-check population and apply matching follow-up results: **154 PASS, 1 FAIL, 2 BLOCKED, 2 NOT_AVAILABLE per region**. Live View display/input and the retested caller-IAM forwarding pass.

[results/final-results.json](results/final-results.json) and [results/feature-matrix.csv](results/feature-matrix.csv) contain the consolidated evidence and counts. The broader [follow-up matrix](results/followup-matrix.csv) includes added diagnostic checks. Initial reports are archived as [REPORT.initial.md](REPORT.initial.md) and [SUMMARY.initial.zh-CN.md](SUMMARY.initial.zh-CN.md), with [initial results](results/initial-results.json) and [initial matrix](results/initial-feature-matrix.csv).

The regional `*-results.jsonl` files retain the investigation chronology, including earlier attempts corrected later. A phase wrapper can pass even when an individual check records a failure: use individual check results. Process exit status alone is not a test verdict.

## Scripts

| Files | Purpose |
| --- | --- |
| `suite.py` | AWS sessions, profile selection, resource inventory, test result recording, phase dispatcher |
| `backend.py`, `prepare_tests.py` | Synthetic Lambda/API Gateway/MCP fixtures and China-specific setup corrections |
| `gateway*_tests.py`, `mcp_roundtrip_tests.py` | Gateway lifecycle, targets, protocols, auth, interceptors, rate limits |
| `runtime_gateway_tests.py`, `caller_baseline_tests.py` | Runtime target and same-credential caller-IAM comparisons |
| `browser*_tests.py`, `live_tests.py` | Browser automation, customization, profiles, downloads, DCV |
| `network_tests.py`, `private_server.py`, `proxy_tests.py` | Private HTTP/TLS server, proxy, VPC, EFS |
| `observability_tests.py`, `recording_tests.py` | Logs, metrics, CloudTrail, S3 recording and local rrweb replay |
| `final_checks_tests.py` | Pagination, idempotency, private-target availability and China exclusions |
| `cleanup_tests.py` | Delete only inventory-recorded test resources and associated logs |
| `verify_cleanup.py` | Read-only resource checks, including tagged EC2 volumes and residual network interfaces |
| `deferred_cleanup.py` | Bounded retry of the exact test security groups awaiting AWS ENI release |
| `export_report.py` | Build report, JSON, and CSV from local evidence; no AWS calls |

These are investigation scripts, with phased corrections and dependencies on persisted state. They are **not a validated one-command fresh-run harness**. Existing state refers to the completed run and deleted resources; review and adapt the setup before another live run.

## Environment and commands

Python 3.12, boto3/botocore 1.43.103, requests, Playwright/Chromium, websockets, and PyJWT/cryptography were used. Python dependencies are in [requirements.txt](requirements.txt). The local `dcv/` folder contains the AWS DCV Web SDK and its license files; `docs/rrweb-all.js` supports replay.

Exact versions are recorded in [results/client-versions.json](results/client-versions.json). Playwright was 1.63.0, local Chromium 153.0.8010.12, remote Chromium 148.0.7778.258, and DCV Web SDK 1.14.1+build.0.

Dependency setup, if the local environment needs rebuilding:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

Refresh the report from local evidence:

```bash
.venv/bin/python export_report.py
```

Rerun cleanup against this run's saved inventory:

```bash
.venv/bin/python suite.py cleanup --profile china
```

Use `--region cn-north-1` or `--region cn-northwest-1` to restrict an individual phase. Do not run concurrent mutating phases for the same region: they share a state file. Cleanup intentionally preserves KMS keys pending their minimum seven-day deletion window and records service-owned secret deletion schedules. Inspect `cleanup.inventory` and remaining resources after a cleanup run.

AWS documents that AgentCore ENIs can persist for up to eight hours after deletion. A local deferred-cleanup worker retries deletion of only the two test security groups for up to 8.5 hours, without force-detaching service interfaces. Its status is in `results/deferred-cleanup.json`, and output is in `results/deferred-cleanup.log`. It refreshes verification and the report on completion. This worker depends on the workspace process remaining alive; if interrupted, rerun the cleanup command above after the interfaces are released.

## China-specific run notes

- API endpoints use `.amazonaws.com.cn` and resource ARNs use `arn:aws-cn`. The tested AgentCore IAM trust principal is `bedrock-agentcore.amazonaws.com`.
- The preinstalled AWS CLI service models were too old for the tested features; the local boto3 version supplied current APIs.
- Unauthenticated synthetic API Gateway methods returned an ICP-registration 403 in this account. Backend methods were changed to AWS_IAM; Browser test pages used presigned API URLs. Regenerate these per browser session: observed execute-api signatures expired after five minutes even when a longer expiry was requested.
- Presigned private S3 object requests returned 401 in this environment. This observation is not a statement about general China S3 availability.
- Set a Gateway's customer KMS key at creation; an attempted key update on an existing gateway was rejected.
- Explicitly configure MCP `supportedVersions`; the default was 2025-03-26. Stateful clients must send `notifications/initialized`.
- A 2026 MCP backend must return `supportedVersions` and `resultType` from `server/discover`; otherwise negotiation can fall back to 2025.
- Create HTTP passthrough gateways without `protocolType="MCP"`.
- Browser VPC provisioning took more than three minutes. IAM changes also needed propagation time.
- Extension ZIP objects required S3 `ContentType=application/zip`. The managed URL blocklist test used the host pattern `blocked.agentcore.test`.

## Artifacts and retained metadata

Both `*-replay.html` files embed real recorded events and rrweb, with Play/Pause/seek controls. Replay reconstruction was verified with local Chromium while blocking external network requests. Screenshots are under `results/`, including browser/CDP, OS, Chrome policy, and replay images.

Final exports redact credential-bearing query parameters and authorization values. The evidence retains account/resource identifiers and synthetic content for troubleshooting. Generated local private keys and test-secret files are removed after cleanup. The `china` credential profile is not modified.
