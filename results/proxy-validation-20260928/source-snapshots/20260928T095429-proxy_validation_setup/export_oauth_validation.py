"""Validate saved OAuth evidence and export bilingual reports without AWS calls."""
import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
LABELS = {
    "oauth.fixture.baselines": ("IdP 正反例与直接 OBO 对照", "IdP positive/negative and direct OBO baselines"),
    "gateway.oauth.2lo.client_secret_basic": ("2LO / client_secret_basic", "2LO / client_secret_basic"),
    "gateway.oauth.2lo.client_secret_post": ("2LO / client_secret_post", "2LO / client_secret_post"),
    "gateway.oauth.3lo.consent_required": ("3LO / 首次调用要求用户授权", "3LO / initial consent required"),
    "gateway.oauth.3lo.session_binding": ("3LO / 回调与用户会话绑定", "3LO / callback and user session binding"),
    "gateway.oauth.3lo.cached_user": ("3LO / 同用户再次调用", "3LO / repeat call by authorized user"),
    "gateway.oauth.3lo.user_isolation": ("3LO / 另一用户需独立授权", "3LO / independent consent for another user"),
    "gateway.oauth.3lo.authorization_code": ("3LO / 恢复调用并到达后端", "3LO / resumed end-to-end invocation"),
    "gateway.oauth.obo.rfc8693-none": ("OBO / RFC 8693 / NONE", "OBO / RFC 8693 / NONE"),
    "gateway.oauth.obo.rfc8693-m2m": ("OBO / RFC 8693 / M2M", "OBO / RFC 8693 / M2M"),
    "gateway.oauth.obo.rfc8693-aws-iam-id-token-jwt": ("OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT", "OBO / RFC 8693 / AWS_IAM_ID_TOKEN_JWT"),
    "gateway.oauth.obo.rfc7523-jwt-bearer": ("OBO / RFC 7523 / JWT Bearer", "OBO / RFC 7523 / JWT Bearer"),
}


def export(output):
    summary = json.loads((output / "summary.json").read_text())
    regions = list(summary["regions"])
    records = []
    snapshots = 0
    for manifest in output.glob("source-snapshots/*/manifest.json"):
        for name, expected in json.loads(manifest.read_text())["files"].items():
            assert hashlib.sha256((manifest.parent / name).read_bytes()).hexdigest() == expected, (manifest, name)
            snapshots += 1
    for region, result in summary["regions"].items():
        audit_path = output / f"{region}-api-audit.jsonl"
        audit = [json.loads(line) for line in audit_path.read_text().splitlines()]
        responses = {}
        for line, event in enumerate(audit, 1):
            if event["event"] == "response":
                request_id = event.get("parsed", {}).get("ResponseMetadata", {}).get("RequestId")
                if request_id:
                    responses[request_id] = (line, event)
            elif event["event"] == "http_response":
                request_id = {k.lower(): v for k, v in event.get("headers", {}).items()}.get("x-amzn-requestid")
                if request_id:
                    responses[request_id] = (line, event)
        for feature, row in result["checks"].items():
            assert row["status"] in ("PASS", "BLOCKED"), (region, feature, row["status"])
            source = output / row["source"]
            original = json.loads(source.read_text().splitlines()[row["sourceLine"] - 1])
            assert all(original[k] == row[k] for k in ("time", "region", "feature", "status", "evidence"))
            proof = row["evidence"]
            if "gatewayResponse" in proof:
                response = proof["gatewayResponse"]
                request_id = response["headers"]["x-amzn-requestid"]
                line, audited = responses[request_id]
                assert audited["status"] == response["status"] == 200
                assert proof["issuerIssuance"] and proof["issuerUsage"]
                records.append({"region": region, "feature": feature, "attempt": 1,
                    "status": row["status"], "httpStatus": 200, "requestId": request_id,
                    "operation": "MCP tools/call", "source": audit_path.name, "sourceLine": line})
            for rejected in proof.get("rejections", []):
                response = rejected["response"]
                request_id = response["ResponseMetadata"]["RequestId"]
                line, audited = responses[request_id]
                assert audited["service"] == "bedrock-agentcore-control"
                assert audited["operation"] == "CreateGatewayTarget"
                assert audited["status"] == response["ResponseMetadata"]["HTTPStatusCode"] == 403
                assert response["Error"]["Message"] == "Token Exchange is not available for this account"
                assert proof["gatewayTokenEndpointRequests"] == 0 and not proof["endToEndInvocationExecuted"]
                records.append({"region": region, "feature": feature, "attempt": rejected["attempt"],
                    "status": row["status"], "httpStatus": 403, "requestId": request_id,
                    "operation": "CreateGatewayTarget", "source": audit_path.name, "sourceLine": line})
        assert result["cleanup"]["status"] == "PASS"
    with (output / "request-index.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["region", "feature", "attempt", "status", "httpStatus",
                                                   "requestId", "operation", "source", "sourceLine"])
        writer.writeheader()
        writer.writerows(records)
    blocked_count = sum(r["status"] == "BLOCKED" for r in records)
    # This detailed interpretation is for the observed baseline. The runner always
    # produces a status-driven report; do not overwrite changed results with it.
    assert all(
        row["status"] == ("BLOCKED" if feature.startswith("gateway.oauth.obo.") else "PASS")
        for result in summary["regions"].values() for feature, row in result["checks"].items()
    ), "Outcomes differ from this baseline; retain the runner report and review the interpretation."
    for lang, suffix in ((0, ".zh-CN"), (1, "")):
        def t(zh, en):
            return (zh, en)[lang]
        lines = [t("# Gateway 出站 OAuth：2LO / 3LO / OBO 验证报告",
                   "# Gateway outbound OAuth: 2LO / 3LO / OBO validation"), "",
            f"{summary['startedAt']} → {summary['completedAt']} (UTC). AWS profile: `china`; account: `209915754514`.", "",
            t("**北京、宁夏：2LO 和 3LO 端到端通过。OBO 在当前账号两区均被 Gateway 服务的账号限制阻断，尚未执行端到端交换。**",
              "**Beijing and Ningxia: 2LO and 3LO pass end to end. Gateway account gating blocks OBO in both regions for this account; no end-to-end Gateway exchange was executed.**"),
            "",
            t("**提供商范围：本次仅使用自建合成 OIDC/OAuth IdP，通过 `CustomOauth2` 接入 AgentCore。未接入 Microsoft Entra ID、Google、Okta 或其他第三方 IdP。2LO/3LO 通过仅说明与该测试 IdP 的流程通过；第三方兼容性及 Microsoft OBO 均未验证。**",
              "**Provider scope: this run uses only a self-hosted synthetic OIDC/OAuth IdP connected through CustomOauth2. Microsoft Entra ID, Google, Okta, and other third-party IdPs were not used. Passing 2LO/3LO results apply to this test IdP; third-party compatibility and Microsoft OBO remain untested.**"),
            "", t("| 检查 | 北京 cn-north-1 | 宁夏 cn-northwest-1 |",
                  "| Check | Beijing cn-north-1 | Ningxia cn-northwest-1 |"), "| --- | --- | --- |"]
        for feature, labels in LABELS.items():
            lines.append("| " + labels[lang] + " | " + " | ".join(
                summary["regions"][r]["checks"][feature]["status"] for r in regions) + " |")
        lines += ["", t("每区 12 个专项检查：8 PASS、4 BLOCKED、0 FAIL。该计数包括对照及流程子步骤，不与主报告的 159 项功能集合相加。",
                        "Each region has 12 focused checks: 8 PASS, 4 BLOCKED, 0 FAIL. These include controls and flow substeps and are separate from the main report's 159-feature population."),
            "", t("## OAuth client 与 OBO 配置", "## OAuth client and OBO configuration"), "",
            t("本次使用了 OAuth client：`client_id=cn-retest`，`client_secret` 为每区独立随机生成的测试密钥，配置在 OAuth Credential Provider 的 `clientId` / `clientSecret` 中。"
              "2LO 分别使用 `CLIENT_SECRET_BASIC` 和 `CLIENT_SECRET_POST`；3LO 与四种 OBO 配置使用 `CLIENT_SECRET_BASIC`。"
              "2LO/3LO 已实际使用该客户端获取出站令牌；OBO 仅完成客户端和提供商配置，随后在创建 Gateway 目标时受阻。密钥未写入报告，测试结束已清理本地密钥文件。",
              "An OAuth client was used: client_id=cn-retest with an independently generated random client_secret per region, configured in the OAuth Credential Provider's clientId/clientSecret fields. "
              "2LO tests CLIENT_SECRET_BASIC and CLIENT_SECRET_POST; 3LO and all four OBO configurations use CLIENT_SECRET_BASIC. "
              "2LO/3LO actually use the client to obtain outbound tokens. OBO client/provider configuration succeeds, but Gateway target creation is blocked. Secrets are omitted from reports and local secret files were removed after the run."),
            "",
            t("OBO 的 Gateway 入站认证为 `CUSTOM_JWT`，允许的 audience/client 为 `cn-retest`、scope 为 `test`。"
              "目标的出站认证为 `OAUTH`，引用提供商 ARN，设置 `scopes=[\"test\"]`、`grantType=TOKEN_EXCHANGE`。"
              "提供商的 `onBehalfOfTokenExchangeConfig` 决定 RFC 8693 或 RFC 7523 模式。`actorTokenContent=NONE` 只表示不附带 actor token，与 Gateway 的 No Authorization 无关。"
              "RFC 7523 合成测试配置不等于接入 Microsoft Entra ID。",
              "The OBO Gateway uses CUSTOM_JWT inbound authentication, allowing audience/client cn-retest and scope test. "
              "Target outbound authentication uses OAUTH, the provider ARN, scopes=[\"test\"], and grantType=TOKEN_EXCHANGE. "
              "The provider's onBehalfOfTokenExchangeConfig selects RFC 8693 or RFC 7523. actorTokenContent=NONE means no actor token is attached; it does not mean Gateway No Authorization. "
              "The synthetic RFC 7523 configuration is not a Microsoft Entra ID integration."),
            "", t("## 实际调用过程", "## Observed flows"), "",
            t("2LO 分别配置 `CLIENT_SECRET_BASIC` 与 `CLIENT_SECRET_POST`，创建 OpenAPI MCP 目标后通过 Gateway 调用。"
              "IdP 记录 `grant_type=client_credentials`；后端验证签名、issuer、audience 和有效期，返回 `authenticated=true`、`sub=synthetic-service`。"
              "后端令牌哈希与 IdP 签发记录一致，且不同于入站 JWT。两种模式再次调用均通过，并各自再次请求了令牌端点；本次不宣称 2LO 缓存命中。",
              "2LO uses separate CLIENT_SECRET_BASIC and CLIENT_SECRET_POST providers and OpenAPI MCP targets. "
              "The IdP observes grant_type=client_credentials, and the backend verifies the signature, issuer, audience, and expiry, returning authenticated=true and sub=synthetic-service. "
              "The backend token hash matches IdP issuance and differs from the inbound JWT. Both repeat calls succeed and each fetches a token again; this run does not demonstrate a 2LO cache hit."),
            "",
            t("3LO 使用 MCP `2026-07-28` 和 URL elicitation：新用户调用得到 `resultType=input_required`；"
              "合成 IdP 自动批准测试身份的授权；跟随 AgentCore → IdP → AgentCore callback → 应用 callback 的重定向；"
              "调用 `CompleteResourceTokenAuth` 绑定同一用户，再通过 `inputResponses` 恢复调用，得到 `resultType=complete`。"
              "后端确认 `grant=authorization_code`。同用户再次调用成功且没有新的令牌请求；另一用户仍须授权，未到达后端。",
              "3LO uses MCP 2026-07-28 and URL elicitation. A new user receives resultType=input_required. "
              "The synthetic IdP automatically approves the test identity; redirects traverse AgentCore, IdP, AgentCore callback, and application callback. "
              "CompleteResourceTokenAuth binds the same inbound user; inputResponses resumes the tool call with resultType=complete. "
              "The backend confirms grant=authorization_code. A repeat call succeeds without another token request. Another user still requires consent and does not reach the backend."),
            "", t("## OBO 的明确结论", "## OBO conclusion"), "",
            t(f"四种提供商配置在两区均创建成功并回读确认。每种配置创建 Gateway 目标两次，共 **{blocked_count} 次**，均返回：",
              f"All four provider configurations were created and read back in both regions. Each configuration was used in two Gateway target creation attempts, **{blocked_count} attempts** in total, all returning:"),
            "", "```text", "Service: bedrock-agentcore-control", "Operation: CreateGatewayTarget",
            "HTTP 403 / AccessDeniedException", "Token Exchange is not available for this account", "```", "",
            t("所有 Gateway 目标都使用 `credentialProviderType=OAUTH`、`grantType=TOKEN_EXCHANGE`。"
              "RFC 8693 的 provider `grantType=TOKEN_EXCHANGE`，actor 分别为 `NONE`、`M2M`、`AWS_IAM_ID_TOKEN_JWT`；"
              "RFC 7523 的 provider `grantType=JWT_AUTHORIZATION_GRANT`。拒绝发生在目标创建阶段，各 OBO 测试窗口没有 Gateway 发往 IdP 的令牌请求。",
              "All Gateway targets use credentialProviderType=OAUTH and grantType=TOKEN_EXCHANGE. "
              "RFC 8693 providers use grantType=TOKEN_EXCHANGE with actor NONE, M2M, or AWS_IAM_ID_TOKEN_JWT. "
              "The RFC 7523 provider uses grantType=JWT_AUTHORIZATION_GRANT. Rejection occurs at target creation, with no Gateway-to-IdP token requests in any OBO test window."),
            "",
            t("直接访问合成 IdP 的 RFC 8693 与 JWT Bearer 交换及受保护后端均通过，排除了基本测试令牌和提供商不可用的前提问题。"
              "这些直接对照不代表 Gateway OBO 通过。结论仅适用于账号 `209915754514` 在测试时的两区状态，不能扩大为所有中国区账号不支持。"
              "下一步需要 AWS 确认/开放该账号的 Gateway Token Exchange 后再运行；AWS IAM actor 模式另有出站 Web Identity Federation 的账号前提，本次未更改。",
              "Direct RFC 8693 and JWT Bearer exchanges against the synthetic IdP, followed by protected-backend calls, pass. "
              "These establish fixture readiness and do not count as Gateway OBO success. The finding applies to account 209915754514 in these regions at the test time, not every China-region account. "
              "AWS must confirm/enable Gateway Token Exchange for this account before end-to-end retesting. The AWS IAM actor mode has an additional outbound web identity federation prerequisite; this run did not change it."),
            "", t("## 请求 ID 与证据索引", "## Request IDs and evidence index"), "",
            t("| 区域 | 调用/配置 | 尝试 | HTTP | 请求 ID | 审计行 |", "| Region | Flow/configuration | Attempt | HTTP | Request ID | Audit line |"),
            "| --- | --- | ---: | ---: | --- | ---: |"]
        for row in records:
            lines.append(f"| {row['region']} | {LABELS[row['feature']][lang]} | {row['attempt']} | "
                         f"{row['httpStatus']} | `{row['requestId']}` | [{row['sourceLine']}]({row['source']}) |")
        lines += ["", t("## 复现命令", "## Reproduction"), "", "```bash",
            "python3 -m venv .venv", ".venv/bin/pip install -r requirements-followup.lock.txt",
            "# Install cloudflared as described in REPRODUCE.zh-CN.md.",
            ".venv/bin/python run_oauth_validation.py --results-dir results/oauth-reproduction-new",
            ".venv/bin/python export_oauth_validation.py --results-dir results/oauth-reproduction-new", "```", "",
            t("必须使用新的空目录。默认使用 `china` profile 同时测试两区；`--cloudflared /absolute/path` 可覆盖二进制位置。"
              "需要创建/删除测试 IAM 角色、AgentCore Gateway/目标、OAuth provider、workload identity，以及回查 Secrets Manager 的权限。"
              "不需要创建 Browser、EC2、Lambda、API Gateway 或 S3 桶。",
              "Use a new empty directory. The runner tests both regions with profile china; --cloudflared /absolute/path overrides the binary location. "
              "Permissions are needed for test IAM roles, AgentCore Gateways/targets, OAuth providers, workload identities, and Secrets Manager cleanup verification. "
              "No Browser, EC2, Lambda, API Gateway, or S3 bucket creation is needed."),
            "",
            t("本次一键运行已实际从零执行并完成清理，退出码 `2` 表示存在明确账号阻断；`0` 为全部通过，`1` 为检查、执行或清理异常。"
              "合成 IdP 和隧道只在运行期间存在；历史资源已清理，不能重用旧 URL、授权码或状态文件。"
              "详细导出器核验本次 2LO/3LO 通过、OBO 受限的基线；未来结果改变时会拒绝覆盖解释，请保留运行器生成的新报告并重新分析。",
              "The one-command runner was executed from a fresh environment and completed cleanup. Exit 2 denotes explicit account gating; 0 denotes all passing and 1 denotes check, execution, or cleanup errors. "
              "The synthetic IdP and tunnel exist only during the run. Historical URLs, authorization codes, and resource state cannot be reused. "
              "The detailed exporter validates this passing-2LO/3LO, blocked-OBO baseline. If outcomes change, it refuses to overwrite the interpretation; retain and analyze the runner's new report."),
            "", t("## 完整记录与清理", "## Records and cleanup"), "",
            "- [console.log](console.log) · [phase-commands.jsonl](phase-commands.jsonl) · [environment.json](environment.json)",
            "- [summary.json](summary.json) · [request-index.csv](request-index.csv) · [validation.json](validation.json)",
            "- [source-snapshots](source-snapshots/) · [artifacts.json](artifacts.json) · [redaction-report.json](redaction-report.json)",
            "", t("各区域 `*-results.jsonl` 保存逐项判定；`*-api-audit.jsonl` 保存请求/响应；`*-issuer-events.jsonl` 保存签发和使用证据。",
                  "Regional *-results.jsonl files hold verdicts, *-api-audit.jsonl files hold requests/responses, and *-issuer-events.jsonl files hold issuance/usage evidence."), ""]
        for region, result in summary["regions"].items():
            cleanup = result["cleanup"]
            scheduled = sum(c.get("status") == "ScheduledDeletion" for c in cleanup["checks"])
            lines.append(t(f"- {region}：清理核验 {cleanup['status']}。Gateway、3 个目标、7 个 OAuth provider、workload identity 和 IAM 角色均查无资源；"
                           f"本地进程已停、私钥/密钥文件已删除。{scheduled} 个服务托管 Secret 在回查时有删除标记，等待 AWS 异步删除。",
                           f"- {region}: cleanup verification {cleanup['status']}. Gateway, 3 targets, 7 OAuth providers, workload identity, and IAM role are absent. "
                           f"Local processes are stopped and key/secret files removed. {scheduled} service-managed secrets had deletion markers at verification, awaiting AWS asynchronous deletion."))
        lines += ["", t("本次范围是合成 CustomOauth2 提供商的功能验证，没有接入 Microsoft Entra ID、Google、Okta 等任何第三方 IdP，也未测试长时间刷新令牌、并发负载或 MFA。"
                         "M2M/AWS IAM actor 的真正交换行为仍因 Gateway 目标账号门槛而未执行。",
                         "This run validates functionality with a synthetic CustomOauth2 provider. No third-party IdP, including Microsoft Entra ID, Google, or Okta, was used. Long-duration refresh-token behavior, concurrency, and MFA were not tested. "
                         "Actual M2M/AWS IAM actor exchange behavior remains unexecuted behind the Gateway target account gate."),
            "", t("## 官方文档", "## Official documentation"), "",
            "- [Gateway outbound authorization](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/gateway-outbound-auth.html)",
            "- [On-behalf-of token exchange](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html)",
            "- [OAuthCredentialProvider](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_OAuthCredentialProvider.html)",
            "- [OnBehalfOfTokenExchangeConfigType](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_OnBehalfOfTokenExchangeConfigType.html)",
            "", t("本次读取的文档副本和检索元数据保存在 `documentation/`；文档定义模式，实际可用性以上述服务调用为准。",
                   "Retrieved documentation and metadata are retained under documentation/. Documentation defines the modes; the service calls above establish observed availability."), ""]
        (output / ("REPORT" + suffix + ".md")).write_text("\n".join(lines))
    report_source = output / "report-source" / Path(__file__).name
    report_source.parent.mkdir(exist_ok=True)
    report_source.write_bytes(Path(__file__).read_bytes())
    (output / "report-generation.json").write_text(json.dumps({
        "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": [".venv/bin/python", "export_oauth_validation.py", "--results-dir", str(output.relative_to(ROOT))],
        "cwd": str(ROOT), "awsCalls": False,
        "exporterSource": str(report_source.relative_to(output)),
        "exporterSha256": hashlib.sha256(report_source.read_bytes()).hexdigest(),
    }, indent=2) + "\n")
    patterns = [
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        rb"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        rb"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b",
    ]
    files = {}
    for path in output.rglob("*"):
        if not path.is_file() or path.name in ("artifacts.json", "validation.json"):
            continue
        data = path.read_bytes()
        assert not any(re.search(pattern, data) for pattern in patterns), f"Potential credential: {path}"
        files[str(path.relative_to(output))] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    validation = {"status": "PASS", "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sourceSnapshotFilesVerified": snapshots, "apiRequestsCrossReferenced": len(records),
        "oboAccountRejections": blocked_count, "artifactCount": len(files),
        "secretPatternScan": "PASS", "sourceRowsMatchSummary": True,
        "counts": {r: dict(Counter(row["status"] for row in x["checks"].values()))
                   for r, x in summary["regions"].items()}}
    (output / "artifacts.json").write_text(json.dumps({"files": files}, indent=2) + "\n")
    (output / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    export(parser.parse_args().results_dir.resolve())
