# Gateway outbound OAuth: 2LO / 3LO / OBO validation

2026-09-28T08:27:03.009944+00:00 → 2026-09-28T08:29:50.869381+00:00 (UTC). AWS profile: `china`; account: `209915754514`.

**Beijing and Ningxia: 2LO and 3LO pass end to end. Gateway account gating blocks OBO in both regions for this account; no end-to-end Gateway exchange was executed.**

**Provider scope: this run uses only a self-hosted synthetic OIDC/OAuth IdP connected through CustomOauth2. Microsoft Entra ID, Google, Okta, and other third-party IdPs were not used. Passing 2LO/3LO results apply to this test IdP; third-party compatibility and Microsoft OBO remain untested.**

| Check | Beijing cn-north-1 | Ningxia cn-northwest-1 |
| --- | --- | --- |
| IdP positive/negative and direct OBO baselines | PASS | PASS |
| 2LO / client_secret_basic | PASS | PASS |
| 2LO / client_secret_post | PASS | PASS |
| 3LO / initial consent required | PASS | PASS |
| 3LO / callback and user session binding | PASS | PASS |
| 3LO / repeat call by authorized user | PASS | PASS |
| 3LO / independent consent for another user | PASS | PASS |
| 3LO / resumed end-to-end invocation | PASS | PASS |
| OBO / RFC 8693 / NONE | BLOCKED | BLOCKED |
| OBO / RFC 8693 / M2M | BLOCKED | BLOCKED |
| OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | BLOCKED | BLOCKED |
| OBO / RFC 7523 / JWT Bearer | BLOCKED | BLOCKED |

Each region has 12 focused checks: 8 PASS, 4 BLOCKED, 0 FAIL. These include controls and flow substeps and are separate from the main report's 159-feature population.

## OAuth client and OBO configuration

An OAuth client was used: client_id=cn-retest with an independently generated random client_secret per region, configured in the OAuth Credential Provider's clientId/clientSecret fields. 2LO tests CLIENT_SECRET_BASIC and CLIENT_SECRET_POST; 3LO and all four OBO configurations use CLIENT_SECRET_BASIC. 2LO/3LO actually use the client to obtain outbound tokens. OBO client/provider configuration succeeds, but Gateway target creation is blocked. Secrets are omitted from reports and local secret files were removed after the run.

The OBO Gateway uses CUSTOM_JWT inbound authentication, allowing audience/client cn-retest and scope test. Target outbound authentication uses OAUTH, the provider ARN, scopes=["test"], and grantType=TOKEN_EXCHANGE. The provider's onBehalfOfTokenExchangeConfig selects RFC 8693 or RFC 7523. actorTokenContent=NONE means no actor token is attached; it does not mean Gateway No Authorization. The synthetic RFC 7523 configuration is not a Microsoft Entra ID integration.

## Observed flows

2LO uses separate CLIENT_SECRET_BASIC and CLIENT_SECRET_POST providers and OpenAPI MCP targets. The IdP observes grant_type=client_credentials, and the backend verifies the signature, issuer, audience, and expiry, returning authenticated=true and sub=synthetic-service. The backend token hash matches IdP issuance and differs from the inbound JWT. Both repeat calls succeed and each fetches a token again; this run does not demonstrate a 2LO cache hit.

3LO uses MCP 2026-07-28 and URL elicitation. A new user receives resultType=input_required. The synthetic IdP automatically approves the test identity; redirects traverse AgentCore, IdP, AgentCore callback, and application callback. CompleteResourceTokenAuth binds the same inbound user; inputResponses resumes the tool call with resultType=complete. The backend confirms grant=authorization_code. A repeat call succeeds without another token request. Another user still requires consent and does not reach the backend.

## OBO conclusion

All four provider configurations were created and read back in both regions. Each configuration was used in two Gateway target creation attempts, **16 attempts** in total, all returning:

```text
Service: bedrock-agentcore-control
Operation: CreateGatewayTarget
HTTP 403 / AccessDeniedException
Token Exchange is not available for this account
```

All Gateway targets use credentialProviderType=OAUTH and grantType=TOKEN_EXCHANGE. RFC 8693 providers use grantType=TOKEN_EXCHANGE with actor NONE, M2M, or AWS_IAM_ID_TOKEN_JWT. The RFC 7523 provider uses grantType=JWT_AUTHORIZATION_GRANT. Rejection occurs at target creation, with no Gateway-to-IdP token requests in any OBO test window.

Direct RFC 8693 and JWT Bearer exchanges against the synthetic IdP, followed by protected-backend calls, pass. These establish fixture readiness and do not count as Gateway OBO success. The finding applies to account 209915754514 in these regions at the test time, not every China-region account. AWS must confirm/enable Gateway Token Exchange for this account before end-to-end retesting. The AWS IAM actor mode has an additional outbound web identity federation prerequisite; this run did not change it.

## Request IDs and evidence index

| Region | Flow/configuration | Attempt | HTTP | Request ID | Audit line |
| --- | --- | ---: | ---: | --- | ---: |
| cn-north-1 | 2LO / client_secret_basic | 1 | 200 | `70955f85-7688-4d30-95c1-7372db18d1de` | [73](cn-north-1-api-audit.jsonl) |
| cn-north-1 | 2LO / client_secret_post | 1 | 200 | `d06678b4-4cc4-4675-856e-608a83470b6f` | [87](cn-north-1-api-audit.jsonl) |
| cn-north-1 | 3LO / resumed end-to-end invocation | 1 | 200 | `04ca536a-23d4-4a1f-81f6-95990ce47863` | [115](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 8693 / NONE | 1 | 403 | `27fd3686-9fc6-4ade-be15-07cb37943214` | [125](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 8693 / NONE | 2 | 403 | `45b09d18-fad9-4bd5-99bd-8c31034bc57a` | [127](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 8693 / M2M | 1 | 403 | `4d6ce174-2fcb-4840-b9c9-433a1089a28f` | [133](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 8693 / M2M | 2 | 403 | `6dc81385-69e1-4422-a3f1-8dc1cf93e7e0` | [135](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | 1 | 403 | `b36502ac-fcbb-44c4-ae1f-2ebd677d5e96` | [141](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | 2 | 403 | `b8b0fb65-e4e2-438e-8c6f-74fba8a12704` | [143](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 7523 / JWT Bearer | 1 | 403 | `30d2e597-19ed-4b66-b94c-15d5285f408d` | [149](cn-north-1-api-audit.jsonl) |
| cn-north-1 | OBO / RFC 7523 / JWT Bearer | 2 | 403 | `869f1a92-03f6-4655-b458-5f5a9fff2b68` | [151](cn-north-1-api-audit.jsonl) |
| cn-northwest-1 | 2LO / client_secret_basic | 1 | 200 | `7a3e2434-ec12-4e58-a932-b85144901263` | [73](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | 2LO / client_secret_post | 1 | 200 | `e9f75d1c-aa03-406b-bd2b-ad73fd50f8b9` | [87](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | 3LO / resumed end-to-end invocation | 1 | 200 | `557b36a3-1448-4ce7-80d3-643ba11a34a0` | [115](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / NONE | 1 | 403 | `1f36fbcb-750d-4e47-929c-3321b4def95f` | [125](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / NONE | 2 | 403 | `d8f36941-bb99-4d40-84a0-2a19cc607ab3` | [127](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / M2M | 1 | 403 | `12b0046c-ce6e-4f3c-a83d-1a672d2be4bc` | [133](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / M2M | 2 | 403 | `69a250f1-3234-462c-8777-587a996d9ce4` | [135](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | 1 | 403 | `01921ec5-e350-4be6-9a5c-720d0c40ab7a` | [141](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | 2 | 403 | `6a1e682a-8d10-486b-b434-0027ca465466` | [143](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 7523 / JWT Bearer | 1 | 403 | `739831b8-0ae5-4d11-b976-ca31593cc784` | [149](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 7523 / JWT Bearer | 2 | 403 | `66275633-c835-4a81-b3ab-158f8ebf129d` | [151](cn-northwest-1-api-audit.jsonl) |

## Reproduction

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-followup.lock.txt
# Install cloudflared as described in REPRODUCE.zh-CN.md.
.venv/bin/python run_oauth_validation.py --results-dir results/oauth-reproduction-new
.venv/bin/python export_oauth_validation.py --results-dir results/oauth-reproduction-new
```

Use a new empty directory. The runner tests both regions with profile china; --cloudflared /absolute/path overrides the binary location. Permissions are needed for test IAM roles, AgentCore Gateways/targets, OAuth providers, workload identities, and Secrets Manager cleanup verification. No Browser, EC2, Lambda, API Gateway, or S3 bucket creation is needed.

The one-command runner was executed from a fresh environment and completed cleanup. Exit 2 denotes explicit account gating; 0 denotes all passing and 1 denotes check, execution, or cleanup errors. The synthetic IdP and tunnel exist only during the run. Historical URLs, authorization codes, and resource state cannot be reused. The detailed exporter validates this passing-2LO/3LO, blocked-OBO baseline. If outcomes change, it refuses to overwrite the interpretation; retain and analyze the runner's new report.

## Records and cleanup

- [console.log](console.log) · [phase-commands.jsonl](phase-commands.jsonl) · [environment.json](environment.json)
- [summary.json](summary.json) · [request-index.csv](request-index.csv) · [validation.json](validation.json)
- [source-snapshots](source-snapshots/) · [artifacts.json](artifacts.json) · [redaction-report.json](redaction-report.json)

Regional *-results.jsonl files hold verdicts, *-api-audit.jsonl files hold requests/responses, and *-issuer-events.jsonl files hold issuance/usage evidence.

- cn-north-1: cleanup verification PASS. Gateway, 3 targets, 7 OAuth providers, workload identity, and IAM role are absent. Local processes are stopped and key/secret files removed. 5 service-managed secrets had deletion markers at verification, awaiting AWS asynchronous deletion.
- cn-northwest-1: cleanup verification PASS. Gateway, 3 targets, 7 OAuth providers, workload identity, and IAM role are absent. Local processes are stopped and key/secret files removed. 5 service-managed secrets had deletion markers at verification, awaiting AWS asynchronous deletion.

This run validates functionality with a synthetic CustomOauth2 provider. No third-party IdP, including Microsoft Entra ID, Google, or Okta, was used. Long-duration refresh-token behavior, concurrency, and MFA were not tested. Actual M2M/AWS IAM actor exchange behavior remains unexecuted behind the Gateway target account gate.

## Official documentation

- [Gateway outbound authorization](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html)
- [On-behalf-of token exchange](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)
- [OAuthCredentialProvider](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_OAuthCredentialProvider.html)
- [OnBehalfOfTokenExchangeConfigType](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_OnBehalfOfTokenExchangeConfigType.html)

Retrieved documentation and metadata are retained under documentation/. Documentation defines the modes; the service calls above establish observed availability.
