# AgentCore 中国区补测复现说明

结论见 [FOLLOWUP.zh-CN.md](FOLLOWUP.zh-CN.md)。Live View 后续更正与专门复现命令见 [LIVEVIEW.zh-CN.md](LIVEVIEW.zh-CN.md)。以下命令使用 AWS `china` profile，各阶段在北京与宁夏并行执行。会创建收费的临时 AWS 资源，并在测试后清理。

专项回归与问题复现见[调用者 IAM 与零字节下载的步骤](REPRODUCE-ISSUES.zh-CN.md)，包含最短阶段依赖、历史错误、成功对照和清理命令。调用者 IAM 于 2026-09-29 在两区复测通过，零字节下载保留此前失败结论。

## 环境与依赖

本次实际环境为 Linux x86_64、Python 3.12.13、Node.js 23.1.0、boto3/botocore 1.43.103。正常浏览器测试使用 Playwright 1.63.0；兼容性对照使用 1.60.0。远端 Chromium 为 148.0.7778.258，本地无界面 Chromium 为 153.0.8010.12。

Python 完整依赖锁定在 [requirements-followup.lock.txt](requirements-followup.lock.txt)，兼容性对照依赖见 [requirements-pw148.lock.txt](requirements-pw148.lock.txt)；前端依赖锁定在 [package-lock.json](retest-viewer/package-lock.json)。使用锁文件，避免自动升级改变复现条件。

```bash
cd /home/ec2-user/agentcore/cn
python3 -m venv .venv
.venv/bin/pip install -r requirements-followup.lock.txt
.venv/bin/playwright install chromium
.venv/bin/pip install --target retest-pw148 -r requirements-pw148.lock.txt
npm ci --prefix retest-viewer --ignore-scripts --no-audit --no-fund
node retest-viewer/build.mjs
```

本次使用 Playwright 的 headless shell；完整 Chrome 二进制在当前主机缺少 `libcups.so.2`。测试会优先寻找已安装的 headless shell。其他平台可设置 `LOCAL_CHROMIUM_EXECUTABLE` 指向可运行的本地 Chromium；平台可移植性未单独认证。

合成 OIDC 提供商使用 cloudflared `2026.9.3`。复现时需要访问 GitHub、npm/PyPI、Cloudflare HTTPS 隧道及两个中国区域：

```bash
mkdir -p results/retest
curl -fL \
  https://github.com/cloudflare/cloudflared/releases/download/2026.9.3/cloudflared-linux-amd64 \
  -o results/retest/cloudflared
chmod +x results/retest/cloudflared
sha256sum results/retest/cloudflared
```

本次二进制 SHA-256：

```text
77e26d8d900e0b8469f416239d14b5f296525fdf79fee6f511ef55609e3fbac2
```

## AWS 前提

`china` profile 必须能访问测试账号，且有权限创建与删除测试用的 IAM 角色、Gateway、Browser、Runtime、Identity 凭证提供商、Lambda、API Gateway、S3、Secrets Manager、EC2 实例与安全组，并读取日志和端点服务目录。调用者 IAM 对照还需要 `sts:GetSessionToken`、`sts:AssumeRole`。

网络测试使用账号中已有的默认 VPC 子网，创建仅允许测试安全组内部通信的测试实例。脚本不会创建或修改生产身份。合成 IdP 仅签发测试 JWT；临时 HTTPS 隧道不承载 AWS 凭证。

Token Exchange 与 Gateway VPC egress 的账号开关，以及 PrivateLink 服务可见性，不属于一般 IAM 权限。未开通时应复现报告中的拒绝或不可用结果。

## 一键编排

必须指定一个新的结果目录；脚本拒绝复用含区域状态文件的目录：

```bash
.venv/bin/python run_followup.py --results-dir results/reproduction-01
```

该编排串联下述已执行的阶段，保存每阶段 stdout、命令、源码快照及结果，然后清理资源并脱敏。存在预期复现的失败检查时，最终退出码为 2；阶段异常或收尾异常返回 1。需要查看具体检查及 `run-summary.json`，不能仅看阶段包装器是否通过。

**验证范围：各阶段和关键复现路径已在两地实测；新增的一键编排已进行语法和命令校验，未再次创建第三套完整资源从零执行。** 本次采用的实际执行顺序及中间修正记录见 [WORKLOG.zh-CN.md](WORKLOG.zh-CN.md)。服务端状态、临时域名、请求 ID 和资源 ID 在复现时会变化。

一键编排另经本地模拟验证：预期功能失败返回 2；阶段异常返回 1，仍执行云端与本地清理步骤。该模拟未访问 AWS，不计入功能实测结果。

## 按阶段执行

如果需要逐步观察，使用一个新的结果目录。相同目录的写状态阶段应串行执行：

```bash
export RETEST_RESULTS_DIR="$PWD/results/reproduction-manual-01"

.venv/bin/python retest.py retest_setup
.venv/bin/python retest.py retest_tunnels
.venv/bin/python retest.py retest_gateway
.venv/bin/python retest.py retest_authcode
.venv/bin/python retest.py retest_runtime
.venv/bin/python retest.py retest_proxy
.venv/bin/python retest.py retest_proxy_ports
.venv/bin/python retest.py retest_browser

PYTHONPATH="$PWD/retest-pw148" \
  .venv/bin/python retest.py retest_browser_deep

.venv/bin/python retest.py retest_download_binary
.venv/bin/python retest.py retest_availability
.venv/bin/python retest.py retest_conclusions
```

每个命令可追加 `--region cn-north-1` 或 `--region cn-northwest-1`。`retest_setup` 中的中国区 API Gateway 公开接口探测可能返回 403；后续 `retest_tunnels` 提供独立的 HTTPS IdP。继续鉴权测试前，应确认 `fixture.oidc.public_discovery` 与 `fixture.oidc.client_credentials` 的最新结果通过。

| 阶段 | 实际动作 | 预期 / 应检查内容 |
| --- | --- | --- |
| `retest_setup` | 创建测试角色、桶、Lambda、API；生成合成签名密钥 | 资源状态完整；公开 API 可记录账号环境限制 |
| `retest_tunnels` | 启动本地合成 IdP 与临时 HTTPS 隧道 | 发现文档可访问，RS256 令牌及受保护后端正常 |
| `retest_gateway` | JWT 正负例、令牌透传、client credentials、Token Exchange 目标、授权码目标配置 | 前三类通过；Token Exchange 复现明确账号拒绝 |
| `retest_authcode` | URL elicitation、保留 Cookie 的回调、会话绑定、恢复工具调用 | 最终 `resultType=complete`，后端 grant 为 `authorization_code` |
| `retest_runtime` | 同一 Runtime 的直接调用与两种出站身份对照；两种入站模式 | 9 月 29 日直接、Gateway 角色及 caller-IAM 全部通过；历史 403 保留 |
| `retest_proxy` | 私有 TLS/代理基线；默认、鉴权、显式域名、非标准端口、私有目标探测 | 外部代理基线正常；保留非标准端口失败；私有目标账号限制 |
| `retest_proxy_ports` | 标准 80/443、Basic/无鉴权、显式域名、独立绕过、服务端日志 | 正常组合通过；默认代理处理上游专用域名返回 DNS 503 |
| `retest_browser` | 默认/新上下文下载、本地基线、AWS 官方 Live View | 远端 `save_as()` 零字节，本地正常；修正提前结束条件及工具栏坐标后，DCV 画面与输入通过 |
| `retest_browser_deep` | Playwright 1.60 对照、远端文件路径检查、CDP 取回、官方 Live View | 同版本系列仍复现 `save_as()`；CDP 取回成功；Live View 共用已修正的等待逻辑 |
| `retest_download_binary` | 用可复用助手取回文本和二进制 | 21 字节文本与 8192 字节二进制均逐字节一致 |
| `retest_availability` | 分页读取 PrivateLink 服务目录、查询 Token Exchange 提供商 | AgentCore 服务名称为空；提供商配置可存在，目标仍受账号开关限制 |
| `retest_conclusions` | 引用具体配置的实测记录生成原检查名称的结论 | 保留历史失败；代理通过结论明确附带已验证端口与域名条件 |

`retest_proxy_ports` 在本次排查中替换了测试 EC2 实例，以补充 80/443 监听；它只终止当前结果目录记录的测试实例，保留固定私有 ENI 地址并更新测试 CA。

## 清理

手动执行各阶段时，最后运行：

```bash
CLEANUP_SG_WAIT_SECONDS=20 .venv/bin/python retest.py cleanup_tests
.venv/bin/python retest.py retest_cleanup_local
VERIFY_RESULTS_DIR="$RETEST_RESULTS_DIR" .venv/bin/python verify_cleanup.py
.venv/bin/python sanitize_evidence.py "$RETEST_RESULTS_DIR"
DEFERRED_RESULTS_DIR="$RETEST_RESULTS_DIR" .venv/bin/python deferred_cleanup.py
```

最后一个命令会等待 AWS 释放 AgentCore ENI，最长 8.5 小时，只重试本次记录的安全组，不强制分离 AWS 服务接口。可由终端进程管理器放入后台运行；中断后可重新执行清理。

清理后生成的 IdP 私钥和 client secret 会被删除，隧道关闭，历史 URL 与资源不能直接重用。要再次运行功能测试，创建新的结果目录。初测的两把 KMS 密钥有七天删除等待期，补测没有新增 KMS 密钥。

## 如何检查结果与源码版本

- `*-results.jsonl`：检查时间、区域、feature、状态、证据、耗时；失败通常包含异常和 traceback。
- `*-api-audit.jsonl`：补充的 AWS API 与 HTTP 请求审计，含配置、响应、请求 ID；敏感值脱敏。
- `source-snapshots/<UTC时间>-<阶段>/manifest.json`：该阶段源码 SHA-256、执行环境参数，以及当时的源码副本。
- `phase-commands.jsonl`、`phase-*.log`：一键编排生成的命令与控制台日志。
- `*-state.json`：仅记录本次创建资源、会话及清理状态；不是可以跨运行直接复用的配置文件。
- `*-cleanup-verification.json`：独立只读删除验证，包含 EC2 实例、EBS 卷及网络接口检查。
- `redaction-report.json`：脱敏时间、修改文件及修改前后 SHA-256；JSONL 的时间、区域、检查名称、状态和耗时保持不变。

检查某个用例时，以最新一次结果判断当前配置；需要解释失败原因时，按时间查看此前记录和对应源码快照。阶段包装器采用“记录单项失败并继续”的方式，包装器 PASS 不代表内部全部检查 PASS。

初测与补测早期已有逐项结果和脚本，但未为所有历史调用保存完整 HTTP 请求。用户要求完整过程记录后增加了逐请求审计和逐阶段源码快照；没有补写或伪造此前不存在的请求日志。

API 审计覆盖测试框架注册的 boto3 客户端及测试线程中的 `requests` 调用；独立创建的客户端、初始化调用和 CDP / DCV 的每条协议消息并非全部原样保存。它与逐项断言结果、客户端观察记录和源码共同构成复现证据，不等同于完整网络抓包。

本次初测及补测目录的汇总可在本地重新生成，不调用 AWS：

```bash
.venv/bin/python export_report.py
.venv/bin/python build_followup_evidence.py
```

`export_report.py` 生成当前英文报告、`final-results.json` 和 `feature-matrix.csv`，保持初测每区 159 个检查名称并合并对应补测结果。同时生成 `initial-results.json` 和 `initial-feature-matrix.csv`，保留初测统计。中文摘要采用同一口径；初测中英文 Markdown 归档为 `SUMMARY.initial.zh-CN.md` 与 `REPORT.initial.md`。

`build_followup_evidence.py` 固定读取本次的 `results/`、`results/retest/`、`results/retest-browser/`，后续 Live View 的 `retest-livewait`、`retest-live-signature`、`retest-livewait-default` 三个子目录，以及调用者 IAM 的 `repro-caller-confirm-20260928`、`repro-caller-confirm-20260929`。其他新复现目录不会自动混入本次历史证据；`run_followup.py` 将结果写入该目录的 `latest-results.json` / `run-summary.json`，调用者 IAM 专用 `run_caller_reproduction.py` 则生成 `summary.json` / `REPORT.zh-CN.md` 并保存完整控制台输出。使用 `export_caller_reproduction.py --results-dir <目录>` 可离线生成双语报告、CSV、JSON 与哈希清单。
