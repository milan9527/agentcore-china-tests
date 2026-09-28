# 当前问题的复现方法

适用结论：2026-09-28，AWS profile `china`，北京 `cn-north-1`、宁夏 `cn-northwest-1`。[当前报告](SUMMARY.zh-CN.md)中仍失败的功能检查是 **Gateway 调用者 IAM 转发**与 **Browser `download.save_as()` 文件取回**。Live View 已通过，不属于当前失败项目。

以下命令使用现有分阶段脚本，相关阶段已在两地实测。调用者 IAM 专用编排最近一轮的从空环境实测记录见第 1 节，其他阶段的验证范围见各自报告。每段默认同时测试两个区域，并创建收费的临时资源。已有历史资源、会话和临时 URL 均已删除或过期，应使用新结果目录。

## 共同准备

在本工作区已安装的环境中执行：

```bash
cd /home/ec2-user/agentcore/cn
unset RETEST_STATE_READ_ONLY
unset PYTHONPATH
```

其他机器先按[完整依赖安装说明](REPRODUCE.zh-CN.md#环境与依赖)安装锁定版本。IAM 用例只需要 Python 依赖；下面复用的浏览器阶段也会检查 Live View，因此需要前端依赖和本地 Chromium。`china` profile 的权限要求见[完整说明](REPRODUCE.zh-CN.md#aws-前提)。

各阶段命令可加 `--region cn-north-1` 或 `--region cn-northwest-1`；下文的批量清理核验默认读取两个区域状态，建议直接按两地命令执行。相同结果目录的写状态阶段必须串行运行。不要通过 `RETEST_STATE_READ_ONLY=1` 启动需要记录新资源的阶段。

## 1. Gateway 调用者 IAM 转发

2026-09-28 **07:48–07:54 UTC** 已在两地新环境再次复现，包含资源创建、AssumeRole / GetSessionToken 对照和完整清理。每区 5 项成功对照、3 项调用者转发 403，清理核验均通过。[本次报告](results/repro-caller-confirm-20260928/REPORT.zh-CN.md)、[完整运行输出](results/repro-caller-confirm-20260928/console.log)、[逐项响应及请求 ID](results/repro-caller-confirm-20260928/invocation-results.csv)。

可用以下专用编排重新执行并实时打印脱敏过程与结果，必须指定一个新的空目录：

```bash
.venv/bin/python run_caller_reproduction.py --results-dir results/repro-caller-next
```

该专用编排已在本次从空目录实测，退出码 2 表示复现出调用者转发问题，退出码 1 表示执行、判定或清理异常。完整功能编排 `run_followup.py` 的验证范围另见后文。

### 执行命令

```bash
export RETEST_RESULTS_DIR="$(mktemp -d "$PWD/results/repro-caller-XXXXXX")"

.venv/bin/python retest.py retest_setup
.venv/bin/python retest.py retest_runtime
.venv/bin/python retest.py caller_baseline_tests
```

这里复用 `retest_setup` 创建角色、桶、Lambda 和 API 测试环境，然后 `retest_runtime` 创建 HTTP Runtime、Gateway 和目标。不需要启动 cloudflared/OIDC 隧道。`retest_setup` 的公开 OIDC 探测可能记录 403；该探测不参与 IAM 转发，但后续需要的角色、桶和 Runtime 必须创建成功。

`GetSessionToken` 对照要求来源凭证适用该操作；若换用已是 AssumeRole 的临时凭证，可能无法再次调用 `GetSessionToken`，这属于前提失败，不能当作复现了 Gateway 转发问题。

### 实际请求与判定

脚本对同一 HTTP Runtime 创建两个目标，其他配置保持一致：

```python
targetConfiguration = {
    "http": {
        "agentcoreRuntime": {
            "arn": "<本次创建的 Runtime ARN>",
            "qualifier": "DEFAULT"
        }
    }
}

# 两个目标分别使用以下 credentialProviderConfigurations：
[{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
[{"credentialProviderType": "CALLER_IAM_CREDENTIALS"}]
```

请求使用 `bedrock-agentcore` 服务名、当前区域做 SigV4 签名，并携带 `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`：

```text
POST <Gateway 基础 URL>/runtime-caller/invocations
Content-Type: application/json

{"a":20,"b":22}
```

只有下面的对照组合同时成立，才符合本次报告中的复现条件：

| 路径 | 预期实测结果 |
| --- | --- |
| 相同凭证直接调用 Runtime | 成功，`sum=42` |
| 相同凭证调用 `GATEWAY_IAM_ROLE` 目标 | HTTP 200，`sum=42` |
| 相同凭证调用 `CALLER_IAM_CREDENTIALS` 目标 | HTTP 403，包含 `The security token included in the request is invalid` |

`retest_runtime` 包含 AssumeRole 凭证和 `AWS_IAM` / `AUTHENTICATE_ONLY` 两种入站模式；`caller_baseline_tests` 补充同一组 GetSessionToken 凭证下的直接调用、执行角色转发和调用者转发三路比较。

重点检查的 `feature`：

- `gateway.caller_iam.assumed_role.direct`：PASS。
- `gateway.caller_iam.AWS_IAM.runtime-role`、`gateway.caller_iam.AUTHENTICATE_ONLY.runtime-role`：PASS。
- `gateway.caller_iam.AWS_IAM.runtime-caller`、`gateway.caller_iam.AUTHENTICATE_ONLY.runtime-caller`：FAIL，403 无效安全令牌。
- `gateway.outbound.caller_iam.direct_runtime_baseline`、`gateway.outbound.caller_iam.gateway_role_baseline`：PASS。
- `gateway.outbound.caller_iam`：FAIL，403 无效安全令牌。

若直接调用或执行角色对照也失败，先排查资源是否就绪、凭证、IAM 权限及传播时间。不能仅凭一个 403 推断为同一问题。可用替代方案是执行角色出站，但权限语义与转发原调用者不同。

历史证据：[北京](results/retest/cn-north-1-results.jsonl)、[宁夏](results/retest/cn-northwest-1-results.jsonl)。原 GetSessionToken 三路基线还记录于[初测北京](results/cn-north-1-results.jsonl)、[初测宁夏](results/cn-northwest-1-results.jsonl)。执行后运行本文“清理”命令，再开始其他独立场景。

## 2. Browser 下载到客户端为零字节

### 执行命令

无需 `retest_setup`、Gateway、Runtime 或测试 IdP。使用已安装的依赖：

```bash
node retest-viewer/build.mjs
export RETEST_RESULTS_DIR="$(mktemp -d "$PWD/results/repro-download-XXXXXX")"

.venv/bin/python retest.py retest_browser

PYTHONPATH="$PWD/retest-pw148" \
  .venv/bin/python retest.py retest_browser_deep

.venv/bin/python retest.py retest_download_binary
```

第一阶段使用 Playwright 1.63.0，测试默认上下文、新上下文及本地 Chromium 对照。第二阶段使用安装在 `retest-pw148/` 的 Playwright 1.60.0，诊断远端文件路径并验证 CDP 取回。第三阶段验证可复用助手的文本和二进制结果。前两个阶段还会执行已修正的 Live View 检查，其结果与下载检查分开记录。

### 最小触发操作

以下是已通过 SigV4 连接远端 Browser 后的关键代码；完整会话创建、连接及清理由上面的阶段脚本处理：

```python
page.set_content(
    '<a id="download" download="retest.txt" '
    'href="data:text/plain,agentcore-download-ok">Download</a>'
)
with page.expect_download() as pending:
    page.locator("#download").click()
download = pending.value
download.save_as("retest.txt")
```

### 判定条件

| 检查 | 预期实测结果 |
| --- | --- |
| `browser.download.save_as.default` / `.new` | FAIL：本地文件为 0 字节，期望为 21 字节 |
| `browser.download.compatible_playwright` | FAIL：Playwright 1.60.0 仍是 0 字节 |
| `browser.download.artifact_diagnostics` | `downloadFailure=null`、`localArtifactExists=false`、`savedBytes=0`，但 `remoteArtifactContent` 为 `agentcore-download-ok` |
| `browser.download.local_baseline` | PASS：本地 Chromium 保存 21 字节 |
| `browser.download.cdp_file_retrieval` | PASS：CDP 从远端取回 21 字节 |
| `browser.download.remote_file_retrieval.text.txt` / `.binary.bin` | PASS：文本 21 字节、二进制 8192 字节，逐字节相同及 SHA-256 校验成功 |

因此复现的是该 CDP 连接方式下的**远端文件取回失败**，不是远端浏览器没有下载成功。不要把通用下载错误、浏览器启动失败或磁盘权限错误视为相同复现。

可用替代实现为 [download_remote_file.py](download_remote_file.py)：将已知的远端下载路径交给 `read_remote_file(context, remote_path)`，得到字节后写入客户端文件。它利用 `DOM.setFileInputFiles` 和 `File.arrayBuffer()`，不依赖客户端能访问远端路径。

历史证据：[1.63 北京](results/retest/cn-north-1-results.jsonl)、[1.63 宁夏](results/retest/cn-northwest-1-results.jsonl)、[1.60 与二进制北京](results/retest-browser/cn-north-1-results.jsonl)、[1.60 与二进制宁夏](results/retest-browser/cn-northwest-1-results.jsonl)。执行后运行下一节清理。

## 查看记录及清理

每次执行后，实际结果位于当前 `$RETEST_RESULTS_DIR`：

- `cn-north-1-results.jsonl` / `cn-northwest-1-results.jsonl`：逐项状态、时间、响应及异常。
- `*-api-audit.jsonl`：已注册 SDK 客户端和 HTTP 请求审计，敏感值脱敏。
- `source-snapshots/`：该阶段源码、环境参数及 SHA-256。
- `*-state.json`：该目录创建的资源及会话，用于清理。

可用以下命令只显示关注项目的最新状态：

```bash
.venv/bin/python - <<'PY'
import json, os
from pathlib import Path
folder = Path(os.environ["RETEST_RESULTS_DIR"])
for path in sorted(folder.glob("*-results.jsonl")):
    latest = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        latest[row["feature"]] = row
    for feature, row in sorted(latest.items()):
        if "caller_iam" in feature or feature.startswith("browser.download."):
            print(row["region"], row["status"], feature, row["time"])
PY
```

**阶段包装器 PASS 或进程退出码 0 不代表全部检查通过**，应查看具体 `feature` 和证据。完成每个独立场景后，在更换 `$RETEST_RESULTS_DIR` 前执行：

```bash
CLEANUP_SG_WAIT_SECONDS=20 .venv/bin/python retest.py cleanup_tests
.venv/bin/python retest.py retest_cleanup_local
VERIFY_RESULTS_DIR="$RETEST_RESULTS_DIR" .venv/bin/python verify_cleanup.py
.venv/bin/python sanitize_evidence.py "$RETEST_RESULTS_DIR"
```

即使中途异常也应执行清理。前两个问题的步骤不会创建 VPC 安全组或 EC2，因此通常不需要等待 AgentCore ENI 释放。确认 `cleanup.browser_sessions`、`cleanup.inventory` 和只读核验结果后保留日志。不可复用已清理目录继续功能测试。

## 账号限制与代理配置边界

这些项目与上面的两项功能失败分开解释。各场景使用新结果目录，并在结束后按上一节清理：

| 项目 | 在新目录内依次执行的阶段 | 预期证据 / 判定 |
| --- | --- | --- |
| Token Exchange | `retest_setup` → `retest_tunnels` → `retest_gateway` | `gateway.outbound.oauth_token_exchange` 为 BLOCKED；提供商已可用，但目标创建明确返回 `Token Exchange is not available for this account` |
| Gateway 私有目标 | `retest_setup` → `retest_proxy` | `gateway.private_target` 明确返回 `Private endpoint configuration requires VPC egress feature to be enabled for this account.` |
| Gateway / Browser PrivateLink | 单独执行 `retest_availability` | 两项 `*.private_link` 为 NOT_AVAILABLE；分页服务目录的 `advertisedServices=[]` |
| 代理非标准端口与上游 DNS | `retest_setup` → `retest_proxy` → `retest_proxy_ports` | 8000/8443 失败；未显式配置域名的上游专用 DNS 返回 503；80/443、显式域名及独立 bypass 对照通过 |

表中的阶段名均使用 `.venv/bin/python retest.py <阶段名>` 执行。Token Exchange 还需要[cloudflared 安装与网络前提](REPRODUCE.zh-CN.md#环境与依赖)。私有目标与代理阶段使用默认 VPC 子网并创建临时 EC2、Secret、Browser 和安全组，清理后若安全组仍被服务 ENI 引用，再执行：

```bash
DEFERRED_RESULTS_DIR="$RETEST_RESULTS_DIR" .venv/bin/python deferred_cleanup.py
```

该进程有界重试，最多 8.5 小时，不强制分离 AWS 管理接口。服务拒绝消息和目录结果仅代表测试时当前账号与区域；若账号开通功能后结果变化，应按新证据更新结论。

如需把全部补测流程一起运行，可按[完整复现说明](REPRODUCE.zh-CN.md)执行 `run_followup.py`。各阶段已经实测，但该完整编排尚未从空环境再次完成一整轮云端验证。
