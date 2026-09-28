"""Append corrected Live View verdicts with references to the completed observations."""
import json
from suite import ROOT


def latest(path):
    return {row["feature"]: row for row in
        (json.loads(line) for line in path.read_text().splitlines())}


def run(s):
    current = latest(ROOT / "results/retest-livewait-default" / f"{s.region}-results.jsonl")
    control_path = ROOT / "results/retest-live-signature" / f"{s.region}-results.jsonl"
    control = latest(control_path)["browser.live_view.default_signature_control"]
    assert control["status"] == "PASS"
    assert control["evidence"]["remoteInput"] == "dcv-official-input-ok"
    observations = []
    for attempt in ("initial_5min", "fresh_signature_retry_5min"):
        row = current["browser.live_view.extended_wait." + attempt]
        evidence = row["evidence"]
        assert evidence["signatureExpirySeconds"] == 300
        assert evidence["actualObservationSeconds"] >= 300
        assert evidence["probe"]["connected"] and evidence["probe"]["firstFrame"]
        assert all(h["sessionStatus"] == "READY" for h in evidence["heartbeats"])
        assert evidence["heartbeats"][-1]["websocket"]["receivedBytes"] > evidence["heartbeats"][1]["websocket"]["receivedBytes"]
        summary = {"attempt": attempt, "originalAttemptTime": row["time"],
            "observationSeconds": evidence["actualObservationSeconds"],
            "events": evidence["probe"]["events"], "finalWebsocketCounters": evidence["websocket"],
            "sessionId": evidence["sessionId"],
            "source": f"results/retest-livewait-default/{s.region}-results.jsonl",
            "scope": "Display connected, first frame received, incoming stream continued throughout observation",
            "inputCorrection": "Original combined check used content coordinates on a full-window stream; input separately passed with browser toolbar offset"}
        observations.append(summary)
        s.record("browser.live_view.extended_wait.display." + attempt, "PASS", summary)
    evidence = {"observations": observations, "frameAndInputControl": {
        "source": str(control_path.relative_to(ROOT)), "time": control["time"], "evidence": control["evidence"]},
        "previousVerdictCorrection": "Original harness exited on a post-success authentication-socket error before the display first frame",
        "actualFirstFrameCriterion": "Wait for display.firstFrame; record authentication-socket errors without prematurely ending the display observation"}
    for feature in ("browser.live_view.official_component", "browser.live_view.dcv_frame_and_input",
                    "browser.live_view.input"):
        s.record(feature, "PASS", evidence)
