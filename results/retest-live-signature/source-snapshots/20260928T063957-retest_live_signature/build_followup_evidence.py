"""Export chronological history, final follow-up matrix, cleanup, and source hashes."""
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
from export_report import sanitize

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/"results"
FOLDERS=[RESULTS,RESULTS/"retest",RESULTS/"retest-browser"]


def main():
    history=[]
    latest={}
    for folder in FOLDERS:
        for path in folder.glob("*-results.jsonl"):
            for line,text in enumerate(path.read_text().splitlines(),1):
                row=sanitize(json.loads(text))
                row.update(source=str(path.relative_to(ROOT)),sourceLine=line)
                history.append(row)
                if folder!=RESULTS:
                    key=row["region"],row["feature"]
                    if key not in latest or row["time"]>latest[key]["time"]:latest[key]=row
    history.sort(key=lambda x:(x["time"],x["region"],x["sourceLine"]))
    (RESULTS/"followup-history.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in history))
    final=sorted(latest.values(),key=lambda x:(x["feature"],x["region"]))
    (RESULTS/"followup-latest.json").write_text(json.dumps(final,ensure_ascii=False,indent=2))
    with (RESULTS/"followup-matrix.csv").open("w",newline="") as f:
        writer=csv.writer(f);writer.writerow(["feature","region","status","time","source","sourceLine","evidence"])
        for row in final:
            if not row["feature"].endswith(".suite"):
                writer.writerow([row[k] for k in ["feature","region","status","time","source","sourceLine"]]+
                                [json.dumps(row["evidence"],ensure_ascii=False)])
    cleanup={"generatedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"runs":[]}
    for folder in FOLDERS:
        for path in sorted(folder.glob("*-state.json")):
            state=json.loads(path.read_text())
            verification=folder/f"{state['region']}-cleanup-verification.json"
            item={"directory":str(folder.relative_to(ROOT)),"region":state["region"],
                "recordedResources":len(state["resources"]),"deletedResources":sum(bool(r.get("deleted")) for r in state["resources"]),
                "remainingRecordedResources":[r for r in state["resources"] if not r.get("deleted")]}
            if verification.exists():item["verification"]=json.loads(verification.read_text())
            deferred=folder/"deferred-cleanup.json"
            if deferred.exists():item["deferredCleanup"]=json.loads(deferred.read_text())
            cleanup["runs"].append(item)
    (RESULTS/"followup-cleanup.json").write_text(json.dumps(sanitize(cleanup),indent=2))
    files=list(ROOT.glob("*.py"))+list(ROOT.glob("*.md"))+list(ROOT.glob("*requirements*"))+[
        ROOT/"requirements-followup.lock.txt",ROOT/"requirements-pw148.lock.txt",ROOT/"retest-viewer/package-lock.json",
        ROOT/"retest-viewer/package.json",ROOT/"retest-viewer/main.jsx",
        ROOT/"retest-viewer/dcv-probe.js",ROOT/"retest-viewer/build.mjs",ROOT/"retest-viewer/index.html"]
    files += list((RESULTS/"retest/source-snapshots").rglob("manifest.json"))
    files += list((RESULTS/"retest-browser/source-snapshots").rglob("manifest.json"))
    manifests={str(path.relative_to(ROOT)):{"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}
               for path in sorted(set(files)) if path.exists()}
    audits={}
    for folder in FOLDERS[1:]:
        for path in folder.glob("*-api-audit.jsonl"):
            rows=[json.loads(x) for x in path.read_text().splitlines()]
            audits[str(path.relative_to(ROOT))]={"rows":len(rows),"first":rows[0]["time"] if rows else None,
                                               "last":rows[-1]["time"] if rows else None}
    evidence_files=[p for folder in FOLDERS for p in folder.iterdir()
                    if p.is_file() and p.suffix in {".json",".jsonl",".csv",".png",".bin",".txt",".html",".log"}
                    and p.name not in {"followup-artifacts.json","deferred-cleanup.json","deferred-cleanup.log","delivery-validation.json"}]
    evidence_hashes={str(p.relative_to(ROOT)):{"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                                              "bytes":p.stat().st_size} for p in sorted(set(evidence_files))}
    (RESULTS/"followup-artifacts.json").write_text(json.dumps({
        "generatedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"files":manifests,"apiAuditCoverage":audits,
        "evidenceFiles":evidence_hashes,
        "hashScope":"Snapshot at generatedAt. Deferred cleanup may later append records and refresh cleanup/report files.",
        "historyRows":len(history),"latestFollowupChecks":len(final),
        "countsIncludeDiagnosticsAndCleanup":dict(collections.Counter(r["status"] for r in final))},indent=2))
    print(json.dumps({"historyRows":len(history),"latestFollowupChecks":len(final),"sourceFilesAndManifests":len(manifests)}))


if __name__=="__main__":main()
