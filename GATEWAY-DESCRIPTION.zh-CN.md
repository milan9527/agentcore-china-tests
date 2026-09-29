# AgentCore Gateway 中国区介绍文案核对

核对日期：2026-09-28；实测范围为 `china` profile 的北京 `cn-north-1`、宁夏 `cn-northwest-1`。原描述前半部分基本准确，后半部分不宜作为中国区全部已验证的能力承诺。

建议使用：

> AgentCore Gateway 将受支持的 API、Lambda 函数和 MCP Server 接入统一的安全工具端点，供 Agent 发现和调用，并提供身份认证、访问控制和请求限流，帮助管理工具访问与调用成本。

以下表述需要区分文档定义与本次中国区实测范围：

| 表述 | 核对结果 |
| --- | --- |
| 将 API、Lambda 和 MCP Server 统一接入，供 Agent 发现和调用 | 本次已验证对应受支持目标的工具发现及调用；不能扩大为任意 API 自动兼容。 |
| 每个用户的请求限额 | 官方模型允许以 JWT 声明（例如 `$.context.jwt.sub`）或 IAM principal 为限流维度。本次两区实测验证的是 `targetName` 维度请求限流和 HTTP 429，未逐用户验证。 |
| 令牌限额 | 文档的 `tokens` 面向推理目标的令牌速率控制；本次未完成中国区推理目标的令牌限流验证，不能作为已验证能力表述。 |
| 连接时长限额 | 术语有误：限流 API 中 `connections` 表示并发连接数，而不是连接时长。本次也未验证中国区并发连接限额的实际执行，不能仅更换术语后就列为实测通过。 |
| MCP 会话超时 | 独立的 `sessionConfiguration.sessionTimeoutInSeconds` 配置，不能与按用户的连接时长配额混为一谈。 |

“令牌”在这里指模型推理消耗的 token，不是 OAuth 访问令牌；请求速率限制也不等同于月度预算或费用硬上限。按用户隔离需要配置可识别该用户的维度，例如已验证 JWT 的 `sub`；多个用户共用同一个 IAM principal 时，仅按该 principal 限流不能区分这些用户。

两区 `gateway.rate_limits` 实测创建、列出、更新、删除限流规则，并将 `targetName` 维度请求速率设为零，实际调用返回 HTTP 429、`Rate limit exceeded`。这证明了该配置的请求限流执行，未覆盖逐用户隔离、非零速率精度、推理 token 计量或并发连接限额。

依据：

- [官方限流说明](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/gateway-rate-limits.html)
- [官方限流维度](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/gateway-rate-limits-dimensions.html)
- [官方 token 与连接限额示例](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/gateway-rate-limits-examples.html)
- boto3/botocore 1.43.103 的 AgentCore 控制面模型
- [本项目中国区实测报告](REPORT.md)、[北京原始结果](results/cn-north-1-results.jsonl)、[宁夏原始结果](results/cn-northwest-1-results.jsonl)中的 `gateway.rate_limits` 检查

此文为文档/已有证据核对，未新增限流云端测试。中国区文档中的能力定义与本账号两区的实际可用性分开记录；未验证不等于不支持。
