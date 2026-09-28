> Historical initial-run report, archived before consolidation. Current conclusions: [REPORT.md](REPORT.md).

# AgentCore Gateway and Browser — AWS China live test report

Tested on **28 September 2026 UTC** using AWS profile **`china`**, account **`209915754514`**, in **Beijing (`cn-north-1`)** and **Ningxia (`cn-northwest-1`)**.

**Follow-up available:** [Chinese follow-up conclusions](FOLLOWUP.zh-CN.md) and [reproduction guide](REPRODUCE.zh-CN.md). The counts below describe the initial run; follow-up tests resolved authentication and proxy gaps. [Extended Live View tests](LIVEVIEW.zh-CN.md) also corrected the initial DCV failure: frames and input pass.

Both regions produced the same initial functional outcomes. Most tested capabilities worked. At the end of the initial run, four areas remained unresolved: Gateway caller-IAM forwarding, the tested Browser VPC proxy configuration, Playwright download retrieval, and DCV display connection. Authentication prerequisites and account networking availability prevented complete coverage of several other features.

## Results and scope

| Region | Checks | PASS | FAIL | BLOCKED | PARTIAL | NOT_AVAILABLE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cn-north-1 | 159 | 145 | 6 | 5 | 1 | 2 |
| cn-northwest-1 | 159 | 145 | 6 | 5 | 1 | 2 |

Counts use the **latest result for each named check in each region**. They include control-plane checks and diagnostic baselines. They exclude setup/phase wrappers, cleanup, documented negative checks, and `gateway.fixture.update`, `gateway.runtime.fixture_create`, `gateway.runtime.fixture_ready`. One product feature can have several checks; these totals are not a count of independent features. Earlier fixture failures and corrected attempts remain in the chronological JSONL evidence.

**PASS** means the named assertion succeeded; configuration-only checks are identified as such. **FAIL** means the attempted behavior failed in this test, without automatically attributing it to an AWS defect. **BLOCKED** means an account or identity prerequisite prevented execution. **PARTIAL** means only part of the feature was verified. **NOT_AVAILABLE** refers to the service catalog visible in this account and region.

This is feature-based API and browser integration coverage. It does not certify every configuration, protocol permutation, console workflow, quota boundary, performance characteristic, or third-party integration. Elicitation used form mode with MCP 2026-07-28; sampling used a synthetic client response. Legacy/URL elicitation variants and real-model sampling were not separately exercised.

Client environment: Python 3.12.13, boto3/botocore 1.43.103, Playwright 1.63.0, local headless Chromium 153.0.8010.12, and DCV Web SDK 1.14.1+build.0. The remote Browser reported Chromium 148.0.7778.258 in both regions. [Complete client versions](results/client-versions.json). Client compatibility remains a possible contributor to the download-retrieval and DCV failures.

## Passing coverage

| Area | Verified behavior in both regions |
| --- | --- |
| Gateway lifecycle | Create/get/list/update, tags, target pagination, active target update followed by invocation, target idempotency; deletion is tracked separately under cleanup. |
| Gateway inbound IAM | SigV4-authorized calls succeed; unsigned calls are rejected. |
| Lambda targets | Inline and S3 schemas; addition, Unicode echo, and target error responses. |
| OpenAPI and API Gateway targets | Inline/S3 schemas, IAM-authenticated backend calls, forwarded headers, REST stage filters and tool overrides. |
| Smithy | Schema import and actual Lambda `GetFunctionConcurrency` invocation. |
| MCP server targets | DEFAULT and DYNAMIC discovery, synchronization, refreshed schema, tools, prompts, resources, and resource templates. |
| MCP protocol/session support | 2025-03-26, 2025-06-18, 2025-11-25, and 2026-07-28; initialize/initialized handshake and 2026 server discovery. |
| MCP streaming and client requests | SSE results, progress/log notifications, form elicitation and synthetic sampling request/resume round trips. |
| Gateway interceptors | Request interceptor changes tool arguments; response interceptor inserts a verified marker. |
| Gateway encryption and authentication | Customer-managed KMS gateway plus tool invocation; outbound API key validated by backend; custom OAuth provider configuration. |
| Gateway HTTP and Runtime | HTTP passthrough; Runtime target invocation using the Gateway IAM role; direct Runtime and Gateway-role calls also pass with the STS credentials used in the failed caller-IAM comparison. |
| Gateway rate limits | Create/list/update/delete; zero-rate rule returns HTTP 429. |
| Browser lifecycle | Managed/custom browsers, get/list, tags, pagination, session idempotency, viewport/timeout settings, stop; profile management and tags. |
| Browser automation | CDP connection, HTTPS navigation, DOM extraction, forms, clicks, Unicode input, tabs, screenshots, upload, and download inside the remote browser. |
| Browser OS actions | All eight InvokeBrowser actions: mouseMove, mouseClick, mouseDrag, mouseScroll, keyType, keyPress, keyShortcut, screenshot. Typed input verified in DOM. |
| Browser state and access | Cookies/local storage; saved profile restores both; concurrent sessions remain isolated; automation disable rejects connections, re-enable permits reconnect. |
| Browser customization | Extension executes; managed URL blocklist enforced; recommended enterprise policies appear in Chrome policy UI. |
| Browser recording | Real S3 gzip NDJSON batches contain full snapshots; local rrweb replay reconstructs the test DOM. Beijing replay: 330 events; Ningxia: 467 events. |
| Browser networking | VPC private HTTP access; private CA rejected by default and trusted after root certificate configuration; EFS file persists into a later session. |
| Browser TTL | 60-second session timeout and automatic termination. |
| Observability | Gateway application logs and Browser usage logs delivered to CloudWatch; service metrics and CloudTrail events observed for both services. |

## Unresolved failures

| Area | Observation and baseline | Scope / next investigation |
| --- | --- | --- |
| Gateway caller-IAM forwarding | `CALLER_IAM_CREDENTIALS` target creation succeeds. Invocation returns HTTP 403, `The security token included in the request is invalid`. Reproduced with profile keys and STS temporary credentials. The same STS credentials successfully invoke the same Runtime directly and through the Gateway-role target. | Investigate credential forwarding for HTTP Runtime targets in the China partition. Service-role invocation is a tested working alternative. |
| Browser external proxy | Session API accepts the VPC proxy and Secrets Manager Basic credentials. HTTPS CONNECT fails with `ERR_TUNNEL_CONNECTION_FAILED`; bypass traffic returns Squid 403; a proxy-only HTTP hostname returns Squid DNS 503. A new Playwright context configured directly with the same private proxy and credentials successfully requests that HTTP hostname. | Three failed checks for this tested VPC proxy configuration. The HTTP baseline establishes fixture health; HTTPS CONNECT and bypass are not independently proven by that baseline. Do not generalize to every proxy deployment. |
| Browser Playwright download retrieval | `download.save_as()` yields 0 bytes instead of the expected 21. The remote browser's downloaded file contains `agentcore-download-ok`, verified through a file URL. | Remote download passes; local Playwright retrieval fails in this client/connection configuration. |
| Browser DCV live view | Presigned DCV authentication succeeds. Display connection fails before the first frame with `Failed to communicate with server`; the `/live-view/auth` WebSocket reports `Close received after close`. | Tested with AWS DCV Web SDK and local Chromium. Rendering and live-view input remain unverified. Root cause is unconfirmed; CDP and InvokeBrowser input pass independently. |

Caller-IAM request IDs from the final STS comparison, around **05:14:48 UTC**:

- Beijing: `0e842653-d009-4e91-84c3-9eefbf694e23`, `482c33e6-c640-477e-a0c6-2e938d3c7213`.
- Ningxia: `d226bc60-fd43-485b-a0eb-d20b448c7a3d`, `581a7630-162f-4b1d-95a0-ff0a3427ce5e`.

## Prerequisite gaps

| Feature | Result in both regions | What remains |
| --- | --- | --- |
| CUSTOM_JWT inbound auth | PARTIAL: public Microsoft OIDC discovery configuration and invalid-token rejection pass. | Valid JWT invocation requires an approved test issuer and signing credentials/test identity. |
| OAuth client credentials, authorization code, token exchange, JWT passthrough | BLOCKED for end-to-end flows; custom OAuth provider configuration passes. | Usable test provider and tokens/identity. The synthetic API Gateway fixture required AWS_IAM, which prevented serving the needed unauthenticated OIDC/Bearer endpoints. |
| Gateway private target | BLOCKED: API returns `Private endpoint configuration requires VPC egress feature to be enabled for this account.` | Account enablement followed by an actual private target invocation. |
| Gateway and Browser PrivateLink | NOT_AVAILABLE: EC2 endpoint-service catalog advertises no AgentCore service names in this account in either region. | Private endpoint ingress testing once services are exposed. Browser VPC egress passed separately. |

## Documented China exclusions

The [AWS China service differences page](https://docs.amazonaws.cn/en_us/aws/latest/userguide/bedrock-agentcore.html) excludes Gateway semantic search, Cognito authorizers, NONE inbound authorization, inference targets, the console connector catalog, WAF integration, Gateway rules, and ConfigBundle A/B testing. Browser Web Bot Auth and S3 Files mounts are also excluded. Private identity providers and the listed built-in OAuth providers are unavailable. These are not counted as failed supported features.

Live creation attempts confirmed rejection of **NONE inbound auth** and **semantic search** in both regions. The remaining exclusions are based on the documentation, without separate negative API tests. EFS mounting was tested successfully and is distinct from S3 Files mounting.

## Cleanup

**cn-north-1:** inventory status `FAIL`; 55/57 recorded resources marked deleted.

| Kind | Identifier | Remaining state |
| --- | --- | --- |
| kms | `arn:aws-cn:kms:cn-north-1:209915754514:key/9fc74828-2ad7-4602-b21b-054a406c75a0` | {"keyState": "PendingDeletion", "deletionDate": "2026-10-05 05:27:41.783000+00:00"} |
| sg | `sg-00ea1d13ed36ba5d3` | {"type": "ClientError", "message": "An error occurred (DependencyViolation) when calling the DeleteSecurityGroup operation: resource sg-00ea1d13ed36ba5d3 has a dependent object"} |

**cn-northwest-1:** inventory status `FAIL`; 55/57 recorded resources marked deleted.

| Kind | Identifier | Remaining state |
| --- | --- | --- |
| kms | `arn:aws-cn:kms:cn-northwest-1:209915754514:key/e9e12008-d491-4524-945e-6d358281618a` | {"keyState": "PendingDeletion", "deletionDate": "2026-10-05 05:27:32.722000+00:00"} |
| sg | `sg-074039951f97aedee` | {"type": "ClientError", "message": "An error occurred (DependencyViolation) when calling the DeleteSecurityGroup operation: resource sg-074039951f97aedee has a dependent object"} |

Resource deletion evidence is in each regional JSONL file under `cleanup.*`; exact inventories are in the regional state JSON files. KMS enforces a minimum seven-day deletion window. Service-owned credential secrets can also have service-managed deletion schedules; any such exceptions appear above.

AWS [VPC documentation](docs/agentcore-vpc.md) states that AgentCore ENIs may persist for up to **eight hours** after deletion. Test security groups remain undeletable while those interfaces are attached. They are identified explicitly above when still present; no service interfaces were force-detached.

Local deferred-cleanup worker status: **WAITING_FOR_AWS_ENI_RELEASE**, last updated `2026-09-28T06:48:05.017117+00:00`. [Worker status](results/deferred-cleanup.json). It retries only the recorded test security groups, then refreshes verification and this report. The workspace process must remain alive for this follow-up to run.

Independent read-only verification for `cn-north-1`: **FAIL** at `2026-09-28T06:22:11.919293+00:00`. [Details](results/cn-north-1-cleanup-verification.json).

The only verification failures are the retained test security group and its attached AgentCore network interface. Test service resources, Lambda/API Gateway backends, EFS, S3 buckets, secrets, and IAM roles are deleted; EC2 instances are terminated and no tagged EBS volumes remain. The KMS key is confirmed `PendingDeletion`.

Independent read-only verification for `cn-northwest-1`: **FAIL** at `2026-09-28T06:22:12.382020+00:00`. [Details](results/cn-northwest-1-cleanup-verification.json).

The only verification failures are the retained test security group and its attached AgentCore network interface. Test service resources, Lambda/API Gateway backends, EFS, S3 buckets, secrets, and IAM roles are deleted; EC2 instances are terminated and no tagged EBS volumes remain. The KMS key is confirmed `PendingDeletion`.

## Evidence and reproduction

- [Final results JSON](results/initial-results.json): latest evidence, classifications, counts, and cleanup inventory.
- [Feature matrix CSV](results/initial-feature-matrix.csv): one functional result per region/check, with source line references.
- [Beijing chronological evidence](results/cn-north-1-results.jsonl) and [Ningxia chronological evidence](results/cn-northwest-1-results.jsonl).
- [Beijing replay](results/cn-north-1-replay.html) and [Ningxia replay](results/cn-northwest-1-replay.html): self-contained rrweb artifacts.
- [Beijing replay screenshot](results/cn-north-1-replay.png) and [Ningxia replay screenshot](results/cn-northwest-1-replay.png).
- [Run notes and script map](README.md). Scripts preserve the investigation phases; a clean fresh run of all phases has not been validated.

Credential-bearing query parameters and authorization values are redacted in exports. Resource ARNs, account ID, request IDs, and synthetic test content are retained for audit. Local generated signing keys and test-secret files are removed after cleanup; the AWS profile is unchanged.

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
| `browser.live_view.dcv_frame_and_input` | FAIL | FAIL |
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
| `browser.proxy.authenticated_routing` | FAIL | FAIL |
| `browser.proxy.bypass` | FAIL | FAIL |
| `browser.proxy.fixture_baseline` | PASS | PASS |
| `browser.proxy.http_routing` | FAIL | FAIL |
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
| `gateway.jwt` | PARTIAL | PARTIAL |
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
| `gateway.outbound.caller_iam` | FAIL | FAIL |
| `gateway.outbound.caller_iam.direct_runtime_baseline` | PASS | PASS |
| `gateway.outbound.caller_iam.gateway_role_baseline` | PASS | PASS |
| `gateway.outbound.jwt_passthrough` | BLOCKED | BLOCKED |
| `gateway.outbound.oauth_authorization_code` | BLOCKED | BLOCKED |
| `gateway.outbound.oauth_client_credentials` | BLOCKED | BLOCKED |
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
