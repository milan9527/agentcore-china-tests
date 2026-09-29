"""Redact completed-run evidence locally while preserving JSONL row order and verdicts."""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile

from export_report import sanitize

TEXT_SUFFIXES = {".json", ".jsonl", ".csv", ".log", ".txt", ".html"}
IDENTITY_KEYS = ("time", "region", "feature", "status", "seconds")


def clean_text(path, text):
    if path.suffix == ".json":
        return json.dumps(sanitize(json.loads(text)), ensure_ascii=False, indent=2) + "\n"
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines()]
        cleaned = sanitize(rows)
        assert len(rows) == len(cleaned)
        for before, after in zip(rows, cleaned):
            assert all(before.get(key) == after.get(key) for key in IDENTITY_KEYS)
        return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in cleaned)
    if path.suffix == ".csv":
        output = io.StringIO()
        csv.writer(output).writerows(
            [sanitize(cell) for cell in row] for row in csv.reader(io.StringIO(text)))
        return output.getvalue()
    return sanitize(text)


def redact_directory(directory):
    directory = Path(directory).resolve()
    changes = []
    for path in sorted(directory.rglob("*")):
        if (not path.is_file() or path.is_symlink() or "source-snapshots" in path.parts
                or path.suffix not in TEXT_SUFFIXES
                or path.name in {"redaction-report.json", "followup-artifacts.json"}):
            continue
        before_stat = path.stat()
        before = path.read_bytes()
        text = before.decode("utf-8")
        # Avoid rewriting unchanged JSON merely to change its formatting.
        cleaned = clean_text(path, text)
        changed = (sanitize(json.loads(text)) != json.loads(text) if path.suffix == ".json"
                   else any(sanitize(json.loads(line)) != json.loads(line) for line in text.splitlines())
                   if path.suffix == ".jsonl" else cleaned != text)
        if not changed:
            continue
        after = cleaned.encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
            temp.write(after)
            temporary = Path(temp.name)
        try:
            current = path.stat()
            if (current.st_ino, current.st_mtime_ns, current.st_size) != (
                    before_stat.st_ino, before_stat.st_mtime_ns, before_stat.st_size):
                raise RuntimeError(f"Evidence changed concurrently; retry after its writer stops: {path}")
            temporary.chmod(before_stat.st_mode & 0o777)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        changes.append({
            "path": str(path.relative_to(directory)),
            "beforeSha256": hashlib.sha256(before).hexdigest(),
            "afterSha256": hashlib.sha256(after).hexdigest(),
        })
    report_path = directory / "redaction-report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {"runs": []}
    report["runs"].append({
        "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        "changes": changes,
        "preserved": list(IDENTITY_KEYS),
        "sourceSnapshotsModified": False,
    })
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return {"directory": str(directory), "changedFiles": len(changes)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(redact_directory(args.directory)))


if __name__ == "__main__":
    main()
