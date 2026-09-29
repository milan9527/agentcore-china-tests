# Gateway 出站 OAuth：2LO / 3LO / OBO 验证报告

2026-09-28T08:27:03.009944+00:00 → 2026-09-28T08:29:50.869381+00:00 (UTC). AWS profile: `china`; account: `209915754514`.

**北京、宁夏：2LO 和 3LO 端到端通过。OBO 在当前账号两区均被 Gateway 服务的账号限制阻断，尚未执行端到端交换。**

**提供商范围：本次仅使用自建合成 OIDC/OAuth IdP，通过 `CustomOauth2` 接入 AgentCore。未接入 Microsoft Entra ID、Google、Okta 或其他第三方 IdP。2LO/3LO 通过仅说明与该测试 IdP 的流程通过；第三方兼容性及 Microsoft OBO 均未验证。**

| 检查 | 北京 cn-north-1 | 宁夏 cn-northwest-1 |
| --- | --- | --- |
| IdP 正反例与直接 OBO 对照 | PASS | PASS |
| 2LO / client_secret_basic | PASS | PASS |
| 2LO / client_secret_post | PASS | PASS |
| 3LO / 首次调用要求用户授权 | PASS | PASS |
| 3LO / 回调与用户会话绑定 | PASS | PASS |
| 3LO / 同用户再次调用 | PASS | PASS |
| 3LO / 另一用户需独立授权 | PASS | PASS |
| 3LO / 恢复调用并到达后端 | PASS | PASS |
| OBO / RFC 8693 / NONE | BLOCKED | BLOCKED |
| OBO / RFC 8693 / M2M | BLOCKED | BLOCKED |
| OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | BLOCKED | BLOCKED |
| OBO / RFC 7523 / JWT Bearer | BLOCKED | BLOCKED |

每区 12 个专项检查：8 PASS、4 BLOCKED、0 FAIL。该计数包括对照及流程子步骤，不与主报告的 159 项功能集合相加。

## OAuth client 与 OBO 配置

本次使用了 OAuth client：`client_id=cn-retest`，`client_secret` 为每区独立随机生成的测试密钥，配置在 OAuth Credential Provider 的 `clientId` / `clientSecret` 中。2LO 分别使用 `CLIENT_SECRET_BASIC` 和 `CLIENT_SECRET_POST`；3LO 与四种 OBO 配置使用 `CLIENT_SECRET_BASIC`。2LO/3LO 已实际使用该客户端获取出站令牌；OBO 仅完成客户端和提供商配置，随后在创建 Gateway 目标时受阻。密钥未写入报告，测试结束已清理本地密钥文件。

OBO 的 Gateway 入站认证为 `CUSTOM_JWT`，允许的 audience/client 为 `cn-retest`、scope 为 `test`。目标的出站认证为 `OAUTH`，引用提供商 ARN，设置 `scopes=["test"]`、`grantType=TOKEN_EXCHANGE`。提供商的 `onBehalfOfTokenExchangeConfig` 决定 RFC 8693 或 RFC 7523 模式。`actorTokenContent=NONE` 只表示不附带 actor token，与 Gateway 的 No Authorization 无关。RFC 7523 合成测试配置不等于接入 Microsoft Entra ID。

## 实际调用过程

2LO 分别配置 `CLIENT_SECRET_BASIC` 与 `CLIENT_SECRET_POST`，创建 OpenAPI MCP 目标后通过 Gateway 调用。IdP 记录 `grant_type=client_credentials`；后端验证签名、issuer、audience 和有效期，返回 `authenticated=true`、`sub=synthetic-service`。后端令牌哈希与 IdP 签发记录一致，且不同于入站 JWT。两种模式再次调用均通过，并各自再次请求了令牌端点；本次不宣称 2LO 缓存命中。

3LO 使用 MCP `2026-07-28` 和 URL elicitation：新用户调用得到 `resultType=input_required`；合成 IdP 自动批准测试身份的授权；跟随 AgentCore → IdP → AgentCore callback → 应用 callback 的重定向；调用 `CompleteResourceTokenAuth` 绑定同一用户，再通过 `inputResponses` 恢复调用，得到 `resultType=complete`。后端确认 `grant=authorization_code`。同用户再次调用成功且没有新的令牌请求；另一用户仍须授权，未到达后端。

## OBO 的明确结论

四种提供商配置在两区均创建成功并回读确认。每种配置创建 Gateway 目标两次，共 **16 次**，均返回：

```text
Service: bedrock-agentcore-control
Operation: CreateGatewayTarget
HTTP 403 / AccessDeniedException
Token Exchange is not available for this account
```

所有 Gateway 目标都使用 `credentialProviderType=OAUTH`、`grantType=TOKEN_EXCHANGE`。RFC 8693 的 provider `grantType=TOKEN_EXCHANGE`，actor 分别为 `NONE`、`M2M`、`AWS_IAM_ID_TOKEN_JWT`；RFC 7523 的 provider `grantType=JWT_AUTHORIZATION_GRANT`。拒绝发生在目标创建阶段，各 OBO 测试窗口没有 Gateway 发往 IdP 的令牌请求。

直接访问合成 IdP 的 RFC 8693 与 JWT Bearer 交换及受保护后端均通过，排除了基本测试令牌和提供商不可用的前提问题。这些直接对照不代表 Gateway OBO 通过。结论仅适用于账号 `209915754514` 在测试时的两区状态，不能扩大为所有中国区账号不支持。下一步需要 AWS 确认/开放该账号的 Gateway Token Exchange 后再运行；AWS IAM actor 模式另有出站 Web Identity Federation 的账号前提，本次未更改。

## 请求 ID 与证据索引

| 区域 | 调用/配置 | 尝试 | HTTP | 请求 ID | 审计行 |
| --- | --- | ---: | ---: | --- | ---: |
| cn-north-1 | 2LO / client_secret_basic | 1 | 200 | `70955f85-7688-4d30-95c1-7372db18d1de` | [73](cn-north-1-api-audit.jsonl) |
| cn-north-1 | 2LO / client_secret_post | 1 | 200 | `d06678b4-4cc4-4675-856e-608a83470b6f` | [87](cn-north-1-api-audit.jsonl) |
| cn-north-1 | 3LO / 恢复调用并到达后端 | 1 | 200 | `04ca536a-23d4-4a1f-81f6-95990ce47863` | [115](cn-north-1-api-audit.jsonl) |
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
| cn-northwest-1 | 3LO / 恢复调用并到达后端 | 1 | 200 | `557b36a3-1448-4ce7-80d3-643ba11a34a0` | [115](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / NONE | 1 | 403 | `1f36fbcb-750d-4e47-929c-3321b4def95f` | [125](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / NONE | 2 | 403 | `d8f36941-bb99-4d40-84a0-2a19cc607ab3` | [127](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / M2M | 1 | 403 | `12b0046c-ce6e-4f3c-a83d-1a672d2be4bc` | [133](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / M2M | 2 | 403 | `69a250f1-3234-462c-8777-587a996d9ce4` | [135](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | 1 | 403 | `01921ec5-e350-4be6-9a5c-720d0c40ab7a` | [141](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT | 2 | 403 | `6a1e682a-8d10-486b-b434-0027ca465466` | [143](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 7523 / JWT Bearer | 1 | 403 | `739831b8-0ae5-4d11-b976-ca31593cc784` | [149](cn-northwest-1-api-audit.jsonl) |
| cn-northwest-1 | OBO / RFC 7523 / JWT Bearer | 2 | 403 | `66275633-c835-4a81-b3ab-158f8ebf129d` | [151](cn-northwest-1-api-audit.jsonl) |

## 复现命令

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-followup.lock.txt
# Install cloudflared as described in REPRODUCE.zh-CN.md.
.venv/bin/python run_oauth_validation.py --results-dir results/oauth-reproduction-new
.venv/bin/python export_oauth_validation.py --results-dir results/oauth-reproduction-new
```

必须使用新的空目录。默认使用 `china` profile 同时测试两区；`--cloudflared /absolute/path` 可覆盖二进制位置。需要创建/删除测试 IAM 角色、AgentCore Gateway/目标、OAuth provider、workload identity，以及回查 Secrets Manager 的权限。不需要创建 Browser、EC2、Lambda、API Gateway 或 S3 桶。

本次一键运行已实际从零执行并完成清理，退出码 `2` 表示存在明确账号阻断；`0` 为全部通过，`1` 为检查、执行或清理异常。合成 IdP 和隧道只在运行期间存在；历史资源已清理，不能重用旧 URL、授权码或状态文件。详细导出器核验本次 2LO/3LO 通过、OBO 受限的基线；未来结果改变时会拒绝覆盖解释，请保留运行器生成的新报告并重新分析。

## 完整记录与清理

- [console.log](console.log) · [phase-commands.jsonl](phase-commands.jsonl) · [environment.json](environment.json)
- [summary.json](summary.json) · [request-index.csv](request-index.csv) · [validation.json](validation.json)
- [source-snapshots](source-snapshots/) · [artifacts.json](artifacts.json) · [redaction-report.json](redaction-report.json)

各区域 `*-results.jsonl` 保存逐项判定；`*-api-audit.jsonl` 保存请求/响应；`*-issuer-events.jsonl` 保存签发和使用证据。

- cn-north-1：清理核验 PASS。Gateway、3 个目标、7 个 OAuth provider、workload identity 和 IAM 角色均查无资源；本地进程已停、私钥/密钥文件已删除。5 个服务托管 Secret 在回查时有删除标记，等待 AWS 异步删除。
- cn-northwest-1：清理核验 PASS。Gateway、3 个目标、7 个 OAuth provider、workload identity 和 IAM 角色均查无资源；本地进程已停、私钥/密钥文件已删除。5 个服务托管 Secret 在回查时有删除标记，等待 AWS 异步删除。

本次范围是合成 CustomOauth2 提供商的功能验证，没有接入 Microsoft Entra ID、Google、Okta 等任何第三方 IdP，也未测试长时间刷新令牌、并发负载或 MFA。M2M/AWS IAM actor 的真正交换行为仍因 Gateway 目标账号门槛而未执行。

## 官方文档

- [Gateway outbound authorization](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html)
- [On-behalf-of token exchange](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)
- [OAuthCredentialProvider](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_OAuthCredentialProvider.html)
- [OnBehalfOfTokenExchangeConfigType](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_OnBehalfOfTokenExchangeConfigType.html)

本次读取的文档副本和检索元数据保存在 `documentation/`；文档定义模式，实际可用性以上述服务调用为准。
