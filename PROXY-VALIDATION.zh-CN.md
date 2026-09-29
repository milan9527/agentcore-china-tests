# Browser 代理再次验证结论

2026-09-28 使用 `china` profile，在北京、宁夏创建独立环境，代理与目标服务分处两个无公网地址的 EC2。每区执行 **95 项检查：60 PASS、35 FAIL**；35 个失败各重复一次且结果一致，两区合计 **260 次请求观察**。这些是场景检查，不是 35 个独立服务缺陷，也不与主报告的 159 项统计相加。

**HTTP 8000/8081 的拒绝已确认由 Browser 托管 Squid 返回；本轮自建外部代理与目标服务均未收到这些失败请求。具体服务内部 ACL 仍未取得，不能断言是某条 `Safe_ports` 配置错误。**

| 验证路径 | HTTP 80 | HTTP 8000/8081 | HTTPS 443 | HTTPS 8443 |
| --- | --- | --- | --- | --- |
| 不配置外部代理的直连对照 | 通过 | 通过 | 通过 | 通过 |
| Playwright 新上下文直接指定外部代理 | 通过 | 通过 | 通过 | 通过 |
| AgentCore `proxyConfiguration` 托管代理 | 通过 | Squid 403，未到外部代理 | 通过 | CONNECT 失败，未到外部代理 |
| 托管代理中配置 bypass | 通过，目标来源为 Browser | Squid 403 | 通过，目标来源为 Browser | CONNECT 失败 |

以上两区一致。托管代理覆盖监听端口 **3128 / 8080（Basic）与 3129（无认证）**，各自包含默认路由及显式域名路由。目标端口与代理监听端口是不同参数：代理监听 `8080` 能访问目标 `80/443`，并不意味着目标 `8081` 可用。

绕过覆盖精确 IP、完整主机名、`.compute.internal` 后缀；另测错误代理凭证下的 IP 绕过，以及同一 IP 同时命中路由与绕过。标准端口均绕过成功，非标准端口仍失败。因此不能把 bypass 的作用理解为绕过 Browser 托管路径的所有访问控制。

其他专项结果：

- **仅外部代理可识别的域名**：默认路由下 HTTP 80 返回 DNS 503、HTTPS 443 CONNECT 失败，均未到外部代理；加入 `externalProxy.domainPatterns` 后 HTTP/HTTPS 均通过。
- **错误及缺失凭证**：标准 HTTP/HTTPS 均被拒绝，外部代理日志确认认证未通过，目标没有收到请求。此时请求到达了外部代理，与端口拒绝的路径不同。
- **多代理选择**：指定域名使用 3128、其余目标使用默认 3129，HTTP/HTTPS 均由对应监听端口实际处理。
- **TLS 对照**：不安装测试根 CA 时被拒绝，安装 CA 后通过；正常测试没有关闭证书校验。

HTTP 端口拒绝的实际响应头：

```text
HTTP 403
server: squid/6.13
via: 1.1 localhost (squid/6.13)
x-squid-error: ERR_ACCESS_DENIED 0
```

只读访问 `/etc/squid/squid.conf` 返回 `ERR_ACCESS_DENIED`。未修改服务配置，也没有读取/保存原始 Squid 配置。HTTPS 的浏览器错误没有揭示具体 ACL；结合端口对照和两端日志，只能定位到外部代理之前的托管路径。

可用配置与操作建议：

1. 在本次验证范围内使用目标 HTTP 80 / HTTPS 443。
2. 上游专用域名显式放入 `externalProxy.domainPatterns`。
3. `server` 填裸 IP/主机名，代理端口单独填写；凭证使用 Secrets Manager 的 `{"username": "...", "password": "..."}`。
4. 需要非标准目标端口时，可参考本轮通过的 Playwright 上下文代理方式，但它是另一种客户端配置路径，不能视为托管 `proxyConfiguration` 已修复。生产使用前需核对网络控制要求。
5. 如必须使用托管路径访问非标准端口，应向 AWS 提供该账号/区域、Browser sessionId、唯一 marker、错误头及“两端无访问记录”的对照，确认服务访问策略和支持范围。

复现：

```bash
.venv/bin/python run_proxy_validation.py --results-dir results/proxy-reproduction-new
.venv/bin/python export_proxy_validation.py --results-dir results/proxy-reproduction-new
```

使用新的空目录；运行器创建资源并在最后清理。每次请求的 marker、sessionId、响应头、错误、来源 IP、服务端日志序号均保留。

- [完整中文矩阵、证据索引和清理状态](results/proxy-validation-20260928-r2/REPORT.zh-CN.md)
- [English report](results/proxy-validation-20260928-r2/REPORT.md)
- [完整控制台输出](results/proxy-validation-20260928-r2/console.log)
- [实际命令](results/proxy-validation-20260928-r2/phase-commands.jsonl)
- [260 次请求明细](results/proxy-validation-20260928-r2/attempts.csv)
- [结构化结果](results/proxy-validation-20260928-r2/final-results.json)

参考的 [9 月 23 日报告](https://github.com/milan9527/aws-agentcore-china-tests/blob/main/COMBINED_TEST_REPORT_ZH.md)来自另一个账号，使用目标 8081/8443 和代理 8080；本轮补齐这些组合、标准端口和独立外部代理对照，不覆盖原报告结果。首次环境准备因默认子网自动分配公网地址而停止并清理，记录保留于 `results/proxy-validation-20260928/`；第二轮显式关闭 ENI 公网地址分配后执行上述功能测试。

清理状态（2026-09-28 10:16 UTC 核验）：40 个 Browser 会话已终止，两个 Browser 资源、四台 EC2、四个自建 ENI 和两个 IAM 角色已清理，六个 Secret 已请求删除。北京安全组 `sg-0cb10af93ab6c0181`、宁夏安全组 `sg-02b620b4720173ddf` 仍等待 AWS 托管 ENI 释放，整体清理尚未完成。后台清理进程 PID `2433055` 正在重试，最长运行至 18:43 UTC；没有强制分离 AWS 托管 ENI。最新状态见 [deferred-cleanup.json](results/proxy-validation-20260928-r2/deferred-cleanup.json)。
