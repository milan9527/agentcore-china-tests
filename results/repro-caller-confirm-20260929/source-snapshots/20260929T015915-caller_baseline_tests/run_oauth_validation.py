"""Reproduce Gateway 2LO/3LO/OBO in both China regions and clean the run."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from sanitize_evidence import redact_directory

ROOT = Path(__file__).resolve().parent
REGIONS = ("cn-north-1", "cn-northwest-1")
CHECKS = [
    "oauth.fixture.baselines",
    "gateway.oauth.2lo.client_secret_basic",
    "gateway.oauth.2lo.client_secret_post",
    "gateway.oauth.3lo.consent_required",
    "gateway.oauth.3lo.session_binding",
    "gateway.oauth.3lo.cached_user",
    "gateway.oauth.3lo.user_isolation",
    "gateway.oauth.3lo.authorization_code",
    "gateway.oauth.obo.rfc8693-none",
    "gateway.oauth.obo.rfc8693-m2m",
    "gateway.oauth.obo.rfc8693-aws-iam-id-token-jwt",
    "gateway.oauth.obo.rfc7523-jwt-bearer",
]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def latest(output):
    rows = {}
    for path in output.glob("*-results.jsonl"):
        for line, text in enumerate(path.read_text().splitlines(), 1):
            row = json.loads(text)
            row.update(source=path.name, sourceLine=line)
            rows[(row["region"], row["feature"])] = row
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--cloudflared", type=Path, default=ROOT / "results/retest/cloudflared")
    args = parser.parse_args()
    output = args.results_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use a new empty results directory")
    cloudflared = args.cloudflared.resolve()
    if not cloudflared.is_file() or not os.access(cloudflared, os.X_OK):
        parser.error("Install cloudflared and provide its executable path")
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "RETEST_RESULTS_DIR": str(output), "RETEST_VERBOSE": "1",
           "PYTHONUNBUFFERED": "1", "RETEST_ISSUER_SCRIPT": "oauth_issuer_server.py",
           "CLOUDFLARED_PATH": str(cloudflared)}
    for key in ("RETEST_STATE_READ_ONLY", "PYTHONPATH"):
        env.pop(key, None)
    started = now()
    errors = []
    (output / "environment.json").write_text(json.dumps({
        "startedAt": started, "profile": "china", "regions": REGIONS,
        "python": sys.version, "command": sys.argv,
        "gitCommitBeforeRun": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "cloudflaredVersion": subprocess.check_output([str(cloudflared), "--version"], text=True).strip(),
        "cloudflaredSha256": hashlib.sha256(cloudflared.read_bytes()).hexdigest(),
        "dependencies": subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines(),
    }, indent=2) + "\n")

    def phase(name):
        command = [sys.executable, str(ROOT / "retest.py"), name]
        entry = {"time": now(), "event": "start", "command": command, "cwd": str(ROOT),
            "environment": {k: env[k] for k in ("RETEST_RESULTS_DIR", "RETEST_VERBOSE",
                "PYTHONUNBUFFERED", "RETEST_ISSUER_SCRIPT", "CLOUDFLARED_PATH")},
            "profile": "china", "regions": REGIONS}
        with (output / "phase-commands.jsonl").open("a") as log:
            log.write(json.dumps(entry) + "\n")
        print(json.dumps(entry), flush=True)
        with (output / "console.log").open("a") as combined, (output / (name + ".log")).open("a") as log:
            combined.write(json.dumps(entry) + "\n")
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            try:
                for line in proc.stdout:
                    print(line, end="", flush=True)
                    combined.write(line)
                    combined.flush()
                    log.write(line)
                    log.flush()
                code = proc.wait()
            except BaseException:
                proc.terminate()
                proc.wait(timeout=30)
                raise
        with (output / "phase-commands.jsonl").open("a") as log:
            log.write(json.dumps({"time": now(), "event": "end", "phase": name, "returncode": code}) + "\n")
        assert code == 0, f"{name} exit {code}"
        rows = latest(output)
        assert all(rows.get((region, name + ".suite"), {}).get("status") == "PASS" for region in REGIONS), name

    try:
        for name in ("oauth_validation_setup", "retest_tunnels", "oauth_validation_tests"):
            phase(name)
    except Exception as error:
        errors.append(str(error))
        print("EXECUTION ERROR:", error, flush=True)
    finally:
        for name in ("cleanup_tests", "retest_cleanup_local", "oauth_validation_cleanup_verify"):
            try:
                phase(name)
            except Exception as error:
                errors.append(str(error))
                print("CLEANUP ERROR:", error, flush=True)
        print(json.dumps(redact_directory(output)), flush=True)
    rows = latest(output)
    summary = {"startedAt": started, "completedAt": now(), "profile": "china", "errors": errors, "regions": {}}
    for region in REGIONS:
        selected = {feature: rows.get((region, feature), {"status": "NOT_RUN"}) for feature in CHECKS}
        verification = output / f"{region}-cleanup-verification.json"
        cleanup = json.loads(verification.read_text()) if verification.exists() else {"status": "NOT_RUN"}
        summary["regions"][region] = {"checks": selected, "cleanup": cleanup}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Gateway 出站 OAuth 2LO / 3LO / OBO 实测", "",
        f"开始：{started}；完成：{summary['completedAt']}；AWS profile：`china`。", "",
        "本次仅使用自建合成 OIDC/OAuth IdP，以 `CustomOauth2` 接入；未使用 Microsoft Entra ID、Google、Okta 等第三方。"
        "OAuth client 为 `cn-retest`，每区独立随机生成 client secret。2LO 测试 Basic/POST 客户端认证，3LO/OBO 使用 Basic。"
        "通过结果仅适用于该测试 IdP；第三方兼容性及 Microsoft OBO 未验证。", "",
        "| 检查 | 北京 | 宁夏 |", "| --- | --- | --- |"]
    for feature in CHECKS:
        lines.append("| " + feature + " | " + " | ".join(summary["regions"][r]["checks"][feature]["status"]
                                                       for r in REGIONS) + " |")
    lines += ["", "## 结果含义", "",
        "- 2LO：Gateway 使用 client credentials 取得服务令牌并调用后端。",
        "- 3LO：首次用户授权 → 回调 → CompleteResourceTokenAuth → 恢复工具调用；另测缓存和用户隔离。",
        "- OBO：Gateway 目标 grantType 为 TOKEN_EXCHANGE；提供商分别配置 RFC 8693 与 RFC 7523。",
        "- BLOCKED 表示当前账号/区域在 Gateway CreateGatewayTarget 阶段被服务拒绝；不算端到端通过，也不推断所有中国区账号均不支持。",
        "- IdP 直接交换基线与 Gateway 出站调用分别记录；令牌哈希关联签发与后端使用。",
        "", "## 复现", "", "```bash",
        ".venv/bin/python run_oauth_validation.py --results-dir results/oauth-reproduction-new",
        "```", "", "使用新的空目录；依赖与 cloudflared 安装步骤见 [复现说明](../../REPRODUCE.zh-CN.md)。",
        "命令默认测试两区，创建临时 IAM 角色、AgentCore Gateway、OAuth 提供商，然后清理本次清单。",
        "退出码：0 全通过；2 包含明确账号限制；1 执行/检查/清理未通过。", "",
        "## 证据", "",
        "- [完整运行输出](console.log)、[命令与环境](phase-commands.jsonl)、[结构化结论](summary.json)。",
        "- 各区域 `*-api-audit.jsonl` 保存 AWS 请求/响应与请求 ID；`*-issuer-events.jsonl` 只保存安全的签发/使用元数据。",
        "- `source-snapshots/` 保存每个阶段的源码和哈希；`environment.json` 保存版本和 cloudflared 哈希。",
        "- `*-cleanup-verification.json` 保存资源回查；`redaction-report.json` 保存脱敏修改哈希。", "",
        "## 清理", ""]
    for region, result in summary["regions"].items():
        lines.append(f"- {region}：{result['cleanup']['status']}")
    if errors:
        lines += ["", "执行异常：" + "; ".join(errors)]
    (output / "REPORT.zh-CN.md").write_text("\n".join(lines) + "\n")
    states = [v["status"] for result in summary["regions"].values() for v in result["checks"].values()]
    code = (1 if errors or any(v not in ("PASS", "BLOCKED") for v in states)
            or any(r["cleanup"]["status"] != "PASS" for r in summary["regions"].values())
            else 2 if "BLOCKED" in states else 0)
    print(json.dumps({"report": str(output / "REPORT.zh-CN.md"), "returncode": code,
        "results": {r: {k: v["status"] for k, v in x["checks"].items()}
                    for r, x in summary["regions"].items()}}, indent=2), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
