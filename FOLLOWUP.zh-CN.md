# AgentCore 中国区未通过项目补测结论

最新出站 OAuth 专项测试见 [2LO / 3LO / OBO 完整过程和结果](results/oauth-validation-20260928/REPORT.zh-CN.md)：08:27–08:29 UTC 在两区新环境再次验证，2LO、3LO 通过，四种 OBO 配置仍在 Gateway 目标创建时受账号限制，共保留 16 次拒绝的请求 ID。

该专项使用自建合成 IdP 和 `CustomOauth2`，配置了 OAuth client `cn-retest` 及每区随机生成的 client secret；未接入 Microsoft Entra ID、Google、Okta 等任何第三方。2LO/3LO 的成功适用于该测试 IdP，第三方兼容性尚未验证。RFC 7523 配置测试不代表 Microsoft OBO 测试；OBO 在 Gateway 目标创建阶段即受阻，未执行 Gateway 交换。

测试日期：2026 年 9 月 28 日；调用者 IAM 复测：9 月 29 日（UTC）<br>
AWS Profile：`china`；账号：`209915754514`  
区域：北京 `cn-north-1`、宁夏 `cn-northwest-1`

**两地补测结果一致。有效 JWT、OAuth client credentials、OAuth authorization code、JWT 透传均已完整通过；Browser 代理在正确配置和标准端口下通过。Live View 延长观察后，画面和人工输入均通过，原 DCV 失败结论已更正。调用者 IAM 转发于 9 月 29 日复测通过；Playwright `save_as()` 仍保留上一轮失败结论，已有两地验证通过的文本及二进制取回方法。**

本报告更新[初测历史报告](REPORT.initial.md)中的未通过项目；当前合并结果见[中文摘要](SUMMARY.zh-CN.md)及[英文完整报告](REPORT.md)。初测失败、排查中的配置错误和后续成功结果均保留在过程记录中；不能将某个修正配置下的通过，解读为所有配置均已通过。

## 逐项结论

| 原未通过项目 | 北京 | 宁夏 | 明确结论 |
| --- | --- | --- | --- |
| CUSTOM_JWT 有效令牌调用 | 通过 | 通过 | 合成 OIDC 提供商签发的有效 JWT 可调用 Lambda 工具；错误 audience、client、scope 及过期令牌均被拒绝 |
| OAuth client credentials | 通过 | 通过 | Gateway 实际获取令牌并调用受保护后端，后端确认 grant 为 `client_credentials` |
| OAuth authorization code | 通过 | 通过 | 完成 URL elicitation、授权回调、用户会话绑定和恢复工具调用；后端确认 grant 为 `authorization_code` |
| JWT 透传 | 通过 | 通过 | `CUSTOM_JWT` 入站 + HTTP `JWT_PASSTHROUGH` 出站；后端收到令牌的 SHA-256 与客户端原令牌一致，无效令牌被拒绝 |
| Browser 代理鉴权与路由 | 有条件通过 | 有条件通过 | Basic 鉴权和无鉴权代理均通过；80/443 端口通过；上游专用域名需显式配置 `externalProxy.domainPatterns` |
| Browser 代理绕过 | 通过 | 通过 | 标准 80 端口、独立绕过测试通过；此前 8000 端口被内置代理拒绝 |
| Playwright `download.save_as()` | 仍失败 | 仍失败 | 1.63.0 与对应 Chromium 148 的 1.60.0 均产生零字节；文件存在远端，客户端对应路径不存在。直接调用 `save_as()` 不能完成此连接方式下的文件传输 |
| Browser 文件取回替代方法 | 通过 | 通过 | 通过 CDP 文件输入接口和 `File.arrayBuffer()` 取回文本与二进制，字节数及哈希一致 |
| DCV 实时画面和人工输入 | 通过（更正） | 通过（更正） | 原测试在鉴权连接关闭错误后提前退出；继续等待约 6–7 秒收到首帧，修正工具栏坐标后输入也通过，见[专项记录](LIVEVIEW.zh-CN.md) |
| Gateway 调用者 IAM 转发 | 通过（9 月 29 日复测） | 通过（9 月 29 日复测） | AssumeRole 两种入站模式及 GetSessionToken 均返回 HTTP 200、sum=42；每区 8 项同凭证对照全通过 |
| Gateway OAuth Token Exchange | 账号限制 | 账号限制 | 创建目标时明确返回 `Token Exchange is not available for this account`，并非缺测试令牌 |
| Gateway 私有目标 | 账号限制 | 账号限制 | 明确要求为账号启用 VPC egress；Browser 的 VPC 访问已独立通过 |
| Gateway / Browser PrivateLink | 当前未提供 | 当前未提供 | 分页遍历该账号的 EC2 端点服务目录，两地均未公布 AgentCore 服务名称 |

“仍失败”表示当前测试条件下的功能失败；AWS 内部根因需要服务日志才能确认。本次未声称能够从客户端定位其内部代码缺陷，也未代用户提交支持工单。

## 1. 鉴权补测：原先的测试前提已补齐

本次使用自建的临时 HTTPS 合成 OIDC/OAuth 服务，只包含测试身份和测试密钥，不依赖真实用户或第三方生产账号。中国区 API Gateway 的公开测试接口仍返回 403，随后改用本地测试服务和临时 HTTPS 隧道。两个中国区域均能实际访问该测试提供商。

有效 JWT 测试使用 RS256，设置 `iss`、`aud`、`client_id`、`sub`、`scope`、`iat`、`exp`，通过 Gateway 调用加法工具得到 42；逐项修改 audience、client、scope、有效期后，请求均被拒绝。

授权码流程通过的完整顺序为：

1. Gateway 支持 MCP `2026-07-28`，客户端声明 URL elicitation 能力。
2. Gateway 执行角色具有 `GetWorkloadAccessTokenForJWT` 等所需权限，工作负载身份登记允许的回调 URL。
3. 工具调用返回 `input_required` 和授权 URL。
4. 使用同一个 HTTP 会话完成 AgentCore → 合成 IdP → AgentCore → 应用回调的重定向，保留 Cookie。
5. 从应用回调取得 `session_id`，按需补全 `urn:ietf:params:oauth:request_uri:` 前缀。
6. 调用 `CompleteResourceTokenAuth`，使用原入站用户 JWT 绑定会话。
7. 携带 `inputResponses` 恢复工具调用，返回 `resultType=complete`，后端确认授权码令牌。

排查过程中，旧 MCP 版本、缺少角色权限、未保留 Cookie、未执行会话绑定，均曾导致失败；修正后已重复验证成功。对应脚本为 [retest_authcode.py](retest_authcode.py)。

文档还存在一处说明冲突：出站鉴权概览曾将令牌透传与 `AUTHENTICATE_ONLY` 关联，但入站文档说明该模式基于 SigV4。本次实际通过的组合是 **`CUSTOM_JWT` + `JWT_PASSTHROUGH`**。

## 2. Browser 代理：能力通过，配置边界已确认

09:56–10:12 新建独立环境进一步验证，见 [Browser 代理再次验证结论](PROXY-VALIDATION.zh-CN.md)。每区 95 项检查（60 PASS / 35 FAIL），每项失败均复现两次。新增 HTTP 8081、代理监听 8080、精确 IP/主机名/后缀绕过、错误凭证及多代理选择。HTTP 8000/8081 明确返回托管 `squid/6.13` 的 `ERR_ACCESS_DENIED 0`，两端日志证明未到外部代理；HTTPS 8443 同样未到外部代理。具体 Squid ACL 文件不可读，未认定某条内部配置的根因。

两地验证了以下组合：

| 场景 | 结果 |
| --- | --- |
| Basic 鉴权代理，HTTP 80 / HTTPS 443 | 通过 |
| 无鉴权代理，HTTP 80 / HTTPS 443 | 通过 |
| 显式 `domainPatterns`，由上游代理识别的专用域名 | 通过 |
| 未设置 `domainPatterns`，由上游代理识别的专用域名 | 失败，内置 Squid 返回 DNS 503 |
| 独立绕过配置，访问私有 DNS 的 HTTP 80 端口 | 通过 |
| 测试目标使用 HTTP 8000 / HTTPS 8443 | 失败，分别出现 Squid 403 / CONNECT 失败 |

代理服务端日志记录了真实的 HTTP 请求、到目标 443 端口的 CONNECT，以及 Basic 凭证验证结果。日志仅记录凭证是否存在、验证是否成功，不记录凭证内容。

此前将私有 DNS 绕过规则与指向同一主机 IP 的代理路由放在一个场景中，会导致目标 IP 经反向 DNS 匹配绕过规则。最终路由测试移除了绕过条件，并将绕过功能单独验证。

可用配置示例：

```python
proxyConfiguration = {
    "proxies": [{
        "externalProxy": {
            "server": "<代理主机名或IP，不含http://>",
            "port": 3128,
            "credentials": {
                "basicAuth": {"secretArn": "<包含username/password的Secret ARN>"}
            },
            "domainPatterns": ["target.example.com"]
        }
    }],
    "bypass": {"domainPatterns": ["bypass.example.com"]}
}
```

`domainPatterns` 位于 `externalProxy` 内部。选择绕过域名时，应避免它同时匹配需要走代理的目标。80/443 与 8000/8443 是本次实际验证的端口，未据此推断其他所有端口的行为。

脚本：[retest_proxy.py](retest_proxy.py)、[retest_proxy_ports.py](retest_proxy_ports.py)。  
服务端日志：[北京](results/retest/cn-north-1-proxy-access.json)、[宁夏](results/retest/cn-northwest-1-proxy-access.json)。

## 3. 下载：远端文件正常，`save_as()` 未成功取回文件

在默认上下文、新建上下文、Playwright 1.63.0 和 1.60.0 中均复现零字节。1.60.0 所对应的 Chromium 版本为 `148.0.7778.96`，与远端 `148.0.7778.258` 属于同一版本系列。

实际检查发现：

- `download.failure()` 返回空值。
- Playwright 返回的下载路径在客户端不存在。
- 同一路径在远端浏览器可读取正确的 `agentcore-download-ok`。
- 本地 Chromium 的同样下载操作正常。

因此可以将问题定位到 **CDP 远端连接下的文件取回环节**，而非远端浏览器下载失败；切换到匹配的 Playwright 版本不能解决。

已验证的替代实现位于 [download_remote_file.py](download_remote_file.py)：

```python
from pathlib import Path
from download_remote_file import read_remote_file

# context 是已经通过 SigV4 连接到 AgentCore Browser 的 Playwright 上下文。
# remote_path 必须指向本次会话中已知的测试下载文件。
data = read_remote_file(context, remote_path)
Path("downloaded.bin").write_bytes(data)
```

该方法利用 `DOM.setFileInputFiles` 让远端浏览器读取自己的文件，再用 `File.arrayBuffer()` 经现有 CDP 连接返回字节。两地均通过 **21 字节文本**和 **8192 字节、包含全部 0–255 字节值的二进制文件**校验。未进行大文件性能测试。

## 4. 调用者 IAM 转发：9 月 29 日复测通过

**最新结果：2026-09-29 01:58–01:59 UTC，两区全新 Runtime / Gateway 的每区 8 项对照全部通过。** 核心复现脚本与 9 月 28 日一致，SDK 版本未变；调用者转发均返回 HTTP 200、`sum=42`，原无效令牌 403 在所测路径未再出现。本次新增资源已清理，独立核验通过。[本次报告与命令](results/repro-caller-confirm-20260929/REPORT.zh-CN.md)、[完整控制台输出](results/repro-caller-confirm-20260929/console.log)、[最新响应与请求 ID](results/repro-caller-confirm-20260929/invocation-results.csv)。

| 凭证 / 入站模式 | 直接调用 Runtime | Gateway 执行角色出站 | 调用者 IAM 出站 |
| --- | --- | --- | --- |
| STS `GetSessionToken` + `AWS_IAM` | 通过 | 通过 | HTTP 200，sum=42 |
| STS `AssumeRole` + `AWS_IAM` | 通过 | 通过 | HTTP 200，sum=42 |
| STS `AssumeRole` + `AUTHENTICATE_ONLY` | 同一凭证直接调用通过 | 通过 | HTTP 200，sum=42 |

9 月 28 日同一对照仍是每区 5 PASS / 3 FAIL，错误为 `The security token included in the request is invalid`，[历史报告](results/repro-caller-confirm-20260928/REPORT.zh-CN.md)与原始证据保留。本次确认调用行为恢复，未确认 AWS 内部根因或部署时间。`GATEWAY_IAM_ROLE` 与调用者凭证仍是两种不同权限语义。

两地实际接受创建 `AUTHENTICATE_ONLY` Gateway，且该模式下的执行角色出站调用通过；这与中国区概览仅列出 `AWS_IAM` / `CUSTOM_JWT` 的说明存在差异。本报告保留实际 API 结果，不将该模式直接列为中国区不支持。

早一轮 AssumeRole 对照的请求 ID（保留历史；本次最新 ID 见上方链接）：

| 区域 | AWS_IAM 入站 | AUTHENTICATE_ONLY 入站 |
| --- | --- | --- |
| 北京 | `b3752ba3-ad3b-4baf-ba50-f456443ceb33`、`e1e08000-7b81-47f6-9507-b4bb68f16e90` | `4b462c3a-38f7-42d0-8941-9734c6b6355e`、`100bbec5-c396-4a8d-a994-4ffc7ad7d593` |
| 宁夏 | `3ed694a0-36cf-4bbb-8341-1773d8e3a05f`、`f70990fb-f44e-44b9-8a1b-b05589029139` | `780aea03-3c6a-4dd3-a1e3-0673c76f24df`、`693f6dbf-bebd-4fd6-8ade-332b50a8aaeb` |

脚本：[retest_runtime.py](retest_runtime.py)。时间与完整响应见区域 JSONL。

## 5. DCV：延长观察后通过，原结论更正

补测使用 AWS 官方 `bedrock-agentcore` TypeScript SDK `0.4.4` 的 BrowserLiveView 组件及随包提供的 DCV 客户端。早期测试在鉴权后收到 `Failed to communicate with server` 即退出，当时记录：

```json
{
  "authenticated": true,
  "connected": false,
  "firstFrame": false,
  "errors": ["Failed to communicate with server."]
}
```

用户提出延长等待后，增加逐事件时间戳，发现该错误来自 `/live-view/auth` WebSocket 的关闭回调，发生在鉴权成功之后、显示连接成功之前。原测试将它作为提前结束条件，约 2.7 秒就退出，尚未等到实际首帧。

保持原 300 秒签名有效期，取消错误回调触发的提前退出后，北京首次首帧为 **6.450 秒**、宁夏为 **6.728 秒**；随后独立会话也收到画面。Live View 展示整个浏览器窗口，点击坐标还需要加上工具栏高度；本次为 87 像素。修正后，两地通过 Live View 键入 `dcv-official-input-ok`，远端 DOM 验证一致。

**更正结论：Live View 显示和人工输入均通过。此前“DCV 显示连接失败”的判断来自测试代码过早结束，不是已证实的服务功能失败。** 鉴权连接关闭错误仍保留在日志中；它的内部原因未确认，但本次没有阻止后续画面和输入。

持续观察、同一会话重新连接、截图及复现命令见 [Live View 延时专项报告](LIVEVIEW.zh-CN.md)。SDK 连接逻辑未修改，测试包装器保持 `observers` / `callbacks` 互斥。

同时发现 TypeScript SDK 的 URL 生成方法硬编码 `.amazonaws.com`。本次使用服务返回的 `.amazonaws.com.cn` 端点生成签名，避免该 SDK 中国分区端点问题影响测试。

前端源码：[retest-viewer/main.jsx](retest-viewer/main.jsx)、[连接观察包装器](retest-viewer/dcv-probe.js)；测试：[retest_live_wait.py](retest_live_wait.py)、[retest_browser.py](retest_browser.py)。

## 6. 无法由客户端补齐的账号 / 服务前提

| 项目 | 服务返回 / 查询结果 | 后续条件 |
| --- | --- | --- |
| Gateway Token Exchange | `AccessDeniedException: Token Exchange is not available for this account` | AWS 为该账号启用功能；OAuth 提供商本身创建成功 |
| Gateway 私有目标 | `Private endpoint configuration requires VPC egress feature to be enabled for this account.` | AWS 为该账号启用 Gateway VPC egress |
| Gateway / Browser PrivateLink | 分页查询 EC2 服务目录，AgentCore 服务名称为空 | 对应区域向该账号提供端点服务后再测 |

上述结论仅适用于测试时的账号及区域，不推断所有中国区账号永远不可用。不能通过修改客户端参数将账号级功能开关补齐。

## 过程记录、复现与清理

- [复现说明及命令](REPRODUCE.zh-CN.md)
- [排查过程与修正记录](WORKLOG.zh-CN.md)
- [完整检查时间线 JSONL](results/followup-history.jsonl)
- [补测最终结果 JSON](results/followup-latest.json)
- [补测逐项矩阵 CSV](results/followup-matrix.csv)
- 原始记录：[北京](results/retest/cn-north-1-results.jsonl)、[宁夏](results/retest/cn-northwest-1-results.jsonl)
- 浏览器兼容性记录：[北京](results/retest-browser/cn-north-1-results.jsonl)、[宁夏](results/retest-browser/cn-northwest-1-results.jsonl)
- 逐请求审计：[北京](results/retest/cn-north-1-api-audit.jsonl)、[宁夏](results/retest/cn-northwest-1-api-audit.jsonl)
- [补测清理状态](results/followup-cleanup.json)
- [交付材料校验](results/delivery-validation.json)、[凭证扫描结果](results/credential-scan.json)

凭证、令牌、授权码、OAuth 回调会话参数和 Cookie 已脱敏；保留资源 ARN、请求 ID、Browser / Runtime 会话 ID、时间和测试数据哈希。临时 HTTPS 提供商随测试关闭，复现时重新创建，不能重复使用过期 URL 或已删除的资源。

最终只读清理核验确认：测试 Gateway、Browser、Runtime、Lambda、API Gateway、S3、IAM 角色及自建 Secret 已删除，EC2 实例已终止，无测试 EBS 卷残留；独立浏览器补测清理通过。初测和补测仍有以下等待项：

| 区域 | 初测安全组 | 补测安全组 | 初测 KMS 删除计划（UTC） |
| --- | --- | --- | --- |
| 北京 | `sg-00ea1d13ed36ba5d3` | `sg-03179feaec145cf84` | `9fc74828-2ad7-4602-b21b-054a406c75a0`，2026-10-05 05:27:41 |
| 宁夏 | `sg-074039951f97aedee` | `sg-0e9e501fda1882754` | `e9e12008-d491-4524-945e-6d358281618a`，2026-10-05 05:27:32 |

四个安全组仍关联 AWS 管理的 AgentCore ENI。AWS 文档说明接口可能在资源删除后保留最多八小时；两个本地清理进程正在有界重试，依赖工作区进程持续运行。**清理尚未全部完成。** 上表为报告生成时快照，后续状态见[初测清理进程](results/deferred-cleanup.json)、[补测清理进程](results/retest/deferred-cleanup.json)及各区域只读核验文件。
