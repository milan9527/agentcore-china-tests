# AgentCore 中国区 Live View 延时测试与结论更正

日期：2026-09-28 UTC；AWS profile：`china`；北京 `cn-north-1`、宁夏 `cn-northwest-1`。

**结论：两地 Live View 画面与人工输入均通过。此前“DCV 显示连接失败”是测试提前退出造成的误判，应予更正。**

原脚本遇到 `probe.errors.length > 0` 就结束。约 2 秒时，鉴权已经成功，`/live-view/auth` WebSocket 关闭回调又报 `Close received after close` / `Failed to communicate with server`。但此时显示连接仍在建立，之后约 3 秒连接成功、约 6–7 秒收到首帧。这个鉴权回调错误不能直接当作显示连接失败。

本次保留官方 `bedrock-agentcore` 0.4.4 组件及默认 300 秒签名配置；每区首次连续观察 300 秒，再用新签名和新的本地页面连接同一个已经运行约 5 分钟的会话，再次观察 300 秒。Browser 会话超时设为 1800 秒。观察期间不会因错误回调提前退出。

## 实测时间与持续接收

时间以每次本地页面加载为起点，单位为秒。WebSocket 帧计数包含协议消息，不等同于视频帧数；它与实际首帧回调、截图及持续变化的远端时钟共同作为显示证据。

| 区域 | 尝试 | 鉴权成功 | 鉴权关闭错误 | 显示连接成功 | 首帧 | 实际观察时长 | 接收字节 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cn-north-1 | 首次 | 1.794 | 2.024 | 3.016 | 6.450 | 300.462 | 413321 |
| cn-north-1 | 新签名重连 | 2.151 | 2.377 | 3.496 | 6.718 | 300.487 | 738497 |
| cn-northwest-1 | 首次 | 1.864 | 2.111 | 3.189 | 6.728 | 300.524 | 373290 |
| cn-northwest-1 | 新签名重连 | 2.172 | 2.429 | 3.599 | 7.514 | 300.540 | 672307 |

两地每次观察期间，Browser 均为 `READY`，后续心跳记录的接收字节持续增加。本次为功能和约十分钟观察，未进行长期运行或负载性能认证。

## 人工输入

首次显示测试按网页内容坐标点击，未计入浏览器工具栏，输入断言失败。Live View 显示整个浏览器窗口；实测窗口外高 719、内容高 632，相差 **87 像素**。将输入框中心坐标加上该偏移后，通过本地 Live View 鼠标和键盘输入文本，再由远端 CDP 只读检查 DOM，两个区域均得到 `dcv-official-input-ok`。

| 区域 | 独立输入对照的首帧时间 | 输入结果 | 截图 |
| --- | ---: | --- | --- |
| cn-north-1 | 6.362 秒 | `dcv-official-input-ok` | [实际画面](results/retest-live-signature/cn-north-1-official-live.png) |
| cn-northwest-1 | 6.959 秒 | `dcv-official-input-ok` | [实际画面](results/retest-live-signature/cn-northwest-1-official-live.png) |

原持续观察用例把显示与固定坐标输入合并成一个断言，因此其历史记录仍为 FAIL；显示部分的 300 秒实测证据完整保留，修正坐标后的输入通过记录独立保存。`retest_live_conclusions.py` 追加明确的显示通过与输入通过结论，不删除旧失败记录。

## 其他试验与边界

- 将 URL 签名有效期改为 900 秒后，两地 `/live-view/auth` 握手返回 403；恢复默认 300 秒签名后鉴权通过。900 秒试验保存在 `results/retest-livewait/`，不用于推断默认配置的显示能力。观察时间与 URL 签名有效期是两个不同参数。
- 原签名对照曾尝试并发连接同一会话的 CDP，返回 429 `Concurrent connections to the same session are not supported`；随后改用独立会话，没有中断正在进行的持续观察。
- 鉴权 WebSocket 关闭错误的内部成因未确认；实测其后显示、持续数据接收和输入正常。
- TypeScript SDK 的 URL 生成器存在中国分区域名问题；本次始终使用服务返回的 `.amazonaws.com.cn` 端点进行 SigV4 签名。

## 复现

依赖安装见 [REPRODUCE.zh-CN.md](REPRODUCE.zh-CN.md)。使用新的结果目录，脚本只启动两地托管 Browser 会话，不创建 Gateway、VPC 或 EC2。

```bash
node retest-viewer/build.mjs
export RETEST_RESULTS_DIR="$PWD/results/liveview-reproduction-01"
LIVE_WAIT_SECONDS=300 LIVE_SIGNATURE_SECONDS=300 \
  .venv/bin/python retest.py retest_live_wait
.venv/bin/python retest.py cleanup_tests
VERIFY_RESULTS_DIR="$RETEST_RESULTS_DIR" .venv/bin/python verify_cleanup.py
.venv/bin/python sanitize_evidence.py "$RETEST_RESULTS_DIR"
```

最终脚本已修正首帧等待和工具栏坐标。实际完整延时实测使用当时的源码快照，其中坐标修正通过独立对照验证；没有为了更改历史状态重新执行全部延时轮次。`retest_browser.py` 的常规检查改为最多等待首帧 120 秒，而不是收到任意错误就退出。

## 证据与清理

- 默认签名持续观察：[北京](results/retest-livewait-default/cn-north-1-results.jsonl)、[宁夏](results/retest-livewait-default/cn-northwest-1-results.jsonl)。
- 逐事件时间线：[北京](results/retest-livewait-default/cn-north-1-live-wait-events.jsonl)、[宁夏](results/retest-livewait-default/cn-northwest-1-live-wait-events.jsonl)。
- 输入及签名对照：[北京](results/retest-live-signature/cn-north-1-results.jsonl)、[宁夏](results/retest-live-signature/cn-northwest-1-results.jsonl)。
- 各目录的 `source-snapshots/` 保存执行时源码、依赖文件和 SHA-256；`*-api-audit.jsonl` 保存框架审计，未保存令牌和 WebSocket 消息内容。
- 本次新建 Browser 会话均已停止；清理结果见 [汇总状态](results/followup-cleanup.json)。之前初测与补测的延迟清理项单独记录。

更新总报告：[FOLLOWUP.zh-CN.md](FOLLOWUP.zh-CN.md)。
