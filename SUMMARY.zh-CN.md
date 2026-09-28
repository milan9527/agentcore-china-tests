# AgentCore Gateway 与 Browser 中国区测试总结

> 本文已合并初测与后续补测结果，与[英文完整报告](REPORT.md)采用相同统计口径。初测版本单独保留在 [SUMMARY.initial.zh-CN.md](SUMMARY.initial.zh-CN.md)。**Live View 两地画面和输入均通过，原失败结论已更正。**

测试日期：2026 年 9 月 28 日（UTC）  
AWS Profile：`china`  
AWS 账号：`209915754514`  
测试区域：北京 `cn-north-1`、宁夏 `cn-northwest-1`

## 总体结果

两个区域的最终检查结果一致。有效 JWT、OAuth client credentials、OAuth authorization code、JWT 透传，以及正确配置下的 Browser 代理均通过；Live View 显示和人工输入也已通过。仍失败的是调用者 IAM 转发和 Playwright `download.save_as()` 取回文件；下载已有文本与二进制验证通过的替代方法。

| 区域 | 检查项数 | 通过 | 失败 | 前提条件不足 | 部分验证 | 当前不可用 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 北京 `cn-north-1` | 159 | 153 | 2 | 2 | 0 | 2 |
| 宁夏 `cn-northwest-1` | 159 | 153 | 2 | 2 | 0 | 2 |

统计保持每区初测的 **159 个检查名称**，使用对应检查的最新补测结果更新状态。新增排查检查单独列在[补测矩阵](results/followup-matrix.csv)，不扩大主表分母。初测每区为 145 通过、6 失败、5 受限、1 部分验证、2 当前不可用；随后 8 项转为通过：JWT、三项 OAuth / 透传、三项代理及 Live View。

检查包含功能调用、配置验证及诊断对照，不包含环境准备、阶段汇总、资源清理和中国区已知不支持能力的负向检查。一个产品功能可能对应多个检查项，因此 **159 项不代表 159 个独立功能**。代理通过仅适用于明确验证的配置，8000/8443 端口等失败记录仍保留。

本次属于 API 与浏览器集成测试，未覆盖所有配置组合、协议变体、控制台流程、性能指标或配额边界，不能视为全部功能均已通过。

## 主要通过的能力

### Gateway

| 类别 | 已验证内容 |
| --- | --- |
| 生命周期与管理 | 创建、查询、列表、更新、标签；目标分页、幂等创建、更新后调用 |
| 入站 IAM 鉴权 | SigV4 签名调用成功，未签名请求被拒绝 |
| JWT 与 OAuth | 有效 RS256 JWT 实际调用 Lambda，错误 audience/client/scope 及过期令牌被拒绝；client credentials、authorization code 完成受保护后端调用；JWT 透传哈希一致 |
| Lambda 目标 | 内联与 S3 工具定义；计算、Unicode 回显及目标错误响应 |
| OpenAPI / API Gateway | 内联与 S3 定义；实际后端调用、IAM 鉴权、请求头转发、REST 阶段筛选及工具覆盖配置 |
| Smithy | 导入定义并实际调用 Lambda `GetFunctionConcurrency` |
| MCP 服务目标 | DEFAULT / DYNAMIC 发现、同步及定义刷新；工具、提示词、资源和资源模板 |
| MCP 协议与会话 | `2025-03-26`、`2025-06-18`、`2025-11-25`、`2026-07-28`；初始化握手及服务发现 |
| 流式与交互 | SSE 结果、进度和日志通知；表单 elicitation、授权码 URL elicitation 回调与会话绑定；sampling 请求与恢复调用 |
| 拦截器 | 请求拦截器修改工具参数，响应拦截器添加标记，均验证实际效果 |
| 加密与出站鉴权 | 自定义 KMS 密钥及实际工具调用；API Key 经后端验证；自定义 OAuth 提供商配置成功 |
| HTTP / Runtime | HTTP 转发；使用 Gateway IAM 执行角色调用 Runtime |
| 限流与可观测性 | 限流规则增删改查、零速率返回 429；CloudWatch 日志与指标、CloudTrail 事件 |

Elicitation 已测试 MCP `2026-07-28` 的表单模式及实际授权码 URL 流程；sampling 使用合成客户端响应，未调用真实大模型。鉴权补测使用临时合成 HTTPS OIDC/OAuth 服务，测试后已关闭。Token Exchange 虽可配置提供商，但目标创建受账号开关限制。

### Browser

| 类别 | 已验证内容 |
| --- | --- |
| 生命周期 | 托管与自定义 Browser、标签、分页、会话幂等、视口与超时配置、停止会话 |
| CDP 自动化 | HTTPS 导航、DOM 提取、表单、点击、中文及 Unicode 输入、多标签页、截图、文件上传 |
| 远端下载与取回替代方法 | 文件在远端内容正确；通过 CDP 文件输入接口与 `File.arrayBuffer()` 取回 21 字节文本和 8192 字节二进制，逐字节及 SHA-256 验证一致 |
| OS 操作 | 全部八种操作：鼠标移动、点击、拖动、滚动、键入、按键、快捷键、截图；输入效果经 DOM 验证 |
| 状态与隔离 | Cookie / localStorage；配置文件保存恢复；并发会话隔离；禁用自动化后连接被拒绝，恢复后可重连 |
| 扩展与企业策略 | 扩展实际执行；托管 URL 黑名单生效；推荐策略在 Chrome 策略页面可见 |
| 录制与回放 | S3 收到真实 gzip NDJSON 录制批次及完整快照；本地 rrweb 回放重建测试页面，北京 330 个事件、宁夏 467 个事件 |
| 私有网络与存储 | VPC 私有 HTTP 访问；默认拒绝私有 CA、配置根证书后 HTTPS 成功；EFS 文件跨会话持久化 |
| 外部代理 | Basic 鉴权与无鉴权均通过 HTTP 80、HTTPS CONNECT 443；显式域名路由和独立绕过验证通过 |
| Live View | 官方组件显示画面并支持鼠标、键盘输入；每区首次连接观察 5 分钟，新签名重连同一会话再观察 5 分钟 |
| 超时与可观测性 | 60 秒 TTL 自动终止；CloudWatch 使用日志与指标、CloudTrail 事件 |

## Live View 更正：显示与人工输入均通过

原测试条件为 `probe.firstFrame || probe.errors.length > 0`，约 2 秒收到鉴权 WebSocket 关闭错误就退出。实际鉴权已经成功，显示连接尚在建立，不能据此判为显示连接失败。保留默认 300 秒签名有效期、取消错误回调触发的提前退出后，两地均收到首帧：

| 区域 | 首次首帧 | 新签名重连首帧 | 持续观察 | 人工输入 |
| --- | ---: | ---: | --- | --- |
| 北京 | 6.450 秒 | 6.718 秒 | 首次及重连后各至少 300 秒 | 通过 |
| 宁夏 | 6.728 秒 | 7.514 秒 | 首次及重连后各至少 300 秒 | 通过 |

每次观察期间接收字节持续增加，远端时钟持续变化。Live View 展示完整浏览器窗口，输入测试还需计入顶部工具栏高度，本次为 87 像素；修正后，通过 Live View 键入 `dcv-official-input-ok`，远端 DOM 验证一致。WebSocket 消息计数包含协议消息，不等同于视频帧数；本次不作为长期稳定性或负载认证。

**原“DCV 显示连接失败”的判断是测试过早结束造成的误判。** 鉴权关闭错误仍保留，内部原因未确认，但实测没有阻止显示和输入。常规测试现在最多等待首帧 120 秒。[详细更正、截图与复现命令](LIVEVIEW.zh-CN.md)。

## 仍未通过的两项功能检查

调用者 IAM 转发于 2026-09-28 07:53 UTC 在两地新环境再次复现；每区 5 项成功对照、3 项调用者转发失败，本次新增资源清理通过。[复现过程与结果](results/repro-caller-confirm-20260928/REPORT.zh-CN.md)。

| 问题 | 现象 | 对照与结论范围 |
| --- | --- | --- |
| Gateway 调用者 IAM 凭证转发 | `CALLER_IAM_CREDENTIALS` 目标创建成功，调用返回 403：`The security token included in the request is invalid` | 长期凭证、STS GetSessionToken、AssumeRole 均复现；AssumeRole 对照覆盖 AWS_IAM 与 AUTHENTICATE_ONLY 入站。相同凭证直接调用 Runtime、使用 Gateway 执行角色调用成功。功能失败明确，服务内部根因未确认 |
| Playwright 下载到本地 | `download.save_as()` 在 Playwright 1.63.0 和 1.60.0 下均保存 0 字节，预期为 21 字节 | 文件在远端存在且内容正确，客户端对应路径不存在；本地 Chromium 对照成功。失败位于该 CDP 连接方式的远端文件取回环节；[替代助手](download_remote_file.py)已通过文本及二进制校验，未测试大文件性能 |

客户端环境：Playwright `1.63.0`，兼容性对照 `1.60.0`；本地 Chromium `153.0.8010.12`，远端 Chromium `148.0.7778.258`。初测使用 DCV Web SDK `1.14.1+build.0`，后续使用官方 `bedrock-agentcore` TypeScript SDK `0.4.4` 的 BrowserLiveView 组件及随包客户端。

代理配置边界仍需保留：HTTP 8000 / HTTPS 8443 在内置代理路径下失败；上游专用域名未配置 `externalProxy.domainPatterns` 时返回 DNS 503。`server` 使用裸主机名/IP；路由与绕过规则分开验证，避免反向 DNS 同时匹配。配置示例及服务端日志见[详细补测报告](FOLLOWUP.zh-CN.md)。

## 未完成验证的前提条件

| 能力 | 当前结果 | 后续需要 |
| --- | --- | --- |
| OAuth Token Exchange | 提供商配置成功，创建目标明确返回 `Token Exchange is not available for this account` | AWS 为账号启用该功能；可用合成 IdP 已补齐 |
| Gateway 私有目标 | API 明确要求账号开通 VPC egress 功能 | 账号开通后，补测私有目标实际调用 |
| Gateway / Browser PrivateLink | 两地当前账号的 EC2 端点服务目录均未公布 AgentCore 服务 | 服务可见后补测私有入口；Browser 的 VPC 出站访问已经通过 |

上述限制仅适用于测试时的账号及区域。CUSTOM_JWT、client credentials、authorization code、JWT 透传已完成实际验证，不再列为缺少测试前提。

## 中国区文档明确不支持的能力

根据 [AWS 中国区服务差异文档](https://docs.amazonaws.cn/en_us/aws/latest/userguide/bedrock-agentcore.html)，以下能力未计为受支持功能的测试失败：

- Gateway：语义搜索、Cognito 鉴权、NONE 入站鉴权、推理目标、控制台连接器目录、WAF 集成、Gateway rules、ConfigBundle A/B 测试。
- Browser：Web Bot Auth、S3 Files 挂载。
- Identity：私有身份提供商，以及文档列出的部分内置 OAuth 提供商。

NONE 入站鉴权和语义搜索在两地均实际验证为拒绝创建；其他排除项依据文档，未逐项执行负向测试。EFS 挂载已通过，与不支持的 S3 Files 挂载不同。

中国区概览只列出 AWS_IAM / CUSTOM_JWT 入站模式，但本次两地实际接受 AUTHENTICATE_ONLY Gateway，且该模式下执行角色出站调用通过；报告保留这一文档与实测差异。

## 资源清理

以下为已记录的清理状态快照，非重新进行云端检查的结果：

- 已保存的独立检查确认：测试 Gateway、Browser、Runtime、Lambda、API Gateway、EFS、S3 存储桶、自建 Secrets Manager 密钥及 IAM 角色已删除；EC2 实例已终止，无残留测试 EBS 卷。后续 Live View 三个测试目录在两地的会话清理及核验均通过。
- 两把 KMS 密钥已进入 `PendingDeletion`，计划于 **2026 年 10 月 5 日约 05:27 UTC** 删除，符合 AWS 最短七天等待期。
- 初测与补测共四个安全组仍受 AgentCore 网络接口依赖：北京 `sg-00ea1d13ed36ba5d3`、`sg-03179feaec145cf84`；宁夏 `sg-074039951f97aedee`、`sg-0e9e501fda1882754`。
- AWS 文档说明相关网络接口可能在资源删除后保留最多八小时。本地清理任务的最新保存状态为等待接口释放，在最长 8.5 小时内重试安全组删除；依赖工作区进程持续运行。
- 本地生成的测试私钥、测试秘密文件已删除，导出证据中的凭证参数已脱敏，`china` profile 未修改。

清理尚未全部完成，最新保存进展见[所有运行的清理状态](results/followup-cleanup.json)、[初测清理任务](results/deferred-cleanup.json)及[补测清理任务](results/retest/deferred-cleanup.json)。

## 报告与证据

- [英文完整报告与逐项矩阵](REPORT.md)
- [CSV 功能检查矩阵](results/feature-matrix.csv)
- [最终结果与证据 JSON](results/final-results.json)
- [初测历史报告](SUMMARY.initial.zh-CN.md)、[初测统计与证据](results/initial-results.json)
- [全部检查时间线](results/followup-history.jsonl)、[补测矩阵](results/followup-matrix.csv)
- [复现步骤](REPRODUCE.zh-CN.md)、[完整排查过程](WORKLOG.zh-CN.md)
- [北京原始检查记录](results/cn-north-1-results.jsonl) / [宁夏原始检查记录](results/cn-northwest-1-results.jsonl)
- [北京 Browser 录制回放](results/cn-north-1-replay.html) / [宁夏 Browser 录制回放](results/cn-northwest-1-replay.html)
- [环境及脚本说明](README.md)

逐请求审计和阶段源码快照在补测过程中增加，早期缺失的原始请求未追溯补写；审计不等同于完整 CDP/DCV 网络抓包。各阶段已实测，一键完整云端编排尚未从空环境再次执行。历史失败保留，最终结论按已验证配置和对应证据更新。
