# Browser proxy validation: ports, authentication, routing, and bypass

Live tests use AWS profile china, account 209915754514, in Beijing and Ningxia. This report is generated from saved observations and endpoint logs without AWS calls.

**The observed path is Browser → managed Squid → custom external proxy → separate origin. The port matrix and server logs distinguish proxy listener ports from origin destination ports.**

## Environment and assertions

Each region uses two EC2 instances without public addresses: a separate origin and Python external proxy in the test security group. The origin listens on HTTP 80/8000/8081 and HTTPS 443/8443. Proxy listeners are 3128/8080 (Basic) and 3129 (no authentication). HTTP is actually forwarded to the origin; HTTPS uses CONNECT. Certificates cover the origin IP and test hostnames, with certificate verification enabled.

Each request carries a unique /probe/<marker> path linking Browser results with origin logs. Proxy routing requires the origin to observe the proxy IP plus corresponding listener authentication/CONNECT evidence. Bypass requires a non-proxy origin peer and no matching external-proxy request in the observation window. Wrong/missing credential controls require no origin request and an external-proxy authentication rejection. Failed checks repeat once with both attempts retained.

| Region | Origin IP | Proxy IP | Unique checks | Attempts | Latest verdicts |
| --- | --- | --- | ---: | ---: | --- |
| cn-north-1 | 172.31.39.252 | 172.31.32.245 | 95 | 130 | {"PASS": 60, "FAIL": 35} |
| cn-northwest-1 | 172.31.14.177 | 172.31.14.103 | 95 | 130 | {"PASS": 60, "FAIL": 35} |

### Summary by path

| Region | Group | Latest verdicts |
| --- | --- | --- |
| cn-north-1 | direct | {"PASS": 10} |
| cn-north-1 | playwrightExternalProxy | {"PASS": 15} |
| cn-north-1 | managedExternalProxy | {"PASS": 12, "FAIL": 18} |
| cn-north-1 | bypass | {"PASS": 10, "FAIL": 15} |
| cn-north-1 | proxyOnlyDns | {"FAIL": 2, "PASS": 2} |
| cn-north-1 | multiProxy | {"PASS": 4} |
| cn-northwest-1 | direct | {"PASS": 10} |
| cn-northwest-1 | playwrightExternalProxy | {"PASS": 15} |
| cn-northwest-1 | managedExternalProxy | {"PASS": 12, "FAIL": 18} |
| cn-northwest-1 | bypass | {"PASS": 10, "FAIL": 15} |
| cn-northwest-1 | proxyOnlyDns | {"FAIL": 2, "PASS": 2} |
| cn-northwest-1 | multiProxy | {"PASS": 4} |

## Check matrix

Cells show Beijing / Ningxia; — means that port was not selected for the scenario. PASS refers to the stated assertion; negative authentication/certificate controls pass when rejection is verified.

| Scenario | HTTP 80 | HTTP 8000 | HTTP 8081 | HTTPS 443 | HTTPS 8443 |
| --- | --- | --- | --- | --- | --- |
| direct-baseline | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| playwright-proxy-3128 | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| playwright-proxy-8080 | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| playwright-proxy-3129 | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| managed-3128-default | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-3128-explicit | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-8080-default | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-8080-explicit | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-3129-default | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| managed-3129-explicit | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-ip | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-hostname | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-suffix | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-ip-bad-credentials | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| bypass-and-route-ip | PASS / PASS | FAIL / FAIL | FAIL / FAIL | PASS / PASS | FAIL / FAIL |
| hostname-route | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| proxy-only-dns-default | FAIL / FAIL | — / — | — / — | FAIL / FAIL | — / — |
| proxy-only-dns-explicit | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| bad-credentials | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| missing-credentials | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| multi-specific | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| multi-fallback | PASS / PASS | — / — | — / — | PASS / PASS | — / — |
| untrusted-control | — / — | — / — | — / — | PASS / PASS | — / — |
| direct-final-control | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |

direct-* uses no external proxy; playwright-proxy-* sets the external proxy directly on a new Playwright context; managed-* uses StartBrowserSession proxyConfiguration; explicit adds domain patterns; bypass-* checks exact IP/hostname/suffix bypass; multi-* checks specific and default proxy selection.

## Failed-request localization

| Region | Scenario | URL | Result | External proxy contacted | Origin reached | Result line |
| --- | --- | --- | --- | --- | --- | --- |
| cn-north-1 | managed-3128-default | `http://172.31.39.252:8000` | 403 | False | False | [30](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-default | `http://172.31.39.252:8081` | 403 | False | False | [32](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-default | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/26dc705312d44388acf | False | False | [35](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-explicit | `http://172.31.39.252:8000` | 403 | False | False | [40](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-explicit | `http://172.31.39.252:8081` | 403 | False | False | [42](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3128-explicit | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/a983d1eb7ba241c2bac | False | False | [45](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-default | `http://172.31.39.252:8000` | 403 | False | False | [50](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-default | `http://172.31.39.252:8081` | 403 | False | False | [52](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-default | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/8b29cd34ea6d4183914 | False | False | [55](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-explicit | `http://172.31.39.252:8000` | 403 | False | False | [60](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-explicit | `http://172.31.39.252:8081` | 403 | False | False | [62](cn-north-1-results.jsonl) |
| cn-north-1 | managed-8080-explicit | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/bb8eda8f079c48ba841 | False | False | [65](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-default | `http://172.31.39.252:8000` | 403 | False | False | [70](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-default | `http://172.31.39.252:8081` | 403 | False | False | [72](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-default | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/133adc1727cb4a5e95b | False | False | [75](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-explicit | `http://172.31.39.252:8000` | 403 | False | False | [80](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-explicit | `http://172.31.39.252:8081` | 403 | False | False | [82](cn-north-1-results.jsonl) |
| cn-north-1 | managed-3129-explicit | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/4435bb73c7b14b1faff | False | False | [85](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip | `http://172.31.39.252:8000` | 403 | False | False | [90](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip | `http://172.31.39.252:8081` | 403 | False | False | [92](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/b18b66efc21240ed956 | False | False | [95](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-hostname | `http://ip-172-31-39-252.cn-north-1.compute.internal:8000` | 403 | False | False | [100](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-hostname | `http://ip-172-31-39-252.cn-north-1.compute.internal:8081` | 403 | False | False | [102](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-hostname | `https://ip-172-31-39-252.cn-north-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-39-252.cn-north-1.compute.internal | False | False | [105](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-suffix | `http://ip-172-31-39-252.cn-north-1.compute.internal:8000` | 403 | False | False | [110](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-suffix | `http://ip-172-31-39-252.cn-north-1.compute.internal:8081` | 403 | False | False | [112](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-suffix | `https://ip-172-31-39-252.cn-north-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-39-252.cn-north-1.compute.internal | False | False | [115](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip-bad-credentials | `http://172.31.39.252:8000` | 403 | False | False | [120](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip-bad-credentials | `http://172.31.39.252:8081` | 403 | False | False | [122](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-ip-bad-credentials | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/323183c2ef154576ac7 | False | False | [125](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-and-route-ip | `http://172.31.39.252:8000` | 403 | False | False | [130](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-and-route-ip | `http://172.31.39.252:8081` | 403 | False | False | [132](cn-north-1-results.jsonl) |
| cn-north-1 | bypass-and-route-ip | `https://172.31.39.252:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.39.252:8443/probe/08a7f20008084277944 | False | False | [135](cn-north-1-results.jsonl) |
| cn-north-1 | proxy-only-dns-default | `http://proxy-only.agentcore.test:80` | 503 | False | False | [143](cn-north-1-results.jsonl) |
| cn-north-1 | proxy-only-dns-default | `https://proxy-only.agentcore.test:443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://proxy-only.agentcore.test/probe/cbe7c142b5f8 | False | False | [145](cn-north-1-results.jsonl) |
| cn-northwest-1 | managed-3128-default | `http://172.31.14.177:8000` | 403 | False | False | [30](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-default | `http://172.31.14.177:8081` | 403 | False | False | [32](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-default | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/459775a07cd44443b3d | False | False | [35](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-explicit | `http://172.31.14.177:8000` | 403 | False | False | [40](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-explicit | `http://172.31.14.177:8081` | 403 | False | False | [42](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3128-explicit | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/acdcffb74e864d41bec | False | False | [45](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-default | `http://172.31.14.177:8000` | 403 | False | False | [50](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-default | `http://172.31.14.177:8081` | 403 | False | False | [52](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-default | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/11808e94ed8244f8a6e | False | False | [55](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-explicit | `http://172.31.14.177:8000` | 403 | False | False | [60](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-explicit | `http://172.31.14.177:8081` | 403 | False | False | [62](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-8080-explicit | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/637a8aff33684e55ab0 | False | False | [65](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-default | `http://172.31.14.177:8000` | 403 | False | False | [70](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-default | `http://172.31.14.177:8081` | 403 | False | False | [72](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-default | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/618cc2d4c8c74ee880f | False | False | [75](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-explicit | `http://172.31.14.177:8000` | 403 | False | False | [80](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-explicit | `http://172.31.14.177:8081` | 403 | False | False | [82](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | managed-3129-explicit | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/b7d2a2840a664c32b9e | False | False | [85](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip | `http://172.31.14.177:8000` | 403 | False | False | [90](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip | `http://172.31.14.177:8081` | 403 | False | False | [92](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/35519e1fcf1c476ebdf | False | False | [95](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-hostname | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8000` | 403 | False | False | [100](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-hostname | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8081` | 403 | False | False | [102](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-hostname | `https://ip-172-31-14-177.cn-northwest-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-14-177.cn-northwest-1.compute.inte | False | False | [105](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-suffix | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8000` | 403 | False | False | [110](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-suffix | `http://ip-172-31-14-177.cn-northwest-1.compute.internal:8081` | 403 | False | False | [112](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-suffix | `https://ip-172-31-14-177.cn-northwest-1.compute.internal:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://ip-172-31-14-177.cn-northwest-1.compute.inte | False | False | [115](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip-bad-credentials | `http://172.31.14.177:8000` | 403 | False | False | [120](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip-bad-credentials | `http://172.31.14.177:8081` | 403 | False | False | [122](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-ip-bad-credentials | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/0f35f30be35740dc8f9 | False | False | [125](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-and-route-ip | `http://172.31.14.177:8000` | 403 | False | False | [130](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-and-route-ip | `http://172.31.14.177:8081` | 403 | False | False | [132](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | bypass-and-route-ip | `https://172.31.14.177:8443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://172.31.14.177:8443/probe/f5d0fb8d006c41ed805 | False | False | [135](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | proxy-only-dns-default | `http://proxy-only.agentcore.test:80` | 503 | False | False | [143](cn-northwest-1-results.jsonl) |
| cn-northwest-1 | proxy-only-dns-default | `https://proxy-only.agentcore.test:443` | Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://proxy-only.agentcore.test/probe/eab4a0e02747 | False | False | [145](cn-northwest-1-results.jsonl) |

No external-proxy or origin event localizes a request failure before the external fixture, but alone does not establish a specific Squid ACL. Without readable service configuration, conclusions are limited to error pages and port controls, not a confirmed AWS internal root cause.

HTTP 403 with server: squid/6.13 and x-squid-error: ERR_ACCESS_DENIED 0 confirms a managed Squid access-control rejection. ERR_TUNNEL_CONNECTION_FAILED alone does not identify the precise cause; interpret it with direct/Playwright proxy controls, port 443 controls, and absent external access logs.

## Read-only Squid diagnostics

### cn-north-1

```json
{
  "readable": false,
  "errorType": "Error",
  "message": "Page.goto: net::ERR_ACCESS_DENIED at file:///etc/squid/squid.conf\nCall log:\n  - navigating to \"file:///etc/squid/squid.conf\", waiting until \"load\"\n"
}
```

### cn-northwest-1

```json
{
  "readable": false,
  "errorType": "Error",
  "message": "Page.goto: net::ERR_ACCESS_DENIED at file:///etc/squid/squid.conf\nCall log:\n  - navigating to \"file:///etc/squid/squid.conf\", waiting until \"load\"\n"
}
```

Only /etc/squid/squid.conf was probed. Saved fields are allow-listed non-credential port/method ACLs, http_access, always_direct/never_direct, and a hash. Raw configuration was not saved and service configuration was not modified.

## Reproduction and evidence

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-followup.lock.txt
.venv/bin/python run_proxy_validation.py --results-dir results/proxy-reproduction-new
.venv/bin/python export_proxy_validation.py --results-dir results/proxy-reproduction-new
```

Use a new empty directory. A default VPC subnet and permissions for test IAM, EC2/ENIs/security groups, Secrets, and AgentCore Browser are required. The runner creates billable test resources and cleans its inventory afterward. Runner exit 0 means phases completed; individual verdicts come from this report and JSON.

- [console.log](console.log) · [phase-commands.jsonl](phase-commands.jsonl) · [environment.json](environment.json)
- [attempts.csv](attempts.csv) · [final-results.json](final-results.json) · [run-summary.json](run-summary.json)
- [validation.json](validation.json) · [artifacts.json](artifacts.json) · [source-snapshots/](source-snapshots/)

Regional *-proxy-access.json and *-origin-access.json retain server logs. *-api-audit.jsonl retains SDK requests/responses and AWS request IDs. Each navigation's sessionId, marker, response headers, errors, peer IP, and log sequence numbers are in *-observations.json.

## Cleanup status

- cn-north-1: FAIL

```json
[
  {
    "kind": "sg",
    "id": "sg-0cb10af93ab6c0181",
    "status": "EXISTS",
    "ok": false
  },
  {
    "kind": "security-group-interfaces",
    "ok": false,
    "interfaces": [
      {
        "NetworkInterfaceId": "eni-012bfc3d15172e094",
        "Status": "in-use",
        "InterfaceType": "agentic_ai",
        "Attachment": {
          "AttachmentId": "ela-attach-0cd34dbbc9512d13b",
          "DeleteOnTermination": false,
          "DeviceIndex": 1,
          "InstanceOwnerId": "amazon-aws",
          "Status": "attached"
        }
      }
    ]
  }
]
```

- cn-northwest-1: FAIL

```json
[
  {
    "kind": "sg",
    "id": "sg-02b620b4720173ddf",
    "status": "EXISTS",
    "ok": false
  },
  {
    "kind": "security-group-interfaces",
    "ok": false,
    "interfaces": [
      {
        "NetworkInterfaceId": "eni-0ee9864df5a9aeca2",
        "Status": "in-use",
        "InterfaceType": "agentic_ai",
        "Attachment": {
          "AttachmentId": "ela-attach-018cc605819d929f3",
          "DeleteOnTermination": false,
          "DeviceIndex": 1,
          "InstanceOwnerId": "amazon-aws",
          "Status": "attached"
        }
      }
    ]
  }
]
```

If security groups await AWS-managed ENI release, a background worker retries for up to 8.5 hours; see deferred-cleanup.json. This report records cleanup at export time; later worker state is authoritative. AWS-managed interfaces are not forcibly detached.

## Relationship to previous reports

The initial 09:54 setup attempt stopped and cleaned up because the default subnet assigned public addresses; no Browser checks ran. Its records are in ../proxy-validation-20260928/. This run explicitly sets ENI AssociatePublicIpAddress=False without changing subnet defaults.

The September 23 reference report uses cntest / account 447150580482, origin HTTP 8081 / HTTPS 8443, and external proxy port 8080. This run adds those combinations and standard-port controls in a different account; it does not overwrite the reference results.
- [Reference report](https://github.com/milan9527/aws-agentcore-china-tests/blob/main/COMBINED_TEST_REPORT_ZH.md)
- [AWS Browser proxy documentation](https://docs.amazonaws.cn/en_us/bedrock-agentcore/latest/devguide/browser-proxies.html)
