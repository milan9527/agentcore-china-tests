# AgentCore 中国区测试过程记录

日期为 2026 年 9 月 28 日，以下时间均为 UTC。完整逐项时间线见 [followup-history.jsonl](results/followup-history.jsonl)，最终结论见 [FOLLOWUP.zh-CN.md](FOLLOWUP.zh-CN.md)。

## 初测：04:15–05:30

使用 `china` profile 在北京、宁夏创建临时环境，执行 Gateway 和 Browser 功能检查。每区初测统计为 159 项检查：145 通过、6 失败、5 受前提限制、1 部分验证、2 当前不可用。初测报告归档于 [REPORT.initial.md](REPORT.initial.md)；[REPORT.md](REPORT.md)与[中文摘要](SUMMARY.zh-CN.md)已合并补测结果，每区为 153 通过、2 失败、2 受限、2 当前不可用。

初测结束后删除资源；两把 KMS 密钥进入七天删除窗口，两个安全组等待 AgentCore ENI 释放。初测清理进程使用原始 `results/`，后续补测使用独立目录，避免互相覆盖资源状态。

## 补测：从 05:40 开始

| 顺序 | 阶段 / 动作 | 实际观察 | 后续处理 |
| --- | --- | --- | --- |
| 1 | 重建最小鉴权测试环境 | 中国区 API Gateway 的 CUSTOM 请求鉴权接口仍返回公开访问 403 | 保留环境失败记录，改用独立合成 HTTPS IdP |
| 2 | 启动本地合成 IdP 和临时 cloudflared 隧道 | 隧道域名存在短暂 DNS 生效延迟；最初探测失败，稍后返回 200 | 增加等待及错误处理；实际验证发现文档、令牌签名与后端鉴权 |
| 3 | AWS 官方 BrowserLiveView 组件 | 首次构建缺 Cloudscape/Babel 依赖 | 安装所需依赖并锁定；重新构建 |
| 4 | Playwright 1.63 默认及新建上下文下载 | 两地 `save_as()` 均零字节；本地 Chromium 基线正常 | 增加匹配 Chromium 148 的 Playwright 1.60 对照 |
| 5 | JWT、JWT 透传、client credentials | 两地均通过；JWT 负例被拒绝；透传令牌哈希一致 | 从“前提不足”更新为实际通过 |
| 6 | Token Exchange | 提供商配置通过；创建 Gateway 目标明确返回账号不可用 | 归类为账号开关限制，不再归因于缺 IdP |
| 7 | 授权码首次调用 | 默认旧 MCP 版本无法触发 URL elicitation | 显式使用 MCP 2026 与 URL elicitation 能力 |
| 8 | 授权码用户身份令牌 | 执行角色缺 `GetWorkloadAccessTokenForJWT` | 补充测试角色权限，等待传播 |
| 9 | 授权重定向 | 各请求使用独立 HTTP 会话，回调返回 Cookie 缺失 400 | 改用同一 `requests.Session()` 保留 Cookie |
| 10 | 授权回调完成后恢复调用 | 回调成功，但仍要求授权 | 读取 `session_id`，调用 `CompleteResourceTokenAuth` 绑定用户 |
| 11 | 授权码最终验证 | 两地绑定成功，恢复工具返回 `resultType=complete`，后端 grant 正确 | 使用新的合成用户标识再次验证，仍通过 |
| 12 | Runtime 调用者 IAM | 新 Runtime 创建等待数分钟；完成后直接、Gateway 角色调用通过 | 继续 AssumeRole 与两种入站模式对照 |
| 13 | `AWS_IAM` / `AUTHENTICATE_ONLY` + AssumeRole | 两地 caller-IAM 均无效令牌 403；同一凭证基线成功 | 保存请求 ID，确认为稳定功能失败，内部根因待 AWS 确认 |
| 14 | Playwright 1.60 文件路径诊断 | 下载路径在客户端不存在，在远端内容正确；仍零字节 | 明确是远端文件取回问题，继续验证可用传输方法 |
| 15 | CDP 网络/资源接口取回尝试 | `Network.loadNetworkResource` 拒绝 file URL；`Page.getResourceContent` 遇到未启用或未缓存资源 | 保留失败；改用远端文件输入接口 |
| 16 | 本地浏览器启动与 DCV 观察包装器 | 1.60 默认本地二进制未安装；完整 Chrome 缺 libcups；观察包装器曾同时传 callbacks/observers | 指定已安装 headless shell，并保持 callbacks/observers 互斥 |
| 17 | 官方组件最终 DCV 对照 | 鉴权成功，显示连接失败，无首帧；与初测相同 | 记录当前不可用，未将配置实验错误计为服务根因 |
| 18 | CDP 文件输入取回 | 文本成功；后续 8192 字节二进制也逐字节一致 | 提供可复用 `download_remote_file.py` |
| 19 | 私有代理初始对照 | Playwright 显式代理 HTTP 和 HTTPS 均通过；服务配置在 8000/8443 失败 | 增加代理访问日志、无鉴权对照、显式域名配置 |
| 20 | 代理参数试验 | `server` 含 `http://` 被 API 拒绝；`domainPatterns` 放错层级被 SDK 拒绝 | 按 API 模型修正为裸主机名及 `externalProxy.domainPatterns` |
| 21 | 显式域名、非标准端口 | 上游专用域名 HTTP 通过；8443 和 8000 仍失败 | 替换测试实例，添加标准 80/443 监听 |
| 22 | 标准端口与组合绕过 | 80/443 访问成功；IP 目标经反向 DNS 匹配绕过规则，未经过外部代理 | 将路由与绕过测试拆分，避免相互影响 |
| 23 | 标准端口最终代理矩阵 | Basic/无鉴权、默认/显式代理的 HTTP/HTTPS 均通过；独立绕过通过 | 服务日志确认 GET、CONNECT 443 及正确凭证 |
| 24 | 上游专用域名边界 | 未显式配置域名时 DNS 503，配置后通过 | 记录为配置边界并给出可用示例 |
| 25 | 私有目标与 PrivateLink 复核 | Gateway 私有目标明确要求账号启用 VPC egress；分页目录无 AgentCore 端点 | 记录账号及服务可见性限制 |
| 26 | 汇总结论与清理 | 保留全部历史失败；单独记录正确配置下的通过 | 删除补测资源、停止临时 IdP、生成最终证据与复现说明 |
| 27 | 交付材料校验 | 汇总 984 条历史记录；20 组阶段快照、843 个快照文件的哈希匹配；链接、行号引用和下载字节一致 | 保存校验结果、脱敏记录及凭证扫描结果 |
| 28 | 新增一键编排的本地检查 | Python 编译与命令帮助正常，官方前端构建通过；模拟功能失败及阶段异常时的退出码与清理路径通过 | 未另行从空环境执行完整云端编排，不计为新增云端功能测试 |

## 后续 Live View 延时复核：06:35 起

用户提出“是否等待时间不足”后，复核发现原等待条件在收到任何错误回调时就退出。新增逐事件时间戳、每 30 秒心跳和 WebSocket 计数，分别观察首次连接与同一会话新签名重连。

1. 首先尝试把签名有效期增至 900 秒，出现鉴权握手 403；保留该配置试验，恢复原 300 秒签名。
2. 默认签名复核显示：约 2 秒的错误是鉴权连接关闭回调；显示连接约 3 秒成功，首帧约 6–7 秒到达。原“显示失败”结论因此更正。
3. 观察期间远端时钟和接收字节持续变化，两地各执行首次 300 秒及重连后 300 秒观察；确切时长见专项报告。
4. 最初使用网页内容坐标在完整浏览器画面中点击，输入为空；补上 87 像素工具栏偏移后，两地通过 Live View 实际键入文本，远端 DOM 校验成功。
5. 并发复用同一会话 CDP 的一次尝试被 429 拒绝，随即改用独立会话完成对照；相关失败保留。
6. 更新报告与常规测试等待条件；原失败行保留，追加引用成功证据的更正结论。

详细时间、截图、命令与清理见 [LIVEVIEW.zh-CN.md](LIVEVIEW.zh-CN.md)。下列规则同样适用于本次复核。

## 记录方式与解释规则

1. 初测、补测、浏览器兼容性补测分别使用 `results/`、`results/retest/`、`results/retest-browser/`。
2. JSONL 记录采用追加方式，未删除配置错误或失败尝试。后续脱敏只替换敏感值，不改变时间、状态、用例名称和结果。
3. 用户要求完整记录后，新增 AWS API / HTTP 审计及逐阶段源码快照。之前没有记录的原始请求不作追溯伪造。
4. 最终结论针对明确的配置组合。代理 80/443 通过不能抹除 8000/8443 的失败；CDP 替代取回成功不能改写 `save_as()` 的失败。
5. 每次排查修正的动机和结果列于上表；最终复现脚本保留当前有效方法，源码快照用于回看中间版本。
6. 请求 ID、ARN、会话 ID、时间、哈希保留；长期凭证、临时令牌、授权码、Cookie、测试私钥不作为共享证据保留。

## 中英文报告合并更正

后续按用户要求，将主报告从“开头提示补测、正文仍保留初测结论”改为完整反映最新结果。`REPORT.md`、`SUMMARY.zh-CN.md`、`final-results.json` 和 `feature-matrix.csv` 统一采用每区原有 159 项检查范围，合并同名补测记录后为 153 通过、2 失败、2 受限、2 当前不可用。Live View 正文、统计和矩阵均更正为通过，保留提前结束及输入坐标修正的解释。

初测中英文 Markdown 归档于 `REPORT.initial.md` 和 `SUMMARY.initial.zh-CN.md`，初测结构化结果另存 `initial-results.json` / `initial-feature-matrix.csv`。此轮仅处理本地报告，没有调用 AWS 或修改历史测试日志。[报告一致性校验](results/report-correction-validation.json)核对双语统计、首帧时间、矩阵行、证据引用和历史日志哈希。

## 调用者 IAM 再次复现：07:48–07:54 UTC

使用 `china` profile 在两地新环境执行 `retest_setup`、`retest_runtime`、`caller_baseline_tests`，开启 `RETEST_VERBOSE=1` 打印阶段、30 秒等待状态和完整脱敏结果。两地 Runtime 分别约 223 / 222 秒达到 READY。07:53 的调用对照中，每区 5 项直接调用 / 执行角色成功，3 项调用者转发返回 `The security token included in the request is invalid`。包含 AssumeRole 配合 AWS_IAM / AUTHENTICATE_ONLY，以及同组 GetSessionToken 凭证的三路对照。

07:54 删除本次 Gateway、Runtime、目标、工作负载身份、Lambda、API、桶和 IAM 角色，生成的本地测试秘密已删除；两地只读清理核验 PASS。运行专用编排退出码为 2，表示问题已复现。初测和此前补测的证据未改写，本次目录为 `results/repro-caller-confirm-20260928/`。[完整输出](results/repro-caller-confirm-20260928/console.log)、[逐项响应](results/repro-caller-confirm-20260928/invocation-results.json)、[复现报告](results/repro-caller-confirm-20260928/REPORT.zh-CN.md)。

## Gateway 出站 OAuth 专项：08:27–08:29

使用 `china` profile 运行 `.venv/bin/python run_oauth_validation.py --results-dir results/oauth-validation-20260928`，在北京、宁夏各创建独立 IAM 角色、AgentCore Gateway、OAuth provider 和合成 HTTPS IdP。运行从 08:27:03 开始，08:29:50 完成；临时隧道发现文档约一分钟后可访问，未修改超时或重复创建整套环境。

两区 2LO 的 CLIENT_SECRET_BASIC / CLIENT_SECRET_POST 均通过实际 Gateway 调用；后端令牌哈希与 IdP 签发记录匹配，并不同于入站 JWT。再次调用仍通过，本次每个 2LO 再次调用均重新请求令牌端点。3LO 通过首次授权要求、合成授权重定向、CompleteResourceTokenAuth 用户绑定、恢复工具调用、同用户再次调用与另一用户隔离检查；同用户再次调用没有新令牌请求。

OBO 覆盖 RFC 8693 的 NONE / M2M / AWS_IAM_ID_TOKEN_JWT 三种 actor 和 RFC 7523 JWT_AUTHORIZATION_GRANT。八个 provider（每区四个）配置与回读成功；每种配置创建两个 Gateway 目标，共 16 次均为 `CreateGatewayTarget` HTTP 403，`Token Exchange is not available for this account`。每个 OBO 测试窗口均无 Gateway 到 IdP 的令牌请求；IdP 直接交换成功仅作前提对照，不计为 Gateway OBO 通过。

每区 12 项专项检查为 8 PASS、4 BLOCKED、0 FAIL；执行无异常，编排退出码 2 表示账号限制。Gateway、目标、provider、workload identity、IAM 角色、本地进程和私钥文件均完成清理核验；回查时每区五个服务托管 Secret 带删除标记，等待 AWS 异步删除。未操作此前调查的资源清单。

08:33 起进行本地报告导出和证据核验：378 份阶段源码文件哈希通过，22 个关键请求关联到原始审计行，16 个 OBO 拒绝均核对服务名、操作名、状态码与错误。导出器最初读取 HTTP 头未忽略大小写，索引验证报 KeyError；修正为不区分大小写后通过，此为本地证据索引问题，未重跑或改写云端结果。使用 `.venv/bin/python export_oauth_validation.py --results-dir results/oauth-validation-20260928` 可重建本次基线的中英文报告；若未来实际结果改变，导出器拒绝覆盖解释，应以运行器的新结果报告为准并重新分析。

[中文专项报告](results/oauth-validation-20260928/REPORT.zh-CN.md) · [English report](results/oauth-validation-20260928/REPORT.md) · [完整控制台](results/oauth-validation-20260928/console.log) · [命令记录](results/oauth-validation-20260928/phase-commands.jsonl) · [请求索引](results/oauth-validation-20260928/request-index.csv) · [核验结果](results/oauth-validation-20260928/validation.json)。

## OAuth client 与第三方 IdP 范围澄清

根据本次实际配置与请求记录，补充中英文专项报告、主报告和 README：使用了 OAuth client `cn-retest`，每区随机生成独立 client secret；2LO 测试 Basic/POST 客户端认证，3LO/OBO 使用 Basic。IdP 为自建合成 OIDC/OAuth 服务，通过 `CustomOauth2` 接入，没有接入 Microsoft Entra ID、Google、Okta 等第三方。

2LO/3LO 的通过只覆盖自建 IdP 的端到端流程，不能推断第三方兼容性；RFC 7523 提供商配置不等于 Microsoft OBO 集成。OBO 已配置客户端和提供商，但在创建 Gateway 目标时受账号限制，未执行 Gateway 到 IdP 的交换。`actorTokenContent=NONE` 仅表示不附带 actor token，与 No Authorization 无关。

此次为文档补充，同步更新报告生成脚本并重新生成专项报告及哈希清单，没有新增 AWS 测试；原始调用日志、结果行及执行时源码快照保留不变。

## Browser 代理独立复核：09:54–10:14 UTC

用户要求继续验证 proxy，并参考另一账号的 9 月 23 日报告。先检查其测试代码和报告：外部代理为 Python 服务，既有失败使用目标 HTTP 8081 / HTTPS 8443，尚缺标准端口及独立目标对照。本轮使用 `china` profile，在北京、宁夏各建立两个独立私有 EC2，分别运行真实转发的 Python 代理和目标服务；没有使用客户自建 Squid。

首次准备于 09:54:29–09:55:27 执行。默认子网仍向预建 ENI 分配公网地址，准备阶段断言失败，尚未创建 Browser 或运行功能检查，随后完成清理。保留 [首次运行记录](results/proxy-validation-20260928/run-summary.json)。修正为启动实例前显式调用 `modify_network_interface_attribute(..., AssociatePublicIpAddress=False)`，未修改共享子网默认设置。

第二轮使用 `.venv/bin/python run_proxy_validation.py --results-dir results/proxy-validation-20260928-r2`，09:56:26 开始，10:13:45 完成编排。目标端口为 HTTP 80/8000/8081、HTTPS 443/8443；代理监听 3128/8080（Basic）和 3129（无认证）。每次导航使用唯一 marker，并保存 sessionId、响应头、错误、目标来源 IP 及代理/目标日志；TLS 校验保持开启，另设未安装 CA 的拒绝对照。

每区 95 个唯一检查为 60 PASS、35 FAIL，每个失败再次尝试且结果一致，共记录 260 次请求观察。直连及 Playwright 新上下文显式代理的五种目标端口全部通过；托管 `proxyConfiguration` 的三种代理监听与默认/显式路由组合均在目标 80/443 通过，8000/8081 返回带 `server: squid/6.13` 和 `ERR_ACCESS_DENIED` 的 HTTP 403，8443 返回 `ERR_TUNNEL_CONNECTION_FAILED`。所有这些失败均没有对应外部代理或目标访问日志。

绕过覆盖精确 IP、主机名、域名后缀、错误凭证和同时匹配路由的组合：80/443 成功且目标来源为 Browser，非标准端口仍失败。代理专用域名默认路由失败，显式 `externalProxy.domainPatterns` 后 HTTP/HTTPS 均通过。多代理选择、错误/缺失凭证拒绝及证书拒绝对照均通过。每区 35 个失败由托管代理非标准端口 18 项、绕过非标准端口 15 项、代理专用域名默认路由 2 项组成，不代表 35 个独立缺陷，也不并入主报告 159 项统计。

HTTP 拒绝明确来自托管 Squid；HTTPS 失败定位在外部代理之前。只读诊断访问 `/etc/squid/squid.conf` 两区均为 `ERR_ACCESS_DENIED`，未读取或保存原始配置，也未修改托管层。因此未断言具体 `Safe_ports` / `SSL_ports` 规则，只记录有日志支持的拒绝位置。

本轮 40 个 Browser 会话、两个 Browser 资源、四台 EC2、四个自建 ENI 和两个 IAM 角色已清理，六个 Secret 已请求删除。10:16 UTC 回查，北京 `sg-0cb10af93ab6c0181` 仍依赖 AWS ENI `eni-012bfc3d15172e094`，宁夏 `sg-02b620b4720173ddf` 仍依赖 AWS ENI `eni-0ee9864df5a9aeca2`；未强制分离。后台 PID `2433055` 自动重试至最长 18:43 UTC，整体清理验证仍未通过，状态由 [后台清理记录](results/proxy-validation-20260928-r2/deferred-cleanup.json)持续更新。

使用 `.venv/bin/python export_proxy_validation.py --results-dir results/proxy-validation-20260928-r2` 离线导出中英文报告。10:14:52 的证据核验通过：260 行观察、206 份源码快照哈希及两端日志关联一致，清单含 243 份产物。该 PASS 仅代表证据一致性；运行器退出码 0 仅代表编排完成，均不代表所有功能通过。清理进程可能继续修改状态文件，产物哈希清单明确为生成时快照。

10:18:47 完成本地交付核验：六个 Python 文件语法解析通过，344 个本地文档链接可解析，两区检查数量及失败重试结果一致；对两个运行目录的 51 个非源码文本证据执行结构化脱敏复核，无新增命中。`git diff --check` 通过。结果保存在 [本地交付核验](results/proxy-documentation-validation-20260928.json)，未新增 AWS 功能调用。

[结论和复现入口](PROXY-VALIDATION.zh-CN.md) · [完整中文矩阵](results/proxy-validation-20260928-r2/REPORT.zh-CN.md) · [English report](results/proxy-validation-20260928-r2/REPORT.md) · [完整控制台](results/proxy-validation-20260928-r2/console.log) · [实际命令](results/proxy-validation-20260928-r2/phase-commands.jsonl) · [260 次观察](results/proxy-validation-20260928-r2/attempts.csv) · [证据核验](results/proxy-validation-20260928-r2/validation.json)。

## Gateway 中国区介绍文案核对

用户询问统一工具入口、逐用户请求/令牌/连接时长限额的表述是否准确。核对已有中国区结果和官方限流文档，统一工具入口已覆盖受支持 API、Lambda、MCP Server 的发现与调用；已有请求限流测试仅覆盖 `targetName` 维度和零速率 HTTP 429。JWT/IAM 用户维度、推理 token 与并发连接限额有文档定义，本轮未实测其在中国区的完整执行。

`connections` 表示并发连接数，不能写成连接时长；MCP `sessionTimeoutInSeconds` 是独立会话设置。将推荐表述、身份维度注意事项、实测边界和依据写入 [GATEWAY-DESCRIPTION.zh-CN.md](GATEWAY-DESCRIPTION.zh-CN.md)。此次核对未新增云端限流测试。

## 调用者 IAM 修复复测：2026-09-29 01:54–02:00 UTC

用户要求确认 Gateway 调用者 IAM 凭证转发是否修复。执行 `.venv/bin/python run_caller_reproduction.py --results-dir results/repro-caller-confirm-20260929`，01:54:05 开始，02:00:23 完成。使用 `china` profile、账号 `209915754514`，北京、宁夏各建全新 Runtime、两个 Gateway、四个目标及独立 IAM 角色。五个核心脚本与 9 月 28 日运行快照逐字节一致；Python 3.12.13、boto3/botocore 1.43.103 版本未变，详见 [环境及源码哈希](results/repro-caller-confirm-20260929/environment.json)。

复用 setup 的公开 OIDC discovery / token 探测仍返回 403，每区两项失败保留；其不参与 IAM 转发路径，本轮未启动外部 IdP。Gateway 约 3.5 秒就绪，Runtime 分别等待 219.7 秒（北京）、222.9 秒（宁夏）达到 READY，未调整十分钟等待窗口。

01:58–01:59 的功能对照结果发生变化：每区所选八项均 PASS，包含 AssumeRole 直接调用、AWS_IAM 和 AUTHENTICATE_ONLY 两种入站下的 Gateway 角色/调用者转发，以及同一组 GetSessionToken 的直接/角色/调用者三路比较。全部六个所选调用者转发请求均为 HTTP 200、`sum=42`；同凭证五项对照每区全部通过。另有每区两次初始 Runtime 冒烟调用也通过，完整日志共保留 20 次 Runtime 调用观察；专项结果表选择 16 项核心对照，不重复计数。

结论：9 月 28 日的 `The security token included in the request is invalid` 403 在本次三种凭证/入站组合中不再出现，按原问题的复现标准已恢复。没有改写之前的失败记录，也没有据此推断 AWS 内部修复代码、准确部署时间或其他未测试组合。

01:59:27 开始清理，两个区域的 Gateway、Runtime、目标、workload identity、Lambda、API、S3 桶、IAM 角色及本地测试秘密均处理完成；两区独立只读核验 PASS、剩余资源为空。此次不创建 Browser、EC2 或 VPC 安全组。编排退出码 0，`errors=[]`；公开 OIDC 探测失败与 IAM 八项对照结果分开解释。

新增 `export_caller_reproduction.py` 离线导出中文/英文报告、配置、响应 CSV/JSON、原始审计行关联与哈希清单。首次导出因 HTTP 响应头 `x-amzn-RequestId` 的大小写匹配失败；改为不区分大小写后重新导出成功，未新增云端调用。02:03:23 核验 16 项结果、12 条 Gateway HTTP 审计关联及 348 份源码快照哈希通过。独立临时凭证 SDK 客户端没有框架审计，其直接调用结果使用已有响应和请求 ID，不补造未保存的 HTTP 状态。

同步更新中英文主报告、README、补测说明、问题复现文档和两个聚合生成器。主统计保持每区原有 159 个检查名称，调用者转发状态由 FAIL 更新为 PASS，变为 **154 PASS / 1 FAIL / 2 BLOCKED / 2 NOT_AVAILABLE**。新增八项对照不扩大主表分母；Browser 下载与其他能力此次未重测。9 月 28 日调用者专项目录保留不变。

02:05:09 本地交付核验通过：16 项所选对照、6 条调用者路径、20 次实际 Runtime 调用观察一致；两区清理通过，主表状态及历史失败均核对。267 个本地文档链接、379 份专项产物哈希及三个修改后的 Python 文件语法检查通过；26 个非源码文本证据的脱敏复核无新增命中。CSV 使用标准 CRLF，差异空白检查允许该行尾后通过。[交付核验结果](results/caller-retest-delivery-validation-20260929.json)。

[最新中文报告](results/repro-caller-confirm-20260929/REPORT.zh-CN.md) · [English report](results/repro-caller-confirm-20260929/REPORT.md) · [完整控制台](results/repro-caller-confirm-20260929/console.log) · [实际命令](results/repro-caller-confirm-20260929/phase-commands.jsonl) · [响应与请求 ID](results/repro-caller-confirm-20260929/invocation-results.csv) · [证据核验](results/repro-caller-confirm-20260929/validation.json)。

## 主要中英文文档同步：2026-09-29 02:08 UTC

按用户要求，将调用者 IAM 最新结果置于 `SUMMARY.zh-CN.md`、`REPORT.md` 和 README 开头，在中英文主报告加入一致的三种凭证/入站模式对照表，并明确本次清理核验通过。两区均为每区 8/8 专项通过；主统计保持 159 项，统一为 154 PASS、1 FAIL、2 BLOCKED、2 NOT_AVAILABLE。补充旧 OAuth 专项的完整日期，修正复现文档中残留的“两项功能失败”表述；同步英文生成器，重新导出主报告及结构化矩阵。

本轮仅更新文档与本地导出，未调用 AWS。六份文档、176 个本地链接、双语表格和主矩阵核对通过；9 月 28 日与 29 日两个调用者专项目录共 698 个文件的哈希前后一致，历史失败及最新测试证据均未改写。[本轮核验记录](results/main-docs-caller-update-validation-20260929.json)。

## GitHub 发布前核验：2026-09-29

用户要求将当前项目推送到既有公开仓库 `milan9527/agentcore-china-tests`。确认远端 `main` 与本地原始提交一致，待发布内容包括 OAuth、代理专项及调用者 IAM 恢复验证的脚本、源码快照、过程记录和中英文文档。缓存、虚拟环境、依赖目录及生成的私钥/测试秘密由忽略规则排除，GitHub 凭证仅在内存中用于鉴权。

发布检查发现初测两区日志的 elicitation / sampling 结果中共有四处 `requestState` 尚未脱敏。仅替换该续传状态值，保留行号、时间、结果及请求 ID；[脱敏审计](results/github-publication-redaction-20260929.json)记录前后文件哈希。此为分享前脱敏，不改变历史测试结论，也未重写 Git 历史。

## 证据入口

- [初测北京记录](results/cn-north-1-results.jsonl) / [初测宁夏记录](results/cn-northwest-1-results.jsonl)
- [补测北京记录](results/retest/cn-north-1-results.jsonl) / [补测宁夏记录](results/retest/cn-northwest-1-results.jsonl)
- [浏览器对照北京记录](results/retest-browser/cn-north-1-results.jsonl) / [浏览器对照宁夏记录](results/retest-browser/cn-northwest-1-results.jsonl)
- [源码快照清单](results/followup-artifacts.json)
- [完整时间线](results/followup-history.jsonl)
- [清理状态](results/followup-cleanup.json)
