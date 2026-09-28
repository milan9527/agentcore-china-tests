> 初测历史版本，归档于合并补测结果之前。当前结论见 [SUMMARY.zh-CN.md](SUMMARY.zh-CN.md)。

# AgentCore Gateway 与 Browser 中国区测试总结

> 本文保留初测总结。后续补测已更新鉴权、代理和下载等项目的结论，见[中文版补测报告](FOLLOWUP.zh-CN.md)及[复现说明](REPRODUCE.zh-CN.md)。**Live View 延长观察后，两地画面和输入均通过；原失败为测试提前结束造成的误判，见[更正报告](LIVEVIEW.zh-CN.md)。**

测试日期：2026 年 9 月 28 日（UTC）  
AWS Profile：`china`  
AWS 账号：`209915754514`  
测试区域：北京 `cn-north-1`、宁夏 `cn-northwest-1`

## 总体结果

两个区域的初测检查结果一致，大部分已测试能力可正常使用。初测结束时记录了四类未解决问题，部分鉴权与私有网络功能因前提条件不足而未完成端到端验证；后续更正见本文开头链接。

| 区域 | 检查项数 | 通过 | 失败 | 前提条件不足 | 部分验证 | 当前不可用 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 北京 `cn-north-1` | 159 | 145 | 6 | 5 | 1 | 2 |
| 宁夏 `cn-northwest-1` | 159 | 145 | 6 | 5 | 1 | 2 |

统计采用每个区域、每个检查项的最后一次结果，包含功能调用、配置验证及诊断对照测试；不包含环境准备、阶段汇总、资源清理和中国区已知不支持能力的负向检查。一个产品功能可能对应多个检查项，因此 **159 项不代表 159 个独立功能**。

本次属于 API 与浏览器集成测试，未覆盖所有配置组合、协议变体、控制台流程、性能指标或配额边界，不能视为全部功能均已通过。

## 主要通过的能力

### Gateway

| 类别 | 已验证内容 |
| --- | --- |
| 生命周期与管理 | 创建、查询、列表、更新、标签；目标分页、幂等创建、更新后调用 |
| 入站 IAM 鉴权 | SigV4 签名调用成功，未签名请求被拒绝 |
| Lambda 目标 | 内联与 S3 工具定义；计算、Unicode 回显及目标错误响应 |
| OpenAPI / API Gateway | 内联与 S3 定义；实际后端调用、IAM 鉴权、请求头转发、REST 阶段筛选及工具覆盖配置 |
| Smithy | 导入定义并实际调用 Lambda `GetFunctionConcurrency` |
| MCP 服务目标 | DEFAULT / DYNAMIC 发现、同步及定义刷新；工具、提示词、资源和资源模板 |
| MCP 协议与会话 | `2025-03-26`、`2025-06-18`、`2025-11-25`、`2026-07-28`；初始化握手及服务发现 |
| 流式与交互 | SSE 结果、进度和日志通知；表单 elicitation、sampling 请求与恢复调用 |
| 拦截器 | 请求拦截器修改工具参数，响应拦截器添加标记，均验证实际效果 |
| 加密与出站鉴权 | 自定义 KMS 密钥及实际工具调用；API Key 经后端验证；自定义 OAuth 提供商配置成功 |
| HTTP / Runtime | HTTP 转发；使用 Gateway IAM 执行角色调用 Runtime |
| 限流与可观测性 | 限流规则增删改查、零速率返回 429；CloudWatch 日志与指标、CloudTrail 事件 |

Elicitation 测试采用 MCP `2026-07-28` 的表单模式；sampling 使用合成客户端响应，未调用真实大模型。OAuth 提供商配置成功不代表 OAuth 端到端流程通过。

### Browser

| 类别 | 已验证内容 |
| --- | --- |
| 生命周期 | 托管与自定义 Browser、标签、分页、会话幂等、视口与超时配置、停止会话 |
| CDP 自动化 | HTTPS 导航、DOM 提取、表单、点击、中文及 Unicode 输入、多标签页、截图、文件上传 |
| 远端下载 | 文件下载到远端浏览器后，内容验证正确 |
| OS 操作 | 全部八种操作：鼠标移动、点击、拖动、滚动、键入、按键、快捷键、截图；输入效果经 DOM 验证 |
| 状态与隔离 | Cookie / localStorage；配置文件保存恢复；并发会话隔离；禁用自动化后连接被拒绝，恢复后可重连 |
| 扩展与企业策略 | 扩展实际执行；托管 URL 黑名单生效；推荐策略在 Chrome 策略页面可见 |
| 录制与回放 | S3 收到真实 gzip NDJSON 录制批次及完整快照；本地 rrweb 回放重建测试页面，北京 330 个事件、宁夏 467 个事件 |
| 私有网络与存储 | VPC 私有 HTTP 访问；默认拒绝私有 CA、配置根证书后 HTTPS 成功；EFS 文件跨会话持久化 |
| 超时与可观测性 | 60 秒 TTL 自动终止；CloudWatch 使用日志与指标、CloudTrail 事件 |

## 未解决的问题

六项失败集中在以下四类，两地均复现。

| 问题 | 现象 | 对照与结论范围 |
| --- | --- | --- |
| Gateway 调用者 IAM 凭证转发 | `CALLER_IAM_CREDENTIALS` 目标创建成功，调用返回 403：`The security token included in the request is invalid` | 长期凭证与 STS 临时凭证均复现；相同 STS 凭证直接调用同一 Runtime、通过 Gateway 执行角色目标调用均成功。需进一步排查中国分区的 HTTP Runtime 目标凭证转发 |
| Browser 代理配置（3 项） | HTTPS CONNECT 报 `ERR_TUNNEL_CONNECTION_FAILED`；绕过规则请求返回 Squid 403；代理专用 HTTP 域名返回 DNS 503 | 直接在新 Playwright 上下文配置同一私有代理及凭证后，HTTP 对照请求成功。结论仅限本次 VPC 代理配置；该对照未独立证明 HTTPS 隧道及绕过规则正常 |
| Playwright 下载到本地 | `download.save_as()` 保存结果为 0 字节，预期为 21 字节 | 远端文件内容为 `agentcore-download-ok`，已实际读取验证。远端下载通过，本地文件取回失败 |
| DCV 实时画面 | 预签名鉴权成功，但首帧前连接失败：`Failed to communicate with server`；WebSocket 报 `Close received after close` | 实时画面与人工输入未验证。CDP 和 InvokeBrowser 输入独立通过；根因尚未确定，不能直接认定为 AWS 服务缺陷 |

客户端环境：Playwright `1.63.0`、本地 Chromium `153.0.8010.12`、远端 Chromium `148.0.7778.258`、DCV Web SDK `1.14.1+build.0`。客户端兼容性仍是下载取回与 DCV 问题的可能影响因素。

## 未完成验证的前提条件

| 能力 | 当前结果 | 后续需要 |
| --- | --- | --- |
| CUSTOM_JWT 入站鉴权 | 部分验证：公共 Microsoft OIDC 发现配置、无效令牌拒绝均通过 | 可用测试身份或签名凭证，以验证有效 JWT 调用 |
| OAuth client credentials、authorization code、token exchange、JWT passthrough | 四项端到端流程未执行；提供商配置通过 | 可用测试 OAuth / OIDC 提供商及令牌；本次 API Gateway 测试后端要求 AWS_IAM，无法承担所需的公开 OIDC / Bearer 接口 |
| Gateway 私有目标 | API 明确要求账号开通 VPC egress 功能 | 账号开通后，补测私有目标实际调用 |
| Gateway / Browser PrivateLink | 两地当前账号的 EC2 端点服务目录均未公布 AgentCore 服务 | 服务可见后补测私有入口；Browser 的 VPC 出站访问已经通过 |

## 中国区文档明确不支持的能力

根据 [AWS 中国区服务差异文档](https://docs.amazonaws.cn/en_us/aws/latest/userguide/bedrock-agentcore.html)，以下能力未计为受支持功能的测试失败：

- Gateway：语义搜索、Cognito 鉴权、NONE 入站鉴权、推理目标、控制台连接器目录、WAF 集成、Gateway rules、ConfigBundle A/B 测试。
- Browser：Web Bot Auth、S3 Files 挂载。
- Identity：私有身份提供商，以及文档列出的部分内置 OAuth 提供商。

NONE 入站鉴权和语义搜索在两地均实际验证为拒绝创建；其他排除项依据文档，未逐项执行负向测试。EFS 挂载已通过，与不支持的 S3 Files 挂载不同。

## 资源清理

以下为已记录的清理状态快照，非重新进行云端检查的结果：

- 2026 年 9 月 28 日约 **05:28 UTC** 的独立检查确认：测试 Gateway、Browser、Runtime、Lambda、API Gateway、EFS、S3 存储桶、Secrets Manager 密钥及 IAM 角色已删除；EC2 实例已终止，无残留测试 EBS 卷。
- 两把 KMS 密钥已进入 `PendingDeletion`，计划于 **2026 年 10 月 5 日约 05:27 UTC** 删除，符合 AWS 最短七天等待期。
- 两个测试安全组仍受 AgentCore 网络接口依赖：北京 `sg-00ea1d13ed36ba5d3`，宁夏 `sg-074039951f97aedee`。
- AWS 文档说明相关网络接口可能在资源删除后保留最多八小时。本地清理任务在 **05:33 UTC** 的状态为等待接口释放，将在最长 8.5 小时内重试安全组删除；依赖工作区进程持续运行。
- 本地生成的测试私钥、测试秘密文件已删除，导出证据中的凭证参数已脱敏，`china` profile 未修改。

清理尚未全部完成，最新进展见[清理任务状态](results/deferred-cleanup.json)及[完整报告](REPORT.md)。

## 报告与证据

- [英文完整报告与逐项矩阵](REPORT.md)
- [CSV 功能检查矩阵](results/initial-feature-matrix.csv)
- [最终结果与证据 JSON](results/initial-results.json)
- [北京原始检查记录](results/cn-north-1-results.jsonl) / [宁夏原始检查记录](results/cn-northwest-1-results.jsonl)
- [北京 Browser 录制回放](results/cn-north-1-replay.html) / [宁夏 Browser 录制回放](results/cn-northwest-1-replay.html)
- [环境及脚本说明](README.md)
