"""Export proxy observations and verification indexes without calling AWS."""
import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REGIONS = ("cn-north-1", "cn-northwest-1")


def export(output):
    result = {"generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "regions": {}}
    records = []
    latest = {}
    for region in REGIONS:
        observations = json.loads((output/f"{region}-observations.json").read_text())
        rows_path = output/f"{region}-results.jsonl"
        rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
        row_index = {(row["feature"], row["evidence"]["marker"]): (i, row)
            for i, row in enumerate(rows, 1) if row["feature"].startswith("proxy.case.")}
        origin_log = json.loads((output/f"{region}-origin-access.json").read_text())
        proxy_log = json.loads((output/f"{region}-proxy-access.json").read_text())
        origin_by_seq = {row["seq"]: row for row in origin_log}
        proxy_by_seq = {row["seq"]: row for row in proxy_log}
        for observation in observations:
            line, raw = row_index[(observation["feature"], observation["marker"])]
            assert raw["status"] == observation["status"]
            assert all(raw["evidence"][key] == value for key, value in observation.items()
                       if key not in ("region", "feature", "status"))
            for item in observation["originEvents"]:
                assert origin_by_seq[item["seq"]] == item
            for item in observation["proxyEvents"]:
                assert proxy_by_seq[item["seq"]] == item
            record = {**observation, "source": rows_path.name, "sourceLine": line}
            records.append(record)
            latest[(region, observation["feature"])] = record
        diagnostics = [r for r in rows if r["feature"] == "proxy.diagnostic.squid_config"]
        environment = next(r["evidence"] for r in rows if r["feature"] == "proxy.validation.environment")
        cleanup_path = output/f"{region}-cleanup-verification.json"
        checks = [v for (r, _), v in latest.items() if r == region]
        result["regions"][region] = {
            "attempts": len(observations), "uniqueChecks": len(checks),
            "counts": dict(Counter(x["status"] for x in checks)),
            "environment": environment, "squidDiagnostic": diagnostics[-1]["evidence"] if diagnostics else None,
            "cleanup": json.loads(cleanup_path.read_text()) if cleanup_path.exists() else {"status": "NOT_RECORDED"},
        }
    result["checks"] = list(latest.values())
    (output/"final-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    fields = ["region", "label", "scheme", "port", "host", "attempt", "status", "httpStatus",
              "expectedRoute", "actualRoute", "externalProxyContacted", "originReached",
              "sessionId", "marker", "source", "sourceLine"]
    with (output/"attempts.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    labels = list(dict.fromkeys(r["label"] for r in records))
    ports = [("http",80),("http",8000),("http",8081),("https",443),("https",8443)]
    for chinese in (True, False):
        def t(zh,en):
            return zh if chinese else en
        lines = [t("# Browser 代理专项验证：端口、认证、路由与绕过",
                   "# Browser proxy validation: ports, authentication, routing, and bypass"), "",
            t("使用 AWS profile `china`，账号 `209915754514`，分别在北京与宁夏实测。"
              "本报告从保存的逐项观察及两端日志生成，不调用 AWS。",
              "Live tests use AWS profile china, account 209915754514, in Beijing and Ningxia. "
              "This report is generated from saved observations and endpoint logs without AWS calls."), "",
            t("## 环境与断言", "## Environment and assertions"), "",
            t("每区使用两个无公网地址的 EC2：独立的目标服务和 Python 外部代理，处于同一测试安全组。"
              "目标监听 HTTP 80/8000/8081 和 HTTPS 443/8443；代理监听 3128/8080（Basic）和 3129（无认证）。"
              "HTTP 请求实际转发到目标，HTTPS 通过 CONNECT 隧道。证书包含目标 IP 和测试主机名，正常 TLS 测试不忽略证书错误。",
              "Each region uses two EC2 instances without public addresses: a separate origin and Python external proxy in the test security group. "
              "The origin listens on HTTP 80/8000/8081 and HTTPS 443/8443. Proxy listeners are 3128/8080 (Basic) and 3129 (no authentication). "
              "HTTP is actually forwarded to the origin; HTTPS uses CONNECT. Certificates cover the origin IP and test hostnames, with certificate verification enabled."),
            "",
            t("每次请求携带唯一 `/probe/<marker>` 路径，关联 Browser 结果与目标日志；目标看到代理 IP 才计为经代理到达。"
              "代理成功同时要求相应监听端口的认证/CONNECT 记录。绕过成功要求目标记录来源不是代理 IP，且对应窗口没有外部代理请求。"
              "错误/缺失凭证检查要求目标未收到请求，且外部代理记录认证拒绝。失败请求在相同配置下重复一次，历史结果保留。",
              "Each request carries a unique /probe/<marker> path linking Browser results with origin logs. Proxy routing requires the origin to observe the proxy IP plus corresponding listener authentication/CONNECT evidence. "
              "Bypass requires a non-proxy origin peer and no matching external-proxy request in the observation window. "
              "Wrong/missing credential controls require no origin request and an external-proxy authentication rejection. Failed checks repeat once with both attempts retained."), "",
            t("| 区域 | 目标 IP | 代理 IP | 唯一检查 | 尝试数 | 最后结果 |",
              "| Region | Origin IP | Proxy IP | Unique checks | Attempts | Latest verdicts |"),
            "| --- | --- | --- | ---: | ---: | --- |"]
        for region, value in result["regions"].items():
            env = value["environment"]
            lines.append(f"| {region} | {env['originIp']} | {env['proxyIp']} | {value['uniqueChecks']} | "
                         f"{value['attempts']} | {json.dumps(value['counts'])} |")
        lines += ["", t("## 逐项矩阵", "## Check matrix"), "",
            t("单元格为北京 / 宁夏；`—` 表示该场景没有安排此端口。PASS 指该行断言通过，认证拒绝/证书拒绝对照的 PASS 表示预期拒绝发生。",
              "Cells show Beijing / Ningxia; — means that port was not selected for the scenario. PASS refers to the stated assertion; negative authentication/certificate controls pass when rejection is verified."), "",
            "| Scenario | HTTP 80 | HTTP 8000 | HTTP 8081 | HTTPS 443 | HTTPS 8443 |",
            "| --- | --- | --- | --- | --- | --- |"]
        for label in labels:
            cells = []
            for scheme, port in ports:
                values = [latest.get((region,f"proxy.case.{label}.{scheme}_{port}")) for region in REGIONS]
                cells.append(" / ".join(v["status"] if v else "—" for v in values))
            lines.append("| "+label+" | "+" | ".join(cells)+" |")
        lines += ["", t("`direct-*`：无外部代理；`playwright-proxy-*`：新 Playwright 上下文直接指定外部代理；"
                        "`managed-*`：StartBrowserSession 的 proxyConfiguration；`explicit`：显式域名规则；"
                        "`bypass-*`：精确 IP/主机名/后缀绕过；`multi-*`：指定域名代理与默认代理选择。",
                        "direct-* uses no external proxy; playwright-proxy-* sets the external proxy directly on a new Playwright context; "
                        "managed-* uses StartBrowserSession proxyConfiguration; explicit adds domain patterns; "
                        "bypass-* checks exact IP/hostname/suffix bypass; multi-* checks specific and default proxy selection."),
            "", t("## 未通过请求的定位", "## Failed-request localization"), "",
            t("| 区域 | 场景 | URL | 结果 | 外部代理收到 | 目标收到 | 结果行 |",
              "| Region | Scenario | URL | Result | External proxy contacted | Origin reached | Result line |"),
            "| --- | --- | --- | --- | --- | --- | --- |"]
        for row in latest.values():
            if row["status"] != "FAIL":
                continue
            error = str(row.get("httpStatus") or row.get("error","")).replace("\n"," ")[:100]
            lines.append(f"| {row['region']} | {row['label']} | `{row['scheme']}://{row['host']}:{row['port']}` | "
                f"{error} | {row['externalProxyContacted']} | {row['originReached']} | "
                f"[{row['sourceLine']}]({row['source']}) |")
        lines += ["", t("“外部代理未收到且目标未收到”把问题定位在到达测试外部代理之前，但不能单独证明具体 Squid ACL。"
                        "没有读取到服务配置时，仅依据错误页和端口对照限定结论，不宣称 AWS 内部根因。",
                        "No external-proxy or origin event localizes a request failure before the external fixture, but alone does not establish a specific Squid ACL. "
                        "Without readable service configuration, conclusions are limited to error pages and port controls, not a confirmed AWS internal root cause."),
            "", t("## Squid 只读诊断", "## Read-only Squid diagnostics"), ""]
        for region,value in result["regions"].items():
            lines += [f"### {region}", "", "```json",
                      json.dumps(value["squidDiagnostic"],ensure_ascii=False,indent=2),"```",""]
        lines += [t("仅尝试读取 `/etc/squid/squid.conf`，保存 port/method ACL、http_access、always_direct/never_direct 等允许列出的非凭证行及文件哈希；未保存原始配置，未修改服务配置。",
                   "Only /etc/squid/squid.conf was probed. Saved fields are allow-listed non-credential port/method ACLs, http_access, always_direct/never_direct, and a hash. Raw configuration was not saved and service configuration was not modified."),
            "", t("## 复现与证据", "## Reproduction and evidence"), "", "```bash",
            "python3 -m venv .venv", ".venv/bin/pip install -r requirements-followup.lock.txt",
            ".venv/bin/python run_proxy_validation.py --results-dir results/proxy-reproduction-new",
            ".venv/bin/python export_proxy_validation.py --results-dir results/proxy-reproduction-new", "```", "",
            t("使用新的空目录。需要默认 VPC 子网以及创建/删除 IAM、EC2/ENI/安全组、Secret、AgentCore Browser 的权限。"
              "会创建收费测试资源；编排最后清理本轮清单。运行器退出 0 仅表示阶段完成，逐项通过/失败以本报告和 JSON 为准。",
              "Use a new empty directory. A default VPC subnet and permissions for test IAM, EC2/ENIs/security groups, Secrets, and AgentCore Browser are required. "
              "The runner creates billable test resources and cleans its inventory afterward. Runner exit 0 means phases completed; individual verdicts come from this report and JSON."), "",
            "- [console.log](console.log) · [phase-commands.jsonl](phase-commands.jsonl) · [environment.json](environment.json)",
            "- [attempts.csv](attempts.csv) · [final-results.json](final-results.json) · [run-summary.json](run-summary.json)",
            "- [validation.json](validation.json) · [artifacts.json](artifacts.json) · [source-snapshots/](source-snapshots/)",
            "", t("各区域 `*-proxy-access.json`、`*-origin-access.json` 保存服务端日志；`*-api-audit.jsonl` 保存 SDK 请求/响应及 AWS 请求 ID。"
                   "每个导航请求的 sessionId、marker、响应头、错误、来源 IP 和日志序号保存在 `*-observations.json`。",
                   "Regional *-proxy-access.json and *-origin-access.json retain server logs. *-api-audit.jsonl retains SDK requests/responses and AWS request IDs. "
                   "Each navigation's sessionId, marker, response headers, errors, peer IP, and log sequence numbers are in *-observations.json."),
            "", t("## 清理状态", "## Cleanup status"), ""]
        for region,value in result["regions"].items():
            cleanup = value["cleanup"]
            remaining = [c for c in cleanup.get("evidence",[]) if not c.get("ok")]
            lines += [f"- {region}: {cleanup['status']}", "", "```json",
                      json.dumps(remaining,ensure_ascii=False,indent=2),"```",""]
        lines += [t("如安全组等待 AWS 托管 ENI 释放，运行器启动最多 8.5 小时的后台重试，见 deferred-cleanup.json。"
                   "本报告记录导出时的清理状态，后续后台状态以该文件为准；不会强制分离 AWS 托管接口。",
                   "If security groups await AWS-managed ENI release, a background worker retries for up to 8.5 hours; see deferred-cleanup.json. "
                   "This report records cleanup at export time; later worker state is authoritative. AWS-managed interfaces are not forcibly detached."),
            "", t("## 与此前报告的关系", "## Relationship to previous reports"), "",
            t("09:54 的首次准备尝试因默认子网自动分配公网地址而停止并清理，未进入 Browser 功能测试，记录见相邻目录 `../proxy-validation-20260928/`。"
              "本轮显式设置 ENI `AssociatePublicIpAddress=False` 后重新创建，未改动默认子网设置。",
              "The initial 09:54 setup attempt stopped and cleaned up because the default subnet assigned public addresses; no Browser checks ran. "
              "Its records are in ../proxy-validation-20260928/. This run explicitly sets ENI AssociatePublicIpAddress=False without changing subnet defaults."),
            "",
            t("参考仓库 9 月 23 日报告使用 `cntest` / 账号 `447150580482`，目标为 HTTP 8081 / HTTPS 8443，外部代理监听 8080。"
              "本轮增加相同端口组合和标准端口对照，使用独立账号，不覆盖原报告结果。",
              "The September 23 reference report uses cntest / account 447150580482, origin HTTP 8081 / HTTPS 8443, and external proxy port 8080. "
              "This run adds those combinations and standard-port controls in a different account; it does not overwrite the reference results."),
            "- [Reference report](https://github.com/milan9527/aws-agentcore-china-tests/blob/main/COMBINED_TEST_REPORT_ZH.md)",
            "- [AWS Browser proxy documentation](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/browser-proxies.html)", ""]
        (output/("REPORT.zh-CN.md" if chinese else "REPORT.md")).write_text("\n".join(lines))
    snapshot_count=0
    for path in output.glob("source-snapshots/*/manifest.json"):
        for name,expected in json.loads(path.read_text())["files"].items():
            assert hashlib.sha256((path.parent/name).read_bytes()).hexdigest()==expected
            snapshot_count+=1
    artifacts={}
    for path in output.rglob("*"):
        if not path.is_file() or path.name in ("artifacts.json","validation.json"):
            continue
        data=path.read_bytes()
        assert not re.search(rb"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",data),path
        artifacts[str(path.relative_to(output))]={"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}
    (output/"artifacts.json").write_text(json.dumps({"snapshotAt":result["generatedAt"],
        "note":"Deferred cleanup can update status/state/results files after this snapshot.","files":artifacts},indent=2)+"\n")
    validation={"status":"PASS","time":result["generatedAt"],"attemptRowsVerified":len(records),
        "sourceSnapshotFilesVerified":snapshot_count,"serverEventsCrossReferenced":True,"artifacts":len(artifacts)}
    (output/"validation.json").write_text(json.dumps(validation,indent=2)+"\n")
    print(json.dumps(validation,indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--results-dir",type=Path,required=True)
    export(parser.parse_args().results_dir.resolve())
