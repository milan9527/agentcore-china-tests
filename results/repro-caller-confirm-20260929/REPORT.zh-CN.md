# Gateway 调用者 IAM 凭证转发复测

2026-09-29T01:54:05.091080+00:00 — 2026-09-29T02:00:23.356468+00:00; AWS profile: `china`.

使用全新 Runtime、Gateway 和 IAM 角色，复用上一轮调用逻辑。两种目标配置分别为 `GATEWAY_IAM_ROLE`、`CALLER_IAM_CREDENTIALS`，均指向同一 HTTP Runtime。请求使用当前区域、`bedrock-agentcore` 服务名做 SigV4 签名。

| Region | Verdict | Checks | Cleanup |
| --- | --- | --- | --- |
| cn-north-1 | NOT_REPRODUCED | {'PASS': 8} | PASS |
| cn-northwest-1 | NOT_REPRODUCED | {'PASS': 8} | PASS |

**结论：本次两区原问题的全部对照通过，调用者 IAM 转发不再返回原无效令牌 403；在所测三种凭证/入站组合中已恢复。** 具体服务内部修复与部署时间未经确认。

## 判定范围

`REPRODUCED`：5 项直接调用/执行角色对照通过，3 项调用者转发仍报原无效令牌错误，本次未观察到修复。`NOT_REPRODUCED`：8 项对照均通过，仅说明本次所测路径未再复现。`INCONCLUSIVE`：对照不完整或错误变化，需要进一步分析。

同一组 AssumeRole 凭证用于直接调用及两种入站模式；另一组 GetSessionToken 凭证用于直接调用、执行角色出站和调用者出站。成功要求返回 `sum=42`。

## 响应与请求 ID

| Region | Check | Result | HTTP | Response | Request ID | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| cn-north-1 | AssumeRole → Runtime 直接调用 | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `d628f645-56d0-4ef0-9159-e644a1186e0a` | [L10](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AWS_IAM → Gateway 执行角色 | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `4d984797-a892-4cb2-90fb-e3945407faf3, 23ec9ab7-4b96-4384-ac77-fb0cdaf7752f` | [L12](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AWS_IAM → 调用者 IAM | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `88ac57c7-1286-4b9f-b838-1516fd3d95cf, 1704a9f1-b3f8-46dc-ad40-f5a6f296646b` | [L13](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AUTHENTICATE_ONLY → Gateway 执行角色 | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `92924dd4-0ab0-4baf-b65a-1920f5ea4366, 40fc27fd-3996-4123-b63b-51b2d295c553` | [L15](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AUTHENTICATE_ONLY → 调用者 IAM | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `4c207c1a-f2ec-485e-9e05-f9c2244b2a74, 03e3ac11-f1ff-443e-99b4-dee083cb93c8` | [L16](cn-north-1-results.jsonl) |
| cn-north-1 | GetSessionToken → Runtime 直接调用 | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `3fd531eb-9e73-492c-a386-b4b20ab06329` | [L18](cn-north-1-results.jsonl) |
| cn-north-1 | GetSessionToken → Gateway 执行角色 | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `07cb373c-900c-4abb-9615-7b8e0ea16ccc, a1a76938-80d9-4f60-be91-d8dbdb98f0ca` | [L19](cn-north-1-results.jsonl) |
| cn-north-1 | GetSessionToken → 调用者 IAM | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-north-1\"}"` | `f98e5c28-3a15-4c0a-9d78-798bcdc8c5fc, 30b54a95-6b76-4594-b169-7d472b908459` | [L20](cn-north-1-results.jsonl) |
| cn-northwest-1 | AssumeRole → Runtime 直接调用 | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `4300278d-a4cc-4809-9fa6-49be26de557b` | [L10](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AWS_IAM → Gateway 执行角色 | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `6d827326-e167-42ee-ade8-7dc9002d450b, 7585b12e-9ac7-456b-aec0-a4a803cf5dbb` | [L12](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AWS_IAM → 调用者 IAM | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `1546de4c-610d-4ec5-ac94-e4fc31e547fe, 507fa5f8-6ca5-4048-bc04-c69acb958cb8` | [L13](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AUTHENTICATE_ONLY → Gateway 执行角色 | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `dec65a18-6b3b-486a-89ed-dff759ffce1d, 1a77d580-85f9-4f9f-b847-5df94a2e29a2` | [L15](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AUTHENTICATE_ONLY → 调用者 IAM | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `cec25052-57c5-4193-b4b1-f6e77db56194, 9776c02b-398b-4c43-90d9-25860fe327b0` | [L16](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | GetSessionToken → Runtime 直接调用 | PASS | SDK | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `ea005686-bfdd-417d-b2e8-8a68e5efe7ee` | [L18](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | GetSessionToken → Gateway 执行角色 | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `3704bbc0-6ba1-4813-8b6d-7db364827f7f, 6d020096-afc6-4219-ab00-5f81ec47509a` | [L19](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | GetSessionToken → 调用者 IAM | PASS | 200 | `"{\"sum\": 42, \"runtime\": \"gateway-fixture\", \"region\": \"cn-northwest-1\"}"` | `5449c32d-d063-436c-9a60-1843f6c6bd14, 678c5bef-2907-4bb0-a9ba-fdfa897ea2b6` | [L20](cn-northwest-1-results.jsonl) |

## 复现与记录

```bash
.venv/bin/python run_caller_reproduction.py --results-dir results/repro-caller-new
.venv/bin/python export_caller_reproduction.py --results-dir results/repro-caller-new
```

必须使用新的空目录。运行器退出码：2=原问题复现，0=所选对照通过，1=执行/判定/清理异常。导出器只读取本地证据，不调用 AWS。

- [Console](console.log) · [Commands](phase-commands.jsonl) · [Summary](summary.json)
- [Invocation JSON](invocation-results.json) · [CSV](invocation-results.csv)
- [Runtime/Gateway/target configurations](configurations.json) · [Environment](environment.json)
- [Validation](validation.json) · [Artifact hashes](artifacts.json)

表格使用每个指定检查的最后一条原始记录，前期 Runtime 冒烟调用和失败均保留在日志。独立临时凭证 SDK 客户端未注册框架审计，直接调用的响应和请求 ID 来自检查结果；不补造未记录的 HTTP 状态码。12 条 Gateway HTTP 响应有原始 HTTP 审计关联（如检查未完成，以 validation.json 的实际计数为准）。

复用的 setup 还会执行公开 OIDC 探测，其失败不属于 IAM 转发检查；此次不启动外部 IdP。清理仅针对本次目录创建的资源。历史结果未改写。
