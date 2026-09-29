# Browser 代理专项验证：端口、认证、路由与绕过

使用 AWS profile `china`，账号 `209915754514`，分别在北京与宁夏实测。本报告从保存的逐项观察及两端日志生成，不调用 AWS。

**本轮将请求路径分为：Browser → 托管 Squid → 自建外部代理 → 独立目标服务。测试端口矩阵并用服务端日志确认路径；不能将外部代理监听端口与目标服务端口混为一谈。**

## 环境与断言

每区使用两个无公网地址的 EC2：独立的目标服务和 Python 外部代理，处于同一测试安全组。目标监听 HTTP 80/8000/8081 和 HTTPS 443/8443；代理监听 3128/8080（Basic）和 3129（无认证）。HTTP 请求实际转发到目标，HTTPS 通过 CONNECT 隧道。证书包含目标 IP 和测试主机名，正常 TLS 测试不忽略证书错误。

每次请求携带唯一 `/probe/<marker>` 路径，关联 Browser 结果与目标日志；目标看到代理 IP 才计为经代理到达。代理成功同时要求相应监听端口的认证/CONNECT 记录。绕过成功要求目标记录来源不是代理 IP，且对应窗口没有外部代理请求。错误/缺失凭证检查要求目标未收到请求，且外部代理记录认证拒绝。失败请求在相同配置下重复一次，历史结果保留。

| 区域 | 目标 IP | 代理 IP | 唯一检查 | 尝试数 | 最后结果 |
| --- | --- | --- | ---: | ---: | --- |
| cn-north-1 | 172.31.39.252 | 172.31.32.245 | 95 | 130 | {"PASS": 60, "FAIL": 35} |
| cn-northwest-1 | 172.31.14.177 | 172.31.14.103 | 95 | 130 | {"PASS": 60, "FAIL": 35} |

### 按路径汇总

| Region | Group | Latest verdicts |
| --- | --- | --- |
| cn-north-1 | direct | {"PASS": 10} |
| cn-north-1 | playwrightExternalProxy | {"PASS": 15} |
| cn-north-1 | managedExternalProxy | {"PASS": 12, "FAIL": 18} |
| cn-north-1 | bypass | {"PASS": 10, "FAIL": 15} |
| cn-north-1 | proxyOnlyDns | {"FAIL": 2, "PASS": 2} |
| cn-north-1 | multiProxy | {"PASS": 4} |
| cn-northwest-1 | direct | {"PASS": 10} |
| cn-northwest-1 | playwrightExternalProxy | {"PASS": 15} |
| cn-northwest-1 | managedExternalProxy | {"PASS": 12, "FAIL": 18} |
| cn-northwest-1 | bypass | {"PASS": 10, "FAIL": 15} |
| cn-northwest-1 | proxyOnlyDns | {"FAIL": 2, "PASS": 2} |
| cn-northwest-1 | multiProxy | {"PASS": 4} |

## 逐项矩阵

单元格为北京 / 宁夏；`—` 表示该场景没有安排此端口。PASS 指该行断言通过，认证拒绝/证书拒绝对照的 PASS 表示预期拒绝发生。

| Scenario | HTTP 80 | HTTP 8000 | HTTP 8081 | HTTPS 443 | HTTPS 8443 |
| --- | --- | --- | --- | --- | --- |
| direct-baseline | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| playwright-proxy-3128 | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| playwright-proxy-8080 | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| playwright-proxy-3129 | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| managed-3128-default | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-3128-explicit | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-8080-default | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-8080-explicit | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-3129-default | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-3129-explicit | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-ip | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-hostname | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-suffix | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-ip-bad-credentials | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-and-route-ip | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| hostname-route | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| proxy-only-dns-default | FAIL / FAIL | — / — | — / — | FAIL / FAIL | — / — |
| proxy-only-dns-explicit | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| bad-credentials | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| missing-credentials | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| multi-specific | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| multi-fallback | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| untrusted-control | — / — | — / — | — / — | PASS / PASS | — / — |
| direct-final-control | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |

`direct-*`：无外部代理；`playwright-proxy-*`：新 Playwright 上下文直接指定外部代理；`managed-*`：StartBrowserSession 的 proxyConfiguration；`explicit`：显式域名规则；`bypass-*`：精确 IP/主机名/后缀绕过；`multi-*`：指定域名代理与默认代理选择。

## 未通过请求的定位

| 区域 | 场景 | URL | 结果 | 外部代理收到 | 目标收到 | 结果行 |
| --- | --- | --- | --- | --- | --- | --- |
| cn-north-1 | managed-3128-default | `http://172.31.39.252:8000` | 403 | False | False | [30](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-default | `http://172.31.39.252:8081` | 403 | False | False | [32](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-default | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/26dc705312d44388acf | False | False | [35](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-explicit | `http://172.31.39.252:8000` | 403 | False | False | [40](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-explicit | `http://172.31.39.252:8081` | 403 | False | False | [42](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-explicit | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/a983d1eb7ba241c2bac | False | False | [45](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-default | `http://172.31.39.252:8000` | 403 | False | False | [50](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-default | `http://172.31.39.252:8081` | 403 | False | False | [52](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-default | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/8b29cd34ea6d4183914 | False | False | [55](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-explicit | `http://172.31.39.252:8000` | 403 | False | False | [60](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-explicit | `http://172.31.39.252:8081` | 403 | False | False | [62](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-explicit | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/bb8eda8f079c48ba841 | False | False | [65](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-default | `http://172.31.39.252:8000` | 403 | False | False | [70](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-default | `http://172.31.39.252:8081` | 403 | False | False | [72](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-default | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/133adc1727cb4a5e95b | False | False | [75](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-explicit | `http://172.31.39.252:8000` | 403 | False | False | [80](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-explicit | `http://172.31.39.252:8081` | 403 | False | False | [82](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-explicit | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/4435bb73c7b14b1faff | False | False | [85](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip | `http://172.31.39.252:8000` | 403 | False | False | [90](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip | `http://172.31.39.252:8081` | 403 | False | False | [92](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/b18b66efc21240ed956 | False | False | [95](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-hostname | `http://ip-172-31-39-252.cn-north-1.compute.internal:8000` | 403 | False | False | [100](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-hostname | `http://ip-172-31-39-252.cn-north-1.compute.internal:8081` | 403 | False | False | [102](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-hostname | `https://ip-172-31-39-252.cn-north-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-39-252.cn-north-1.compute.internal | False | False | [105](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-suffix | `http://ip-172-31-39-252.cn-north-1.compute.internal:8000` | 403 | False | False | [110](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-suffix | `http://ip-172-31-39-252.cn-north-1.compute.internal:8081` | 403 | False | False | [112](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-suffix | `https://ip-172-31-39-252.cn-north-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-39-252.cn-north-1.compute.internal | False | False | [115](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip-bad-credentials | `http://172.31.39.252:8000` | 403 | False | False | [120](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip-bad-credentials | `http://172.31.39.252:8081` | 403 | False | False | [122](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip-bad-credentials | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/323183c2ef154576ac7 | False | False | [125](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-and-route-ip | `http://172.31.39.252:8000` | 403 | False | False | [130](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-and-route-ip | `http://172.31.39.252:8081` | 403 | False | False | [132](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-and-route-ip | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/08a7f20008084277944 | False | False | [135](cn-north-1-results.jsonl) |
| cn-north-1 | proxy-only-dns-default | `http://proxy-only.agentcore.test:80` | 503 | False | False | [143](cn-north-1-results.jsonl) |
| cn-north-1 | proxy-only-dns-default | `https://proxy-only.agentcore.test:443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://proxy-only.agentcore.test/probe/cbe7c142b5f8 | False | False | [145](cn-north-1-results.jsonl) |
| cn-northwest-1 | managed-3128-default | `http://172.31.14.177:8000` | 403 | False | False | [30](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-default | `http://172.31.14.177:8081` | 403 | False | False | [32](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-default | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/459775a07cd44443b3d | False | False | [35](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-explicit | `http://172.31.14.177:8000` | 403 | False | False | [40](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-explicit | `http://172.31.14.177:8081` | 403 | False | False | [42](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-explicit | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/acdcffb74e864d41bec | False | False | [45](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-default | `http://172.31.14.177:8000` | 403 | False | False | [50](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-default | `http://172.31.14.177:8081` | 403 | False | False | [52](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-default | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/11808e94ed8244f8a6e | False | False | [55](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-explicit | `http://172.31.14.177:8000` | 403 | False | False | [60](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-explicit | `http://172.31.14.177:8081` | 403 | False | False | [62](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-explicit | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/637a8aff33684e55ab0 | False | False | [65](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-default | `http://172.31.14.177:8000` | 403 | False | False | [70](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-default | `http://172.31.14.177:8081` | 403 | False | False | [72](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-default | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/618cc2d4c8c74ee880f | False | False | [75](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-explicit | `http://172.31.14.177:8000` | 403 | False | False | [80](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-explicit | `http://172.31.14.177:8081` | 403 | False | False | [82](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-explicit | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/b7d2a2840a664c32b9e | False | False | [85](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip | `http://172.31.14.177:8000` | 403 | False | False | [90](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip | `http://172.31.14.177:8081` | 403 | False | False | [92](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/35519e1fcf1c476ebdf | False | False | [95](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-hostname | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8000` | 403 | False | False | [100](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-hostname | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8081` | 403 | False | False | [102](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-hostname | `https://ip-172-31-14-177.cn-northwest-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-14-177.cn-northwest-1.compute.inte | False | False | [105](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-suffix | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8000` | 403 | False | False | [110](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-suffix | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8081` | 403 | False | False | [112](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-suffix | `https://ip-172-31-14-177.cn-northwest-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-14-177.cn-northwest-1.compute.inte | False | False | [115](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip-bad-credentials | `http://172.31.14.177:8000` | 403 | False | False | [120](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip-bad-credentials | `http://172.31.14.177:8081` | 403 | False | False | [122](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip-bad-credentials | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/0f35f30be35740dc8f9 | False | False | [125](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-and-route-ip | `http://172.31.14.177:8000` | 403 | False | False | [130](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-and-route-ip | `http://172.31.14.177:8081` | 403 | False | False | [132](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-and-route-ip | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/f5d0fb8d006c41ed805 | False | False | [135](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | proxy-only-dns-default | `http://proxy-only.agentcore.test:80` | 503 | False | False | [143](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | proxy-only-dns-default | `https://proxy-only.agentcore.test:443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://proxy-only.agentcore.test/probe/eab4a0e02747 | False | False | [145](cn-northwest-1-results.jsonl) |

“外部代理未收到且目标未收到”把问题定位在到达测试外部代理之前，但不能单独证明具体 Squid ACL。没有读取到服务配置时，仅依据错误页和端口对照限定结论，不宣称 AWS 内部根因。

HTTP 403 若同时带 `server: squid/6.13` 和 `x-squid-error: ERR_ACCESS_DENIED 0`，可确认托管 Squid 返回访问控制拒绝。HTTPS 的 `ERR_TUNNEL_CONNECTION_FAILED` 单独没有指出具体拒绝原因，需与直连/显式 Playwright 代理、443 端口及无外部访问记录的对照共同解读。

## Squid 只读诊断

### cn-north-1

```json
{
  "readable": false,
  "errorType": "Error",
  "message": "Page.goto: net::ERR_ACCESS_DENIED at file:///etc/squid/squid.conf\nCall log:\n  - navigating to \"file:///etc/squid/squid.conf\", waiting until \"load\"\n"
}
```

### cn-northwest-1

```json
{
  "readable": false,
  "errorType": "Error",
  "message": "Page.goto: net::ERR_ACCESS_DENIED at file:///etc/squid/squid.conf\nCall log:\n  - navigating to \"file:///etc/squid/squid.conf\", waiting until \"load\"\n"
}
```

仅尝试读取 `/etc/squid/squid.conf`，保存 port/method ACL、http_access、always_direct/never_direct 等允许列出的非凭证行及文件哈希；未保存原始配置，未修改服务配置。

## 复现与证据

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-followup.lock.txt
.venv/bin/python run_proxy_validation.py --results-dir results/proxy-reproduction-new
.venv/bin/python export_proxy_validation.py --results-dir results/proxy-reproduction-new
```

使用新的空目录。需要默认 VPC 子网以及创建/删除 IAM、EC2/ENI/安全组、Secret、AgentCore Browser 的权限。会创建收费测试资源；编排最后清理本轮清单。运行器退出 0 仅表示阶段完成，逐项通过/失败以本报告和 JSON 为准。

- [console.log](console.log) · [phase-commands.jsonl](phase-commands.jsonl) · [environment.json](environment.json)
- [attempts.csv](attempts.csv) · [final-results.json](final-results.json) · [run-summary.json](run-summary.json)
- [validation.json](validation.json) · [artifacts.json](artifacts.json) · [source-snapshots/](source-snapshots/)

各区域 `*-proxy-access.json`、`*-origin-access.json` 保存服务端日志；`*-api-audit.jsonl` 保存 SDK 请求/响应及 AWS 请求 ID。每个导航请求的 sessionId、marker、响应头、错误、来源 IP 和日志序号保存在 `*-observations.json`。

## 清理状态

- cn-north-1: FAIL

```json
[
  {
    "kind": "sg",
    "id": "sg-0cb10af93ab6c0181",
    "status": "EXISTS",
    "ok": false
  },
  {
    "kind": "security-group-interfaces",
    "ok": false,
    "interfaces": [
      {
        "NetworkInterfaceId": "eni-012bfc3d15172e094",
        "Status": "in-use",
        "InterfaceType": "agentic_ai",
        "Attachment": {
          "AttachmentId": "ela-attach-0cd34dbbc9512d13b",
          "DeleteOnTermination": false,
          "DeviceIndex": 1,
          "InstanceOwnerId": "amazon-aws",
          "Status": "attached"
        }
      }
    ]
  }
]
```

- cn-northwest-1: FAIL

```json
[
  {
    "kind": "sg",
    "id": "sg-02b620b4720173ddf",
    "status": "EXISTS",
    "ok": false
  },
  {
    "kind": "security-group-interfaces",
    "ok": false,
    "interfaces": [
      {
        "NetworkInterfaceId": "eni-0ee9864df5a9aeca2",
        "Status": "in-use",
        "InterfaceType": "agentic_ai",
        "Attachment": {
          "AttachmentId": "ela-attach-018cc605819d929f3",
          "DeleteOnTermination": false,
          "DeviceIndex": 1,
          "InstanceOwnerId": "amazon-aws",
          "Status": "attached"
        }
      }
    ]
  }
]
```

如安全组等待 AWS 托管 ENI 释放，运行器启动最多 8.5 小时的后台重试，见 deferred-cleanup.json。本报告记录导出时的清理状态，后续后台状态以该文件为准；不会强制分离 AWS 托管接口。

## 与此前报告的关系

09:54 的首次准备尝试因默认子网自动分配公网地址而停止并清理，未进入 Browser 功能测试，记录见相邻目录 `../proxy-validation-20260928/`。本轮显式设置 ENI `AssociatePublicIpAddress=False` 后重新创建，未改动默认子网设置。

参考仓库 9 月 23 日报告使用 `cntest` / 账号 `447150580482`，目标为 HTTP 8081 / HTTPS 8443，外部代理监听 8080。本轮增加相同端口组合和标准端口对照，使用独立账号，不覆盖原报告结果。
- [Reference report](https://github.com/milan9527/aws-agentcore-china-tests/blob/main/COMBINED_TEST_REPORT_ZH.md)
- [AWS Browser proxy documentation](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/browser-proxies.html)
