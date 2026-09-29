# Gateway caller-IAM forwarding retest

2026-09-29T01:54:05.091080+00:00 — 2026-09-29T02:00:23.356468+00:00; AWS profile: `china`.

Fresh Runtime, Gateway and IAM roles use the previous invocation logic. GATEWAY_IAM_ROLE and CALLER_IAM_CREDENTIALS targets point to the same HTTP Runtime. Requests use SigV4 with bedrock-agentcore and the current region.

| Region | Verdict | Checks | Cleanup |
| --- | --- | --- | --- |
| cn-north-1 | NOT_REPRODUCED | {'PASS': 8} | PASS |
| cn-northwest-1 | NOT_REPRODUCED | {'PASS': 8} | PASS |

**All original comparison checks pass in both regions. Caller-IAM forwarding no longer returns the invalid-token 403 in the three tested credential/inbound combinations.** The internal fix and deployment time have not been established.

## Interpretation

REPRODUCED: all five direct/role controls pass and all three caller paths retain the invalid-token error; no fix observed in this run. NOT_REPRODUCED: all eight checks pass, limited to the tested paths. INCONCLUSIVE: incomplete controls or a changed error.

The same AssumeRole credentials are used for direct invocation and both inbound modes. A separate GetSessionToken set is shared by its three comparison paths. Success requires sum=42.

## Responses and request IDs

| Region | Check | Result | HTTP | Response | Request ID | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| cn-north-1 | gateway.caller_iam.assumed_role.direct | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `d628f645-56d0-4ef0-9159-e644a1186e0a` | [L10](cn-north-1-results.jsonl) |
| cn-north-1 | gateway.caller_iam.AWS_IAM.runtime-role | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `4d984797-a892-4cb2-90fb-e3945407faf3, 23ec9ab7-4b96-4384-ac77-fb0cdaf7752f` | [L12](cn-north-1-results.jsonl) |
| cn-north-1 | gateway.caller_iam.AWS_IAM.runtime-caller | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `88ac57c7-1286-4b9f-b838-1516fd3d95cf, 1704a9f1-b3f8-46dc-ad40-f5a6f296646b` | [L13](cn-north-1-results.jsonl) |
| cn-north-1 | gateway.caller_iam.AUTHENTICATE_ONLY.runtime-role | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `92924dd4-0ab0-4baf-b65a-1920f5ea4366, 40fc27fd-3996-4123-b63b-51b2d295c553` | [L15](cn-north-1-results.jsonl) |
| cn-north-1 | gateway.caller_iam.AUTHENTICATE_ONLY.runtime-caller | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `4c207c1a-f2ec-485e-9e05-f9c2244b2a74, 03e3ac11-f1ff-443e-99b4-dee083cb93c8` | [L16](cn-north-1-results.jsonl) |
| cn-north-1 | gateway.outbound.caller_iam.direct_runtime_baseline | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `3fd531eb-9e73-492c-a386-b4b20ab06329` | [L18](cn-north-1-results.jsonl) |
| cn-north-1 | gateway.outbound.caller_iam.gateway_role_baseline | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `07cb373c-900c-4abb-9615-7b8e0ea16ccc, a1a76938-80d9-4f60-be91-d8dbdb98f0ca` | [L19](cn-north-1-results.jsonl) |
| cn-north-1 | gateway.outbound.caller_iam | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `f98e5c28-3a15-4c0a-9d78-798bcdc8c5fc, 30b54a95-6b76-4594-b169-7d472b908459` | [L20](cn-north-1-results.jsonl) |
| cn-northwest-1 | gateway.caller_iam.assumed_role.direct | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `4300278d-a4cc-4809-9fa6-49be26de557b` | [L10](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | gateway.caller_iam.AWS_IAM.runtime-role | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `6d827326-e167-42ee-ade8-7dc9002d450b, 7585b12e-9ac7-456b-aec0-a4a803cf5dbb` | [L12](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | gateway.caller_iam.AWS_IAM.runtime-caller | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `1546de4c-610d-4ec5-ac94-e4fc31e547fe, 507fa5f8-6ca5-4048-bc04-c69acb958cb8` | [L13](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | gateway.caller_iam.AUTHENTICATE_ONLY.runtime-role | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `dec65a18-6b3b-486a-89ed-dff759ffce1d, 1a77d580-85f9-4f9f-b847-5df94a2e29a2` | [L15](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | gateway.caller_iam.AUTHENTICATE_ONLY.runtime-caller | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `cec25052-57c5-4193-b4b1-f6e77db56194, 9776c02b-398b-4c43-90d9-25860fe327b0` | [L16](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | gateway.outbound.caller_iam.direct_runtime_baseline | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `ea005686-bfdd-417d-b2e8-8a68e5efe7ee` | [L18](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | gateway.outbound.caller_iam.gateway_role_baseline | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `3704bbc0-6ba1-4813-8b6d-7db364827f7f, 6d020096-afc6-4219-ab00-5f81ec47509a` | [L19](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | gateway.outbound.caller_iam | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `5449c32d-d063-436c-9a60-1843f6c6bd14, 678c5bef-2907-4bb0-a9ba-fdfa897ea2b6` | [L20](cn-northwest-1-results.jsonl) |

## Reproduction and evidence

```bash
.venv/bin/python run_caller_reproduction.py --results-dir results/repro-caller-new
.venv/bin/python export_caller_reproduction.py --results-dir results/repro-caller-new
```

Use a new empty directory. Runner exits: 2=original issue reproduced, 0=selected checks pass, 1=execution/verdict/cleanup issue. The exporter is offline.

- [Console](console.log) · [Commands](phase-commands.jsonl) · [Summary](summary.json)
- [Invocation JSON](invocation-results.json) · [CSV](invocation-results.csv)
- [Runtime/Gateway/target configurations](configurations.json) · [Environment](environment.json)
- [Validation](validation.json) · [Artifact hashes](artifacts.json)

The table selects the latest original row per specified check; initial Runtime smoke calls and failures remain in the logs. Separate temporary-credential SDK clients do not register the framework audit; their responses and request IDs come from check results. Unrecorded HTTP status codes are not inferred. Gateway HTTP responses are cross-referenced to audit rows; see validation.json for actual counts.

Shared setup also probes public OIDC; those failures are outside the IAM comparison. No external IdP is started. Cleanup targets this run's inventory; historical evidence is preserved.
