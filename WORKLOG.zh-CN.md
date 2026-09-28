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

## 证据入口

- [初测北京记录](results/cn-north-1-results.jsonl) / [初测宁夏记录](results/cn-northwest-1-results.jsonl)
- [补测北京记录](results/retest/cn-north-1-results.jsonl) / [补测宁夏记录](results/retest/cn-northwest-1-results.jsonl)
- [浏览器对照北京记录](results/retest-browser/cn-north-1-results.jsonl) / [浏览器对照宁夏记录](results/retest-browser/cn-northwest-1-results.jsonl)
- [源码快照清单](results/followup-artifacts.json)
- [完整时间线](results/followup-history.jsonl)
- [清理状态](results/followup-cleanup.json)
