# AgentCore Gateway and Browser — AWS China live test report

Tested on **28 September 2026 UTC**, with caller-IAM retested on **29 September**, using AWS profile **`china`**, account **`209915754514`**, in **Beijing (`cn-north-1`)** and **Ningxia (`cn-northwest-1`)**.

**Updated consolidated report:** includes authentication, proxy, download and extended Live View follow-up tests. [Chinese summary](SUMMARY.zh-CN.md), [detailed follow-up](FOLLOWUP.zh-CN.md), and [reproduction guide](REPRODUCE.zh-CN.md). The [initial report](REPORT.initial.md) is retained as history.

**Latest update — 29 September 2026:** Gateway caller-IAM forwarding passes in Beijing and Ningxia, with all 8/8 selected checks passing per region. The invalid-token 403 no longer occurs in the tested paths. Consolidated counts are now 154 PASS, 1 FAIL, 2 BLOCKED and 2 NOT_AVAILABLE per region. [Full retest evidence](results/repro-caller-confirm-20260929/REPORT.md).

**Outbound OAuth validation, 28 September 2026, 08:27–08:29 UTC:** 2LO (Basic and POST client authentication) and complete 3LO, repeat authorized access, and user isolation pass in both regions. Four OBO provider configurations are accepted, but 16 Gateway target creation attempts return the explicit account-gating 403. The separate 8 PASS / 4 BLOCKED checks per region do not change the 159-check population below. [Full English evidence and reproduction](results/oauth-validation-20260928/REPORT.md) · [中文报告](results/oauth-validation-20260928/REPORT.zh-CN.md).

**OAuth provider scope:** this run uses a self-hosted synthetic IdP through `CustomOauth2`, with OAuth client `cn-retest` and a random client secret per region. Microsoft Entra ID, Google, Okta, and other third-party IdPs were not used. Passing 2LO/3LO results apply to this test IdP; third-party compatibility and Microsoft OBO remain untested. OBO client configuration succeeded, but Gateway target creation was account-gated before any Gateway token exchange.

**Both regions pass Live View display and mouse/keyboard input.** The previous DCV failure verdict was caused by the test exiting on an authentication-socket close error before the first frame. JWT, OAuth client credentials, OAuth authorization code and JWT passthrough also pass. Browser proxy routing passes with the tested standard ports and configuration. Caller-IAM forwarding now passes the unchanged reproduction in both regions on 29 September. The remaining failure in the original 159-check population is Playwright `download.save_as()` retrieval; a verified remote-file retrieval alternative is available.

## Results and scope

| Region | Checks | PASS | FAIL | BLOCKED | PARTIAL | NOT_AVAILABLE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cn-north-1 | 159 | 154 | 1 | 2 | 0 | 2 |
| cn-northwest-1 | 159 | 154 | 1 | 2 | 0 | 2 |

Counts retain the **159 initial named checks per region**, replacing matching checks with their latest follow-up result. Newly added diagnostic checks are listed separately in the [follow-up matrix](results/followup-matrix.csv), so they do not inflate this comparison. The initial count was 145 PASS, 6 FAIL, 5 BLOCKED, 1 PARTIAL and 2 NOT_AVAILABLE per region. Nine checks now pass: JWT, three OAuth/passthrough checks, three proxy checks, Live View, and caller-IAM forwarding. Counts include control-plane checks and diagnostic baselines. They exclude setup/phase wrappers, cleanup, documented negative checks, and `gateway.fixture.update`, `gateway.runtime.fixture_create`, `gateway.runtime.fixture_ready`. One product feature can have several checks; these totals are not a count of independent features. Earlier fixture failures and corrected attempts remain in the chronological JSONL evidence.

**PASS** means the named assertion succeeded; configuration-only checks are identified as such. **FAIL** means the attempted behavior failed in this test, without automatically attributing it to an AWS defect. **BLOCKED** means an account or identity prerequisite prevented execution. **PARTIAL** means only part of the feature was verified. **NOT_AVAILABLE** refers to the service catalog visible in this account and region.

This is feature-based API and browser integration coverage. It does not certify every configuration, protocol permutation, console workflow, quota boundary, performance characteristic, or third-party integration. Elicitation used form mode and an actual URL authorization-code round trip with MCP 2026-07-28; sampling used a synthetic client response. Other elicitation variants and real-model sampling were not separately exercised. A proxy PASS applies to the explicitly verified configuration; nonstandard-port and upstream-only DNS failures remain recorded.

Client environment: Python 3.12.13, boto3/botocore 1.43.103, Playwright 1.63.0, local headless Chromium 153.0.8010.12, and DCV Web SDK 1.14.1+build.0. The remote Browser reported Chromium 148.0.7778.258 in both regions. [Complete client versions](results/client-versions.json). Follow-up used the official `bedrock-agentcore` TypeScript SDK 0.4.4 BrowserLiveView component and its bundled DCV client. Playwright 1.60.0 was also tested against the Chromium 148 series: `save_as()` still returned zero bytes. Live View passes after fixing the test's early-exit condition.

## Passing coverage

| Area | Verified behavior in both regions |
| --- | --- |
| Gateway lifecycle | Create/get/list/update, tags, target pagination, active target update followed by invocation, target idempotency; deletion is tracked separately under cleanup. |
| Gateway inbound IAM | SigV4-authorized calls succeed; unsigned calls are rejected. |
| Gateway JWT and OAuth | Valid RS256 JWT invokes a Lambda tool; incorrect audience/client/scope and expired tokens are rejected. Client credentials and authorization code flows invoke protected backends with the expected grant. JWT passthrough preserves the token SHA-256. |
| Lambda targets | Inline and S3 schemas; addition, Unicode echo, and target error responses. |
| OpenAPI and API Gateway targets | Inline/S3 schemas, IAM-authenticated backend calls, forwarded headers, REST stage filters and tool overrides. |
| Smithy | Schema import and actual Lambda `GetFunctionConcurrency` invocation. |
| MCP server targets | DEFAULT and DYNAMIC discovery, synchronization, refreshed schema, tools, prompts, resources, and resource templates. |
| MCP protocol/session support | 2025-03-26, 2025-06-18, 2025-11-25, and 2026-07-28; initialize/initialized handshake and 2026 server discovery. |
| MCP streaming and client requests | SSE results, progress/log notifications, form elicitation, URL elicitation with OAuth callback/session binding/resumption, and synthetic sampling request/resume round trips. |
| Gateway interceptors | Request interceptor changes tool arguments; response interceptor inserts a verified marker. |
| Gateway encryption and authentication | Customer-managed KMS gateway plus tool invocation; outbound API key validated by backend; custom OAuth provider configuration. |
| Gateway HTTP and Runtime | HTTP passthrough; Runtime target invocation using the Gateway IAM role; caller-IAM forwarding now passes using STS GetSessionToken and AssumeRole, including AWS_IAM and AUTHENTICATE_ONLY inbound. The same credentials pass direct Runtime and Gateway-role controls. |
| Gateway rate limits | Create/list/update/delete; zero-rate rule returns HTTP 429. |
| Browser lifecycle | Managed/custom browsers, get/list, tags, pagination, session idempotency, viewport/timeout settings, stop; profile management and tags. |
| Browser automation | CDP connection, HTTPS navigation, DOM extraction, forms, clicks, Unicode input, tabs, screenshots, upload, and download inside the remote browser. |
| Browser OS actions | All eight InvokeBrowser actions: mouseMove, mouseClick, mouseDrag, mouseScroll, keyType, keyPress, keyShortcut, screenshot. Typed input verified in DOM. |
| Browser state and access | Cookies/local storage; saved profile restores both; concurrent sessions remain isolated; automation disable rejects connections, re-enable permits reconnect. |
| Browser customization | Extension executes; managed URL blocklist enforced; recommended enterprise policies appear in Chrome policy UI. |
| Browser recording | Real S3 gzip NDJSON batches contain full snapshots; local rrweb replay reconstructs the test DOM. Beijing replay: 330 events; Ningxia: 467 events. |
| Browser networking | VPC private HTTP access; private CA rejected by default and trusted after root certificate configuration; EFS file persists into a later session. |
| Browser proxy | Basic-auth and no-auth routing pass on HTTP 80 and HTTPS CONNECT 443; explicit `externalProxy.domainPatterns` resolves upstream-only hostnames; bypass passes in a separate session. |
| Browser Live View | Official component renders frames and transmits mouse/keyboard input. Initial connection and fresh-signature reconnect each observed for 300 seconds per region, with incoming bytes increasing throughout. |
| Browser remote file retrieval alternative | CDP `DOM.setFileInputFiles` plus `File.arrayBuffer()` retrieves exact 21-byte text and 8192-byte binary files; byte equality and SHA-256 verified in both regions. |
| Browser TTL | 60-second session timeout and automatic termination. |
| Observability | Gateway application logs and Browser usage logs delivered to CloudWatch; service metrics and CloudTrail events observed for both services. |

## Live View correction: display and input pass

The earlier test exited when `probe.errors.length > 0`. At about two seconds, the `/live-view/auth` WebSocket reported `Close received after close` and an authentication error callback reported `Failed to communicate with server.` Authentication had already succeeded and the display connection was still being established. The test stopped too early; this was not evidence that display connection had failed.

Keeping the default 300-second SigV4 URL and waiting for the actual first frame yielded the following results. Each region was observed for five minutes, then reconnected to the same Browser session with a fresh signature and observed for another five minutes. Browser session timeout was 1800 seconds.

| Region | Attempt | Authentication success (s) | Auth close error (s) | Display connected (s) | First frame (s) | Observation (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| cn-north-1 | Initial | 1.794 | 2.024 | 3.016 | 6.450 | 300.462 |
| cn-north-1 | Fresh-signature reconnect | 2.151 | 2.377 | 3.496 | 6.718 | 300.487 |
| cn-northwest-1 | Initial | 1.864 | 2.111 | 3.189 | 6.728 | 300.524 |
| cn-northwest-1 | Fresh-signature reconnect | 2.172 | 2.429 | 3.599 | 7.514 | 300.540 |

Incoming WebSocket bytes increased at every 30-second observation and the remote clock continued changing. These counters include protocol messages, so they are not video-frame counts. This demonstrates the tested ten-minute viewing sequence, not long-duration or load certification.

A separate mouse/keyboard check passed in both regions after correcting the click coordinate for the browser toolbar: the full window was 719 pixels high and content was 632 pixels high, a difference of 87 pixels. Text typed through Live View was read back from the remote DOM as `dcv-official-input-ok`. [Beijing screenshot](results/retest-live-signature/cn-north-1-official-live.png) and [Ningxia screenshot](results/retest-live-signature/cn-northwest-1-official-live.png).

The extended-observation combined display/input checks remain FAIL in the historical log because they used incorrect click coordinates. Separate display evidence and the corrected input checks support the appended PASS verdicts. The official SDK connection logic was unchanged; the test now waits up to 120 seconds for the first frame without treating every auth-socket error as terminal.

Increasing the URL signature lifetime to 900 seconds caused an auth WebSocket 403 in both regions; restoring the default 300 seconds allowed authentication. Signature lifetime and first-frame observation timeout are separate settings. The auth close error's internal cause remains unconfirmed, but it did not prevent display or input in these tests.

The SDK URL generator hardcodes `.amazonaws.com`; tests signed the actual service-returned `.amazonaws.com.cn` endpoint. [Full timing, evidence and reproduction](LIVEVIEW.zh-CN.md).

## Proxy configuration boundaries

A fresh proxy matrix used separate origin and proxy EC2 instances in each region: **95 checks per region, 60 PASS / 35 FAIL**, with all failures reproduced twice (260 observations overall). Managed HTTP 8000/8081 requests returned `squid/6.13` and `ERR_ACCESS_DENIED 0` before reaching the external proxy; HTTPS 8443 also failed before it. Direct and explicit Playwright-proxy controls passed on all five destination ports. Standard-port IP/hostname/suffix bypass, bad/missing credential controls, and specific/default multi-proxy selection passed. The precise internal Squid ACL remains unreadable. These scenario counts are separate from the original 159-check population. [Full evidence](results/proxy-validation-20260928-r2/REPORT.md) · [中文结论](PROXY-VALIDATION.zh-CN.md).

Basic-auth and no-auth external proxies pass HTTP 80, HTTPS CONNECT 443, explicit domain routing and an independently tested bypass rule. For upstream-only DNS, place `domainPatterns` inside `externalProxy`. Use a bare host/IP for `server`, without `http://`. Test route and bypass assertions separately if reverse DNS could make both match the same host.

HTTP 8000 and HTTPS 8443 failed through the built-in proxy; upstream-only DNS without explicit domain patterns returned Squid DNS 503. These failed configurations remain in the evidence. The proxy PASS verdict is limited to the verified combinations. Server logs verify actual GET/CONNECT traffic and successful credential checks.

## Unresolved failures

| Area | Observation and baseline | Scope / next investigation |
| --- | --- | --- |
| Browser Playwright download retrieval | `download.save_as()` returns zero bytes in Playwright 1.63.0 and 1.60.0. The returned file path exists with correct contents in the remote browser but not on the client. Local Chromium baseline passes. | Failure is in remote-file retrieval in this CDP setup. [download_remote_file.py](download_remote_file.py) is a verified alternative for the tested text and binary files; large files were not benchmarked. |

## Caller-IAM forwarding: original error resolved in the tested paths

On **29 September 2026, 01:58–01:59 UTC**, fresh environments passed all eight selected checks per region. All three caller-forwarding combinations returned HTTP 200 and sum=42 (AssumeRole with AWS_IAM, AssumeRole with AUTHENTICATE_ONLY, and GetSessionToken); all five same-credential direct/role controls passed. Core invocation scripts and SDK versions match the 28 September run. The earlier invalid-token 403 is no longer reproduced in these paths. This establishes the observed behavior, not an AWS deployment time or an internal root cause. [Current report](results/repro-caller-confirm-20260929/REPORT.md), [console](results/repro-caller-confirm-20260929/console.log), [responses/request IDs](results/repro-caller-confirm-20260929/invocation-results.csv).

| Caller credentials / inbound mode | Beijing | Ningxia |
| --- | --- | --- |
| AssumeRole + AWS_IAM | HTTP 200, sum=42 | HTTP 200, sum=42 |
| AssumeRole + AUTHENTICATE_ONLY | HTTP 200, sum=42 | HTTP 200, sum=42 |
| GetSessionToken + AWS_IAM | HTTP 200, sum=42 | HTTP 200, sum=42 |

All resources created for this retest were cleaned up, with independent read-only verification passing in both regions. Other features were not retested on 29 September.

The **28 September 07:53 UTC** run had five passing controls and three failing caller paths per region; its [report and evidence](results/repro-caller-confirm-20260928/REPORT.zh-CN.md) remain unchanged. Earlier failing AssumeRole request IDs are retained below:

| Region | AWS_IAM inbound | AUTHENTICATE_ONLY inbound |
| --- | --- | --- |
| Beijing | `b3752ba3-ad3b-4baf-ba50-f456443ceb33`, `e1e08000-7b81-47f6-9507-b4bb68f16e90` | `4b462c3a-38f7-42d0-8941-9734c6b6355e`, `100bbec5-c396-4a8d-a994-4ffc7ad7d593` |
| Ningxia | `3ed694a0-36cf-4bbb-8341-1773d8e3a05f`, `f70990fb-f44e-44b9-8a1b-b05589029139` | `780aea03-3c6a-4dd3-a1e3-0673c76f24df`, `693f6dbf-bebd-4fd6-8ade-332b50a8aaeb` |

## Prerequisite gaps

| Feature | Result in both regions | What remains |
| --- | --- | --- |
| OAuth Token Exchange | BLOCKED: provider configuration succeeds, but target creation explicitly returns `Token Exchange is not available for this account`. | Account enablement by AWS; a usable synthetic issuer was already supplied. |
| Gateway private target | BLOCKED: API returns `Private endpoint configuration requires VPC egress feature to be enabled for this account.` | Account enablement followed by an actual private target invocation. |
| Gateway and Browser PrivateLink | NOT_AVAILABLE: EC2 endpoint-service catalog advertises no AgentCore service names in this account in either region. | Private endpoint ingress testing once services are exposed. Browser VPC egress passed separately. |

These availability results apply to the tested account and regions at test time. JWT, client credentials, authorization code and JWT passthrough no longer have missing-issuer prerequisites: a temporary synthetic HTTPS OIDC/OAuth provider completed those tests and has been shut down.

## Documented China exclusions

The [AWS China service differences page](https://docs.amazonaws.cn/en_us/aws/latest/userguide/bedrock-agentcore.html) excludes Gateway semantic search, Cognito authorizers, NONE inbound authorization, inference targets, the console connector catalog, WAF integration, Gateway rules, and ConfigBundle A/B testing. Browser Web Bot Auth and S3 Files mounts are also excluded. Private identity providers and the listed built-in OAuth providers are unavailable. These are not counted as failed supported features.

Live creation attempts confirmed rejection of **NONE inbound auth** and **semantic search** in both regions. The remaining exclusions are based on the documentation, without separate negative API tests. EFS mounting was tested successfully and is distinct from S3 Files mounting.
The China overview lists AWS_IAM and CUSTOM_JWT inbound authorization. In this account, AUTHENTICATE_ONLY Gateway creation was also accepted in both regions, and Gateway-role outbound invocation passed with that inbound mode. The report retains this observed documentation difference.

## Cleanup

This is a summary of saved inventories and read-only verification; report generation makes no AWS calls. The Live View follow-up sessions have been stopped and all three Live View test directories have passing cleanup verification in both regions. Earlier test compute and service resources are deleted. Any remaining recorded resources across the initial and follow-up runs are listed below.

| Region | Run directory | Kind | Identifier | Recorded state |
| --- | --- | --- | --- | --- |
| cn-north-1 | `results` | kms | `9fc74828-2ad7-4602-b21b-054a406c75a0` | PendingDeletion; deletion 2026-10-05 05:27:41.783000+00:00 |
| cn-northwest-1 | `results` | kms | `e9e12008-d491-4524-945e-6d358281618a` | PendingDeletion; deletion 2026-10-05 05:27:32.722000+00:00 |

KMS has a minimum seven-day deletion window; the two initial-run keys are scheduled for 5 October 2026. AWS [VPC documentation](docs/agentcore-vpc.md) says service-owned ENIs may persist for up to eight hours. Security groups cannot be deleted while those ENIs remain attached. No service interfaces were force-detached.

[All-run cleanup inventory](results/followup-cleanup.json). Local deferred-cleanup workers retry the recorded security groups for a bounded period and depend on the workspace processes remaining alive:

- [results worker](results/deferred-cleanup.json): `COMPLETE`, last recorded update `2026-09-28T13:22:56.148058+00:00`.
- [results/retest worker](results/retest/deferred-cleanup.json): `COMPLETE`, last recorded update `2026-09-28T14:24:21.618360+00:00`.

| Run directory | Region | Saved cleanup verification | Verified at (UTC) |
| --- | --- | --- | --- |
| `results` | cn-north-1 | [PASS](results/cn-north-1-cleanup-verification.json) | 2026-09-28T13:22:54.324006+00:00 |
| `results` | cn-northwest-1 | [PASS](results/cn-northwest-1-cleanup-verification.json) | 2026-09-28T13:22:56.018952+00:00 |
| `results/retest` | cn-north-1 | [PASS](results/retest/cn-north-1-cleanup-verification.json) | 2026-09-28T14:24:20.065897+00:00 |
| `results/retest` | cn-northwest-1 | [PASS](results/retest/cn-northwest-1-cleanup-verification.json) | 2026-09-28T14:24:21.495526+00:00 |
| `results/retest-browser` | cn-north-1 | [PASS](results/retest-browser/cn-north-1-cleanup-verification.json) | 2026-09-28T06:16:50.697129+00:00 |
| `results/retest-browser` | cn-northwest-1 | [PASS](results/retest-browser/cn-northwest-1-cleanup-verification.json) | 2026-09-28T06:16:50.911643+00:00 |
| `results/retest-livewait` | cn-north-1 | [PASS](results/retest-livewait/cn-north-1-cleanup-verification.json) | 2026-09-28T06:46:08.919332+00:00 |
| `results/retest-livewait` | cn-northwest-1 | [PASS](results/retest-livewait/cn-northwest-1-cleanup-verification.json) | 2026-09-28T06:46:09.153456+00:00 |
| `results/retest-live-signature` | cn-north-1 | [PASS](results/retest-live-signature/cn-north-1-cleanup-verification.json) | 2026-09-28T06:44:43.115182+00:00 |
| `results/retest-live-signature` | cn-northwest-1 | [PASS](results/retest-live-signature/cn-northwest-1-cleanup-verification.json) | 2026-09-28T06:44:43.328797+00:00 |
| `results/retest-livewait-default` | cn-north-1 | [PASS](results/retest-livewait-default/cn-north-1-cleanup-verification.json) | 2026-09-28T06:48:51.412130+00:00 |
| `results/retest-livewait-default` | cn-northwest-1 | [PASS](results/retest-livewait-default/cn-northwest-1-cleanup-verification.json) | 2026-09-28T06:48:51.672482+00:00 |
| `results/repro-caller-confirm-20260928` | cn-north-1 | [PASS](results/repro-caller-confirm-20260928/cn-north-1-cleanup-verification.json) | 2026-09-28T07:54:37.149770+00:00 |
| `results/repro-caller-confirm-20260928` | cn-northwest-1 | [PASS](results/repro-caller-confirm-20260928/cn-northwest-1-cleanup-verification.json) | 2026-09-28T07:54:37.505405+00:00 |
| `results/repro-caller-confirm-20260929` | cn-north-1 | [PASS](results/repro-caller-confirm-20260929/cn-north-1-cleanup-verification.json) | 2026-09-29T02:00:22.602867+00:00 |
| `results/repro-caller-confirm-20260929` | cn-northwest-1 | [PASS](results/repro-caller-confirm-20260929/cn-northwest-1-cleanup-verification.json) | 2026-09-29T02:00:23.111617+00:00 |

## Evidence and reproduction

- [Final results JSON](results/final-results.json): latest evidence, classifications, counts, and cleanup inventory.
- [Feature matrix CSV](results/feature-matrix.csv): one functional result per region/check, with source line references.
- [Initial results JSON](results/initial-results.json) and [initial matrix](results/initial-feature-matrix.csv): unchanged initial functional outcomes.
- [Full chronology](results/followup-history.jsonl) and [follow-up matrix](results/followup-matrix.csv): failed configurations, diagnostics, corrections, and added checks.
- [Beijing chronological evidence](results/cn-north-1-results.jsonl) and [Ningxia chronological evidence](results/cn-northwest-1-results.jsonl).
- [Beijing replay](results/cn-north-1-replay.html) and [Ningxia replay](results/cn-northwest-1-replay.html): self-contained rrweb artifacts.
- [Beijing replay screenshot](results/cn-north-1-replay.png) and [Ningxia replay screenshot](results/cn-northwest-1-replay.png).
- [Run notes and script map](README.md). Scripts preserve the investigation phases; a clean fresh run of all phases has not been validated.

Credential-bearing query parameters and authorization values are redacted in exports. Resource ARNs, account ID, request IDs, and synthetic test content are retained for audit. Local generated signing keys and test-secret files are removed after cleanup; the AWS profile is unchanged.
Per-request auditing and phase source snapshots were added during the follow-up. Earlier missing raw requests were not reconstructed. Audit coverage includes registered SDK clients and traced requests, not every CDP/DCV message or a complete network capture.

Sources consulted: [China availability/differences](docs/bedrock-agentcore.md), [Gateway features](docs/gateway-features.md), [Gateway outbound auth](docs/gateway-outbound-auth.md), [MCP targets](docs/gateway-target-MCPservers.md), [Browser features](docs/browser-features.md), [Browser tool](docs/browser-tool.md), and the API/service-model snapshots in `docs/`. China-specific documentation takes precedence over globally described capabilities.

## Detailed functional matrix

Each identifier matches the `feature` field in the JSON and CSV evidence. The latest row's exact source file and line are included in those exports.

| Check | Beijing | Ningxia |
| --- | --- | --- |
| `browser.cdp.connect` | PASS | PASS |
| `browser.cdp.screenshot` | PASS | PASS |
| `browser.certificates.start_with_root_ca` | PASS | PASS |
| `browser.certificates.stop` | PASS | PASS |
| `browser.certificates.trusted_https` | PASS | PASS |
| `browser.certificates.untrusted_rejected` | PASS | PASS |
| `browser.cookies_local_storage` | PASS | PASS |
| `browser.custom.create_recording_managed_policies` | PASS | PASS |
| `browser.custom.features` | PASS | PASS |
| `browser.custom.get_ready` | PASS | PASS |
| `browser.custom.start_extensions_recommended_policy` | PASS | PASS |
| `browser.custom.stop` | PASS | PASS |
| `browser.download.playwright_save_as` | FAIL | FAIL |
| `browser.efs` | PASS | PASS |
| `browser.efs.session_start` | PASS | PASS |
| `browser.enterprise.managed_enforced` | PASS | PASS |
| `browser.enterprise.policies` | PASS | PASS |
| `browser.enterprise.recommended_loaded` | PASS | PASS |
| `browser.extensions.executed` | PASS | PASS |
| `browser.file_download` | PASS | PASS |
| `browser.file_upload` | PASS | PASS |
| `browser.forms_click_unicode_extract` | PASS | PASS |
| `browser.isolation.concurrent_start` | PASS | PASS |
| `browser.isolation.cookies_local_storage` | PASS | PASS |
| `browser.isolation.stop` | PASS | PASS |
| `browser.list` | PASS | PASS |
| `browser.live_view.dcv_frame_and_input` | PASS | PASS |
| `browser.live_view.presigned_access` | PASS | PASS |
| `browser.managed.start_viewport_timeout` | PASS | PASS |
| `browser.managed.stop` | PASS | PASS |
| `browser.multiple_tabs` | PASS | PASS |
| `browser.navigation_https_dom` | PASS | PASS |
| `browser.observability.cloudtrail` | PASS | PASS |
| `browser.observability.log_delivery_received` | PASS | PASS |
| `browser.observability.metrics` | PASS | PASS |
| `browser.observability.usage_log_configure` | PASS | PASS |
| `browser.os.input_effect` | PASS | PASS |
| `browser.os.keyPress` | PASS | PASS |
| `browser.os.keyShortcut` | PASS | PASS |
| `browser.os.keyType` | PASS | PASS |
| `browser.os.mouseClick` | PASS | PASS |
| `browser.os.mouseDrag` | PASS | PASS |
| `browser.os.mouseMove` | PASS | PASS |
| `browser.os.mouseScroll` | PASS | PASS |
| `browser.os.screenshot` | PASS | PASS |
| `browser.pagination` | PASS | PASS |
| `browser.private_link` | NOT_AVAILABLE | NOT_AVAILABLE |
| `browser.profile.cookies_local_storage_restored` | PASS | PASS |
| `browser.profile.create` | PASS | PASS |
| `browser.profile.get` | PASS | PASS |
| `browser.profile.list` | PASS | PASS |
| `browser.profile.restore_start` | PASS | PASS |
| `browser.profile.save` | PASS | PASS |
| `browser.profile.session_stop` | PASS | PASS |
| `browser.profile.tags` | PASS | PASS |
| `browser.proxy.authenticated_routing` | PASS | PASS |
| `browser.proxy.bypass` | PASS | PASS |
| `browser.proxy.fixture_baseline` | PASS | PASS |
| `browser.proxy.http_routing` | PASS | PASS |
| `browser.proxy.start_basic_auth_bypass` | PASS | PASS |
| `browser.proxy.stop` | PASS | PASS |
| `browser.recording.replay` | PASS | PASS |
| `browser.recording.s3_delivery` | PASS | PASS |
| `browser.session.get` | PASS | PASS |
| `browser.session.idempotency` | PASS | PASS |
| `browser.session.list` | PASS | PASS |
| `browser.session.stopped_status` | PASS | PASS |
| `browser.stream.disable` | PASS | PASS |
| `browser.stream.disabled_enforced` | PASS | PASS |
| `browser.stream.enable` | PASS | PASS |
| `browser.stream.reenabled_connect` | PASS | PASS |
| `browser.tags.add` | PASS | PASS |
| `browser.tags.list` | PASS | PASS |
| `browser.tags.remove` | PASS | PASS |
| `browser.ttl.auto_termination` | PASS | PASS |
| `browser.ttl.short_session` | PASS | PASS |
| `browser.vpc.create` | PASS | PASS |
| `browser.vpc.private_http` | PASS | PASS |
| `browser.vpc.ready` | PASS | PASS |
| `browser.vpc.start` | PASS | PASS |
| `browser.vpc.stop` | PASS | PASS |
| `gateway.api_gateway.filters_overrides` | PASS | PASS |
| `gateway.api_gateway.iam_invocation` | PASS | PASS |
| `gateway.create_iam` | PASS | PASS |
| `gateway.debug.target_error` | PASS | PASS |
| `gateway.get_ready` | PASS | PASS |
| `gateway.http_passthrough` | PASS | PASS |
| `gateway.iam.unsigned_denied` | PASS | PASS |
| `gateway.interceptors.configure` | PASS | PASS |
| `gateway.interceptors.remove` | PASS | PASS |
| `gateway.interceptors.response_effect` | PASS | PASS |
| `gateway.jwt` | PASS | PASS |
| `gateway.jwt.configuration_and_rejection` | PASS | PASS |
| `gateway.kms` | PASS | PASS |
| `gateway.lambda.inline_target` | PASS | PASS |
| `gateway.lambda.invoke_add` | PASS | PASS |
| `gateway.lambda.invoke_unicode` | PASS | PASS |
| `gateway.lambda.s3_invoke` | PASS | PASS |
| `gateway.lambda.s3_schema` | PASS | PASS |
| `gateway.list` | PASS | PASS |
| `gateway.mcp.elicitation_roundtrip` | PASS | PASS |
| `gateway.mcp.initialize.2025-03-26` | PASS | PASS |
| `gateway.mcp.initialize.2025-06-18` | PASS | PASS |
| `gateway.mcp.initialize.2025-11-25` | PASS | PASS |
| `gateway.mcp.prompts_get` | PASS | PASS |
| `gateway.mcp.prompts_list` | PASS | PASS |
| `gateway.mcp.resources_list` | PASS | PASS |
| `gateway.mcp.resources_read` | PASS | PASS |
| `gateway.mcp.resources_templates_list` | PASS | PASS |
| `gateway.mcp.sampling_roundtrip` | PASS | PASS |
| `gateway.mcp.server_discover.2026-07-28` | PASS | PASS |
| `gateway.mcp.tools_list` | PASS | PASS |
| `gateway.mcp.tools_list.2026-07-28` | PASS | PASS |
| `gateway.mcp_server.dynamic_invoke` | PASS | PASS |
| `gateway.mcp_server.dynamic_listing` | PASS | PASS |
| `gateway.mcp_server.invoke` | PASS | PASS |
| `gateway.mcp_server.refresh_schema` | PASS | PASS |
| `gateway.mcp_server.synchronize` | PASS | PASS |
| `gateway.mcp_server.target` | PASS | PASS |
| `gateway.metadata.request_header` | PASS | PASS |
| `gateway.observability.cloudtrail` | PASS | PASS |
| `gateway.observability.log_delivery_configure` | PASS | PASS |
| `gateway.observability.log_delivery_received` | PASS | PASS |
| `gateway.observability.metrics` | PASS | PASS |
| `gateway.observability.traced_invocation` | PASS | PASS |
| `gateway.openapi.inline_target` | PASS | PASS |
| `gateway.openapi.invoke` | PASS | PASS |
| `gateway.openapi.s3_invoke` | PASS | PASS |
| `gateway.openapi.s3_schema` | PASS | PASS |
| `gateway.outbound.api_key` | PASS | PASS |
| `gateway.outbound.caller_iam` | PASS | PASS |
| `gateway.outbound.caller_iam.direct_runtime_baseline` | PASS | PASS |
| `gateway.outbound.caller_iam.gateway_role_baseline` | PASS | PASS |
| `gateway.outbound.jwt_passthrough` | PASS | PASS |
| `gateway.outbound.oauth_authorization_code` | PASS | PASS |
| `gateway.outbound.oauth_client_credentials` | PASS | PASS |
| `gateway.outbound.oauth_configuration` | PASS | PASS |
| `gateway.outbound.oauth_token_exchange` | BLOCKED | BLOCKED |
| `gateway.private_link` | NOT_AVAILABLE | NOT_AVAILABLE |
| `gateway.private_target` | BLOCKED | BLOCKED |
| `gateway.protocols.configure` | PASS | PASS |
| `gateway.rate_limits` | PASS | PASS |
| `gateway.runtime.role_invocation` | PASS | PASS |
| `gateway.runtime.runtime-caller.target` | PASS | PASS |
| `gateway.runtime.runtime-role.target` | PASS | PASS |
| `gateway.sessions.full_handshake` | PASS | PASS |
| `gateway.sessions.initialize` | PASS | PASS |
| `gateway.sessions_streaming.configure` | PASS | PASS |
| `gateway.smithy` | PASS | PASS |
| `gateway.streaming.progress_logging` | PASS | PASS |
| `gateway.streaming.tool_call` | PASS | PASS |
| `gateway.tags.add` | PASS | PASS |
| `gateway.tags.list` | PASS | PASS |
| `gateway.tags.remove` | PASS | PASS |
| `gateway.targets.idempotency` | PASS | PASS |
| `gateway.targets.list` | PASS | PASS |
| `gateway.targets.pagination` | PASS | PASS |
| `gateway.targets.update_active_and_invoke` | PASS | PASS |
| `gateway.update_description` | PASS | PASS |
