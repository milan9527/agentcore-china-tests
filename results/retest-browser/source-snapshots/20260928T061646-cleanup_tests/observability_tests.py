import datetime as dt
import json
import secrets
import time
from gateway_tests import call
from browser_tests import start, stop, connect


def delivery(s, component, arn, log_type):
    logs = s.client("logs")
    group = "/aws/vendedlogs/bedrock-agentcore/cn-test/" + s.name + "-" + component
    logs.create_log_group(logGroupName=group, tags={"Purpose": s.name})
    s.resource("log-group", group)
    logs.put_retention_policy(logGroupName=group, retentionInDays=1)
    source_name = s.name + "-" + component + "-source"
    dest_name = s.name + "-" + component + "-dest"
    source = logs.put_delivery_source(name=source_name, resourceArn=arn, logType=log_type)
    s.resource("delivery-source", source_name)
    dest = logs.put_delivery_destination(name=dest_name, deliveryDestinationType="CWL",
        deliveryDestinationConfiguration={"destinationResourceArn": f"arn:aws-cn:logs:{s.region}:{s.account}:log-group:{group}"},
        outputFormat="json")
    s.resource("delivery-destination", dest_name)
    d = logs.create_delivery(deliverySourceName=source_name, deliveryDestinationArn=dest["deliveryDestination"]["arn"])
    s.resource("delivery", d["delivery"]["id"])
    s.state[component + "_log_group"] = group
    s.save()
    return {"logGroup": group, "deliveryId": d["delivery"]["id"]}


def run(s):
    gw = s.state["gateway"]
    s.test("gateway.observability.log_delivery_configure", lambda: delivery(s, "gateway", gw["gatewayArn"], "APPLICATION_LOGS"))
    browser = s.control.get_browser(browserId=s.state["custom_browser"])
    s.test("browser.observability.usage_log_configure", lambda: delivery(s, "browser", browser["browserArn"], "USAGE_LOGS"))
    trace = f"1-{int(time.time()):08x}-{secrets.token_hex(12)}"
    for n in range(3):
        s.test("gateway.observability.traced_invocation", lambda: call(s, "lambda-inline___add", {"a": 20, "b": 22}, "42",
            extra_headers={"X-Amzn-Trace-Id": "Root=" + trace + ";Parent=" + secrets.token_hex(8) + ";Sampled=1"}))
    r = start(s, s.state["custom_browser"])
    stop(s, r)
    cw = s.client("cloudwatch")
    all_metrics = []
    for page in cw.get_paginator("list_metrics").paginate(Namespace="AWS/Bedrock-AgentCore"):
        all_metrics.extend(page["Metrics"])
    for component, marker in [("gateway", gw["gatewayArn"]), ("browser", browser["browserArn"])]:
        def metrics(comp=component, resource=marker):
            selected = [x for x in all_metrics if any(d["Value"] in [resource, resource.split("/")[-1]] for d in x["Dimensions"])]
            assert selected, {"resource": resource, "metricCountInNamespace": len(all_metrics)}
            evidence = []
            for metric in selected[:10]:
                data = cw.get_metric_statistics(Namespace=metric["Namespace"], MetricName=metric["MetricName"], Dimensions=metric["Dimensions"],
                    StartTime=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2), EndTime=dt.datetime.now(dt.timezone.utc),
                    Period=60, Statistics=["Sum", "Average"])
                evidence.append({"metric": metric, "datapoints": data["Datapoints"][-5:]})
            assert any(x["datapoints"] for x in evidence), evidence
            return {"metricCount": len(selected), "samples": evidence}
        s.test(component + ".observability.metrics", metrics)
    for component, event_name in [("gateway", "CreateGateway"), ("browser", "CreateBrowser")]:
        def cloudtrail(event=event_name):
            response = s.client("cloudtrail").lookup_events(LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": event}],
                StartTime=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3), MaxResults=50)
            events = []
            for e in response["Events"]:
                body = json.loads(e["CloudTrailEvent"])
                if s.name in json.dumps(body) or s.name.replace("-", "_") in json.dumps(body):
                    events.append({"eventId": e["EventId"], "eventName": e["EventName"], "eventTime": e["EventTime"],
                                   "eventSource": body.get("eventSource"), "awsRegion": body.get("awsRegion")})
            assert events, {"matchingEvents": 0}
            return events
        s.test(component + ".observability.cloudtrail", cloudtrail)
    for component in ["gateway", "browser"]:
        group = s.state.get(component + "_log_group")
        if not group:
            continue
        def logs(group=group):
            deadline = time.monotonic() + 150
            while True:
                result = s.client("logs").filter_log_events(logGroupName=group, limit=10)
                if result.get("events"):
                    # Log payloads may include caller headers; retain only structure and event IDs.
                    return [{"eventId": x["eventId"], "timestamp": x["timestamp"],
                        "keys": list(json.loads(x["message"])) if x["message"].startswith("{") else ["text"],
                        "bytes": len(x["message"])} for x in result["events"]]
                if time.monotonic() > deadline:
                    raise TimeoutError("No delivered events within 150 seconds: " + group)
                time.sleep(5)
        s.test(component + ".observability.log_delivery_received", logs)
    ttl = s.state.get("ttl_session")
    if ttl:
        def expired():
            r = s.runtime.get_browser_session(browserIdentifier="aws.browser.v1", sessionId=ttl["id"])
            assert r["status"] in ["TERMINATED", "TIMED_OUT"], r
            return r
        s.test("browser.ttl.auto_termination", expired)
