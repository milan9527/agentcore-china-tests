"""Run the caller-IAM comparison, stream redacted results, and clean its inventory."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

from sanitize_evidence import redact_directory

ROOT = Path(__file__).resolve().parent
REGIONS = ("cn-north-1", "cn-northwest-1")
CHECKS = {
    "gateway.caller_iam.assumed_role.direct": "AssumeRole → Runtime 直接调用",
    "gateway.caller_iam.AWS_IAM.runtime-role": "AssumeRole / AWS_IAM → Gateway 执行角色",
    "gateway.caller_iam.AWS_IAM.runtime-caller": "AssumeRole / AWS_IAM → 调用者 IAM",
    "gateway.caller_iam.AUTHENTICATE_ONLY.runtime-role": "AssumeRole / AUTHENTICATE_ONLY → Gateway 执行角色",
    "gateway.caller_iam.AUTHENTICATE_ONLY.runtime-caller": "AssumeRole / AUTHENTICATE_ONLY → 调用者 IAM",
    "gateway.outbound.caller_iam.direct_runtime_baseline": "GetSessionToken → Runtime 直接调用",
    "gateway.outbound.caller_iam.gateway_role_baseline": "GetSessionToken → Gateway 执行角色",
    "gateway.outbound.caller_iam": "GetSessionToken → 调用者 IAM",
}
CALLER = {key for key in CHECKS if key.endswith("runtime-caller") or key == "gateway.outbound.caller_iam"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def latest(output):
    rows = {}
    for path in output.glob("*-results.jsonl"):
        for line, text in enumerate(path.read_text().splitlines(), 1):
            row = json.loads(text)
            row.update(source=str(path.relative_to(ROOT)), sourceLine=line)
            rows[(row["region"], row["feature"])] = row
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.results_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use a new empty results directory")
    output.mkdir(parents=True, exist_ok=True)
    output.relative_to(ROOT)
    env = {**os.environ, "RETEST_RESULTS_DIR":str(output), "VERIFY_RESULTS_DIR":str(output),
           "RETEST_VERBOSE":"1", "PYTHONUNBUFFERED":"1"}
    for key in ("RETEST_STATE_READ_ONLY", "PYTHONPATH"):
        env.pop(key, None)
    errors = []
    started = now()

    def run_command(command, label, extra=None):
        details = {"time":now(), "event":"start", "command":command, "cwd":str(ROOT),
            "profile":"china", "regions":list(REGIONS),
            "environment":{key:env[key] for key in ("RETEST_RESULTS_DIR", "VERIFY_RESULTS_DIR", "RETEST_VERBOSE")},
            "extraEnvironment":extra or {}}
        with (output/"phase-commands.jsonl").open("a") as log:
            log.write(json.dumps(details)+"\n")
        print(f"\n[{details['time']}] RUN {label}",flush=True)
        print(json.dumps(details,ensure_ascii=False),flush=True)
        with (output/(label+".log")).open("a") as log, (output/"console.log").open("a") as combined:
            header = json.dumps(details,ensure_ascii=False)+"\n"
            log.write(header); combined.write(header)
            process = subprocess.Popen(command,cwd=ROOT,env={**env,**(extra or {})},
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            try:
                for text in process.stdout:
                    print(text,end="",flush=True)
                    log.write(text);log.flush()
                    combined.write(text);combined.flush()
                code = process.wait()
            except BaseException:
                process.terminate()
                process.wait(timeout=30)
                raise
        with (output/"phase-commands.jsonl").open("a") as log:
            log.write(json.dumps({"time":now(),"event":"end","command":command,"returncode":code})+"\n")
        if code:
            raise RuntimeError(f"{label} process exit {code}")
        if command[1] == str(ROOT/"retest.py"):
            for row in latest(output).values():
                if row["feature"] == label+".suite" and row["time"] >= details["time"] and row["status"] != "PASS":
                    raise RuntimeError(f"{row['region']} phase failed: {label}")

    def phase(name, extra=None):
        run_command([sys.executable,str(ROOT/"retest.py"),name],name,extra)

    try:
        for name in ("retest_setup", "retest_runtime", "caller_baseline_tests"):
            phase(name)
    except Exception as error:
        errors.append(str(error))
        print("PHASE ERROR:",error,flush=True)
    finally:
        for name in ("cleanup_tests", "retest_cleanup_local"):
            try:
                phase(name,{"CLEANUP_SG_WAIT_SECONDS":"20"} if name=="cleanup_tests" else None)
            except Exception as error:
                errors.append(str(error));print("CLEANUP ERROR:",error,flush=True)
        try:
            run_command([sys.executable,str(ROOT/"verify_cleanup.py")],"verify_cleanup")
        except Exception as error:
            errors.append(str(error))
        print(json.dumps(redact_directory(output)),flush=True)
    rows = latest(output)
    conclusions = {}
    for region in REGIONS:
        selected = {key:rows.get((region,key)) for key in CHECKS}
        baselines_ok = all(selected[key] and selected[key]["status"]=="PASS" for key in CHECKS if key not in CALLER)
        callers_fail = all(selected[key] and selected[key]["status"]=="FAIL" and
            "The security token included in the request is invalid" in json.dumps(selected[key]["evidence"])
            for key in CALLER)
        all_pass = all(row and row["status"]=="PASS" for row in selected.values())
        verification = output/f"{region}-cleanup-verification.json"
        cleanup = json.loads(verification.read_text()) if verification.exists() else {"status":"NOT_RECORDED"}
        conclusions[region] = {"verdict":"REPRODUCED" if baselines_ok and callers_fail else
            "NOT_REPRODUCED" if all_pass else "INCONCLUSIVE",
            "baselinesPass":baselines_ok, "callerInvalidTokenReproduced":callers_fail,
            "checks":selected, "cleanup":cleanup}
    summary = {"startedAt":started,"completedAt":now(),"profile":"china",
        "errors":errors,"regions":conclusions}
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    lines = ["# Gateway 调用者 IAM 转发再次复现", "",
        f"开始：{started}；结束：{summary['completedAt']}；profile：`china`。", "",
        "| 区域 | 结论 | 成功对照 | 清理核验 |","| --- | --- | --- |"]
    for region, result in conclusions.items():
        lines.append(f"| {region} | {result['verdict']} | {result['baselinesPass']} | {result['cleanup']['status']} |")
    lines += ["", "## 逐项结果", "", "| 区域 | 调用路径 | 结果 | 证据 |","| --- | --- | --- | --- |"]
    for region, result in conclusions.items():
        for key,label in CHECKS.items():
            row = result["checks"][key]
            evidence = f"[结果第 {row['sourceLine']} 行]({region}-results.jsonl)" if row else "未执行"
            lines.append(f"| {region} | {label} | {row['status'] if row else 'NOT_RUN'} | {evidence} |")
    lines += ["", "## 运行记录", "",
        "- [完整控制台输出](console.log)：阶段开始、等待状态、逐项结果与脱敏后的完整证据。",
        "- [命令记录](phase-commands.jsonl)：实际命令、时间、环境参数和进程退出码。",
        "- [结构化结论](summary.json)：调用结果、响应、请求 ID、源文件及行号、清理核验。",
        "- 各区域 `*-api-audit.jsonl` 和 `source-snapshots/` 保留框架请求审计及执行时源码。",
        "", "调用者路径失败且相同凭证直接调用和执行角色对照均通过，才判定为本次无效令牌问题复现。"
        "其他错误或前提未就绪判为 INCONCLUSIVE；失败不直接证明 AWS 内部根因。",
        "", "setup 中公开 OIDC 403 探测与本次 IAM 调用无关；此次没有启动外部 IdP 隧道。", ""]
    if errors:
        lines += ["## 执行异常", "", *("- "+error for error in errors), ""]
    (output/"REPORT.zh-CN.md").write_text("\n".join(lines))
    print("\nFINAL SUMMARY",flush=True)
    print(json.dumps({region:{k:v for k,v in result.items() if k not in ("checks","cleanup")} |
        {"cleanup":result["cleanup"]["status"]} for region,result in conclusions.items()},indent=2),flush=True)
    print("REPORT:",output/"REPORT.zh-CN.md",flush=True)
    return 1 if errors or any(r["cleanup"]["status"]!="PASS" or r["verdict"]=="INCONCLUSIVE" for r in conclusions.values()) else (
        2 if any(r["verdict"]=="REPRODUCED" for r in conclusions.values()) else 0)


if __name__ == "__main__":
    sys.exit(main())
