"""Export bilingual caller-IAM evidence and verify saved source/audit references offline."""
import argparse
import ast
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil

from run_caller_reproduction import CHECKS, REGIONS

ROOT = Path(__file__).resolve().parent


def export(output):
    summary = json.loads((output / "summary.json").read_text())
    records = []
    configurations = {}
    for region in REGIONS:
        audit_path = output / f"{region}-api-audit.jsonl"
        audit = [json.loads(line) for line in audit_path.read_text().splitlines()]
        state = json.loads((output / f"{region}-state.json").read_text())
        configurations[region] = {
            "runtimeArn": state.get("runtime_arn"), "callerRoleArn": state.get("caller_role"),
            "gatewayRoleArn": state.get("agentcore_role"),
            "gateways": [event["parsed"] for event in audit
                         if event.get("event") == "response"
                         and event.get("operation") == "CreateGateway"],
            "targetRequests": [event["body"] for event in audit
                               if event.get("event") == "request"
                               and event.get("operation") == "CreateGatewayTarget"],
        }
        source = output / f"{region}-results.jsonl"
        rows = [json.loads(line) for line in source.read_text().splitlines()]
        for feature, selected in summary["regions"][region]["checks"].items():
            if selected is None:
                continue
            raw = rows[selected["sourceLine"] - 1]
            assert all(raw[key] == selected[key] for key in raw)
            evidence = raw["evidence"]
            if evidence.get("type") == "AssertionError":
                try:
                    parsed = ast.literal_eval(evidence["message"])
                except (ValueError, SyntaxError):
                    parsed = {}
            else:
                parsed = evidence
            request_id = parsed.get("requestId")
            matches = [
                (i, event) for i, event in enumerate(audit, 1)
                if request_id and event.get("event") == "http_response"
                and {key.lower(): value for key, value in event.get("headers", {}).items()
                     }.get("x-amzn-requestid") == request_id
            ]
            record = {
                "region": region, "feature": feature, "label": CHECKS[feature],
                "time": raw["time"], "status": raw["status"],
                "httpStatus": parsed.get("status"), "body": parsed.get("body"),
                "requestId": request_id, "source": source.name,
                "sourceLine": selected["sourceLine"],
                "auditSource": audit_path.name if matches else None,
                "auditResponseLines": [i for i, _ in matches],
                "rawEvidence": evidence,
            }
            for _, event in matches:
                assert event["status"] == record["httpStatus"]
                body = record["body"]
                try:
                    body = json.loads(body) if isinstance(body, str) else body
                except ValueError:
                    pass
                assert event["body"] == body
            if record["httpStatus"] is not None and request_id:
                assert matches, f"Missing HTTP audit reference: {region} {feature}"
            records.append(record)
    (output / "configurations.json").write_text(
        json.dumps(configurations, ensure_ascii=False, indent=2) + "\n")
    (output / "invocation-results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    fields = ["region", "feature", "label", "time", "status", "httpStatus", "body",
              "requestId", "source", "sourceLine", "auditSource", "auditResponseLines"]
    with (output / "invocation-results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({**record, "body": json.dumps(record["body"], ensure_ascii=False),
                             "auditResponseLines": json.dumps(record["auditResponseLines"])})
    snapshots = 0
    for manifest_path in (output / "source-snapshots").glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text())
        for name, digest in manifest["files"].items():
            assert hashlib.sha256((manifest_path.parent / name).read_bytes()).hexdigest() == digest
            snapshots += 1
    for chinese in (True, False):
        def t(zh, en):
            return zh if chinese else en
        lines = [
            t("# Gateway 调用者 IAM 凭证转发复测", "# Gateway caller-IAM forwarding retest"), "",
            f"{summary['startedAt']} — {summary['completedAt']}; AWS profile: `china`.", "",
            t("使用全新 Runtime、Gateway 和 IAM 角色，复用上一轮调用逻辑。"
              "两种目标配置分别为 `GATEWAY_IAM_ROLE`、`CALLER_IAM_CREDENTIALS`，"
              "均指向同一 HTTP Runtime。请求使用当前区域、`bedrock-agentcore` 服务名做 SigV4 签名。",
              "Fresh Runtime, Gateway and IAM roles use the previous invocation logic. "
              "GATEWAY_IAM_ROLE and CALLER_IAM_CREDENTIALS targets point to the same HTTP Runtime. "
              "Requests use SigV4 with bedrock-agentcore and the current region."), "",
            "| Region | Verdict | Checks | Cleanup |", "| --- | --- | --- | --- |",
        ]
        for region, result in summary["regions"].items():
            counts = dict(Counter(row["status"] for row in records if row["region"] == region))
            lines.append(f"| {region} | {result['verdict']} | {counts} | {result['cleanup']['status']} |")
        if all(result["verdict"] == "NOT_REPRODUCED" for result in summary["regions"].values()):
            lines += ["", t(
                "**结论：本次两区原问题的全部对照通过，调用者 IAM 转发不再返回原无效令牌 403；"
                "在所测三种凭证/入站组合中已恢复。** 具体服务内部修复与部署时间未经确认。",
                "**All original comparison checks pass in both regions. Caller-IAM forwarding no longer "
                "returns the invalid-token 403 in the three tested credential/inbound combinations.** "
                "The internal fix and deployment time have not been established.")]
        lines += ["", t("## 判定范围", "## Interpretation"), "",
            t("`REPRODUCED`：5 项直接调用/执行角色对照通过，3 项调用者转发仍报原无效令牌错误，"
              "本次未观察到修复。`NOT_REPRODUCED`：8 项对照均通过，仅说明本次所测路径未再复现。"
              "`INCONCLUSIVE`：对照不完整或错误变化，需要进一步分析。",
              "REPRODUCED: all five direct/role controls pass and all three caller paths retain "
              "the invalid-token error; no fix observed in this run. NOT_REPRODUCED: all eight "
              "checks pass, limited to the tested paths. INCONCLUSIVE: incomplete controls or a changed error."),
            "", t("同一组 AssumeRole 凭证用于直接调用及两种入站模式；另一组 GetSessionToken 凭证"
                  "用于直接调用、执行角色出站和调用者出站。成功要求返回 `sum=42`。",
                  "The same AssumeRole credentials are used for direct invocation and both inbound modes. "
                  "A separate GetSessionToken set is shared by its three comparison paths. "
                  "Success requires sum=42."), "",
            t("## 响应与请求 ID", "## Responses and request IDs"), "",
            "| Region | Check | Result | HTTP | Response | Request ID | Evidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in records:
            body = json.dumps(row["body"], ensure_ascii=False).replace("|", "\\|").replace("\n", " ")
            label = row["label"] if chinese else row["feature"]
            status = row["httpStatus"] if row["httpStatus"] is not None else "SDK"
            lines.append(f"| {row['region']} | {label} | {row['status']} | {status} | "
                         f"`{body}` | `{row['requestId']}` | "
                         f"[L{row['sourceLine']}]({row['source']}) |")
        lines += ["", t("## 复现与记录", "## Reproduction and evidence"), "", "```bash",
            ".venv/bin/python run_caller_reproduction.py --results-dir results/repro-caller-new",
            ".venv/bin/python export_caller_reproduction.py --results-dir results/repro-caller-new",
            "```", "",
            t("必须使用新的空目录。运行器退出码：2=原问题复现，0=所选对照通过，1=执行/判定/清理异常。"
              "导出器只读取本地证据，不调用 AWS。",
              "Use a new empty directory. Runner exits: 2=original issue reproduced, "
              "0=selected checks pass, 1=execution/verdict/cleanup issue. The exporter is offline."), "",
            "- [Console](console.log) · [Commands](phase-commands.jsonl) · [Summary](summary.json)",
            "- [Invocation JSON](invocation-results.json) · [CSV](invocation-results.csv)",
            "- [Runtime/Gateway/target configurations](configurations.json) · [Environment](environment.json)",
            "- [Validation](validation.json) · [Artifact hashes](artifacts.json)",
            "", t("表格使用每个指定检查的最后一条原始记录，前期 Runtime 冒烟调用和失败均保留在日志。"
                  "独立临时凭证 SDK 客户端未注册框架审计，直接调用的响应和请求 ID 来自检查结果；"
                  "不补造未记录的 HTTP 状态码。12 条 Gateway HTTP 响应有原始 HTTP 审计关联"
                  "（如检查未完成，以 validation.json 的实际计数为准）。",
                  "The table selects the latest original row per specified check; initial Runtime smoke "
                  "calls and failures remain in the logs. Separate temporary-credential SDK clients "
                  "do not register the framework audit; their responses and request IDs come from "
                  "check results. Unrecorded HTTP status codes are not inferred. Gateway HTTP responses "
                  "are cross-referenced to audit rows; see validation.json for actual counts."), "",
            t("复用的 setup 还会执行公开 OIDC 探测，其失败不属于 IAM 转发检查；此次不启动外部 IdP。"
              "清理仅针对本次目录创建的资源。历史结果未改写。",
              "Shared setup also probes public OIDC; those failures are outside the IAM comparison. "
              "No external IdP is started. Cleanup targets this run's inventory; historical evidence is preserved."),
            "",
        ]
        if summary["errors"]:
            lines += [t("## 执行异常", "## Execution errors"), "",
                      *("- " + item for item in summary["errors"]), ""]
        (output / ("REPORT.zh-CN.md" if chinese else "REPORT.md")).write_text("\n".join(lines))
    report_source = output / "report-source"
    report_source.mkdir(exist_ok=True)
    shutil.copy2(__file__, report_source / Path(__file__).name)
    validation = {
        "time": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "PASS",
        "scope": "Evidence consistency only, not functional success",
        "selectedRowsVerified": len(records), "sourceSnapshotFilesVerified": snapshots,
        "httpResponsesCrossReferenced": sum(bool(row["auditResponseLines"]) for row in records),
    }
    (output / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    files = {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "artifacts.json"
    }
    (output / "artifacts.json").write_text(json.dumps({
        "generatedAt": validation["time"], "files": files}, indent=2) + "\n")
    print(json.dumps(validation))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    export(parser.parse_args().results_dir.resolve())
