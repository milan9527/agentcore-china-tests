# Gateway 调用者 IAM 转发再次复现

开始：2026-09-28T07:48:38.273408+00:00；结束：2026-09-28T07:54:37.756108+00:00；profile：`china`。

| 区域 | 结论 | 成功对照 | 清理核验 |
| --- | --- | --- |
| cn-north-1 | REPRODUCED | True | PASS |
| cn-northwest-1 | REPRODUCED | True | PASS |

## 逐项结果

| 区域 | 调用路径 | 结果 | 证据 |
| --- | --- | --- | --- |
| cn-north-1 | AssumeRole → Runtime 直接调用 | PASS | [结果第 10 行](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AWS_IAM → Gateway 执行角色 | PASS | [结果第 12 行](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AWS_IAM → 调用者 IAM | FAIL | [结果第 13 行](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AUTHENTICATE_ONLY → Gateway 执行角色 | PASS | [结果第 15 行](cn-north-1-results.jsonl) |
| cn-north-1 | AssumeRole / AUTHENTICATE_ONLY → 调用者 IAM | FAIL | [结果第 16 行](cn-north-1-results.jsonl) |
| cn-north-1 | GetSessionToken → Runtime 直接调用 | PASS | [结果第 18 行](cn-north-1-results.jsonl) |
| cn-north-1 | GetSessionToken → Gateway 执行角色 | PASS | [结果第 19 行](cn-north-1-results.jsonl) |
| cn-north-1 | GetSessionToken → 调用者 IAM | FAIL | [结果第 20 行](cn-north-1-results.jsonl) |
| cn-northwest-1 | AssumeRole → Runtime 直接调用 | PASS | [结果第 10 行](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AWS_IAM → Gateway 执行角色 | PASS | [结果第 12 行](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AWS_IAM → 调用者 IAM | FAIL | [结果第 13 行](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AUTHENTICATE_ONLY → Gateway 执行角色 | PASS | [结果第 15 行](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | AssumeRole / AUTHENTICATE_ONLY → 调用者 IAM | FAIL | [结果第 16 行](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | GetSessionToken → Runtime 直接调用 | PASS | [结果第 18 行](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | GetSessionToken → Gateway 执行角色 | PASS | [结果第 19 行](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | GetSessionToken → 调用者 IAM | FAIL | [结果第 20 行](cn-northwest-1-results.jsonl) |

## 运行记录

- [完整控制台输出](console.log)：阶段开始、等待状态、逐项结果与脱敏后的完整证据。
- [命令记录](phase-commands.jsonl)：实际命令、时间、环境参数和进程退出码。
- [结构化结论](summary.json)：调用结果、响应、请求 ID、源文件及行号、清理核验。
- 各区域 `*-api-audit.jsonl` 和 `source-snapshots/` 保留框架请求审计及执行时源码。

调用者路径失败且相同凭证直接调用和执行角色对照均通过，才判定为本次无效令牌问题复现。其他错误或前提未就绪判为 INCONCLUSIVE；失败不直接证明 AWS 内部根因。

setup 中公开 OIDC 403 探测与本次 IAM 调用无关；此次没有启动外部 IdP 隧道。

## 调用响应与请求 ID

| 区域 | 调用路径 | HTTP / SDK 结果 | 响应 | 请求 ID |
| --- | --- | --- | --- | --- |
| cn-north-1 | AssumeRole → Runtime 直接调用 | SDK 调用成功 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `fc2cdf2a-b94e-4b28-a92e-f19cca436009` |
| cn-north-1 | AssumeRole / AWS_IAM → Gateway 执行角色 | 200 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `e9d13319-d067-45d0-b1ce-97ce811b3a6d, ece3ba84-d4fa-4606-ba06-d7b32591bc45` |
| cn-north-1 | AssumeRole / AWS_IAM → 调用者 IAM | 403 | `{"message":"The security token included in the request is invalid"}` | `a4fc4263-eebc-45eb-a110-ac09e6f4696b, b5a76bf2-31cf-40c9-8a4e-b8b30caa58c0` |
| cn-north-1 | AssumeRole / AUTHENTICATE_ONLY → Gateway 执行角色 | 200 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `fd334d81-704a-4f19-8fa1-11eb5b291d39, 22306f7c-6dc8-48d6-ad7a-2f698dbf1680` |
| cn-north-1 | AssumeRole / AUTHENTICATE_ONLY → 调用者 IAM | 403 | `{"message":"The security token included in the request is invalid"}` | `5b04360f-d2d3-40a2-8af0-679ef472dc66, eb685b08-2672-43b6-b3c6-c1142bd930e5` |
| cn-north-1 | GetSessionToken → Runtime 直接调用 | SDK 调用成功 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `e568e71c-ee90-46bb-8e71-d22c6cb61daa` |
| cn-north-1 | GetSessionToken → Gateway 执行角色 | 200 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-north-1"}` | `736ff975-0a73-4552-b656-1d4d4fb23d1e, 30defd95-75be-485e-b777-5c1b6991aee7` |
| cn-north-1 | GetSessionToken → 调用者 IAM | 403 | `{"message":"The security token included in the request is invalid"}` | `a67d4b40-641d-4e3a-9a50-f5a4247f7a27, fbde43c4-b440-4eab-97a6-8b5a028755ce` |
| cn-northwest-1 | AssumeRole → Runtime 直接调用 | SDK 调用成功 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `5d1c19e0-799a-464e-9a0f-0a5c9c23c5f1` |
| cn-northwest-1 | AssumeRole / AWS_IAM → Gateway 执行角色 | 200 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `be1a84cf-d5ba-45e7-a388-446f7e90cce4, d88595d2-c9e1-43d0-9c93-c9cda37b8277` |
| cn-northwest-1 | AssumeRole / AWS_IAM → 调用者 IAM | 403 | `{"message":"The security token included in the request is invalid"}` | `111ed982-323f-48c4-9172-261d603fa4f9, 8a7e6d72-0771-493d-b84f-ff8856c2c206` |
| cn-northwest-1 | AssumeRole / AUTHENTICATE_ONLY → Gateway 执行角色 | 200 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `ccfddd44-16d2-424e-8b95-09b7c8d4ff10, 713feaeb-a150-4181-8f5f-0880990fa2ab` |
| cn-northwest-1 | AssumeRole / AUTHENTICATE_ONLY → 调用者 IAM | 403 | `{"message":"The security token included in the request is invalid"}` | `28c41132-876a-4f4f-844b-4f5112f1300a, 84e24964-33be-4035-bcaf-39e876100eb9` |
| cn-northwest-1 | GetSessionToken → Runtime 直接调用 | SDK 调用成功 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `b30312d0-c93a-4272-8284-7d9afbdb6bfc` |
| cn-northwest-1 | GetSessionToken → Gateway 执行角色 | 200 | `{"sum": 42, "runtime": "gateway-fixture", "region": "cn-northwest-1"}` | `d1acd12d-5f61-4265-8019-41da5467d119, bb0ac42e-944a-47d2-9975-9387f4565b21` |
| cn-northwest-1 | GetSessionToken → 调用者 IAM | 403 | `{"message":"The security token included in the request is invalid"}` | `13c4ba9f-3242-421a-8eb3-b643992373ab, 0deb0fb1-c183-499e-a962-87aa101782d3` |

直接 SDK 调用记录保留了成功响应及请求 ID，未单独记录 HTTP 状态码，表中不补造 HTTP 数值。

完整机器可读表格：[JSON](invocation-results.json)、[CSV](invocation-results.csv)。

## 再次执行

在仓库目录使用一个新的空结果目录：

```bash
.venv/bin/python run_caller_reproduction.py --results-dir results/repro-caller-next
```

该编排已于本次从空目录在两地执行完成，包括资源创建、功能对照与清理。退出码 2 表示问题被复现；退出码 1 表示流程、判定或清理存在异常，退出码 0 表示所选对照全部通过。它与覆盖全部功能的 `run_followup.py` 是两个不同编排。
