"""Archive the eight adjudicated Nepal construct-evidence sources with hashes.

This writes a supplemental study-layer archive/manifest.  It deliberately does
not edit the frozen case source manifest used by the historical confrontation.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_adjudicated_v1.csv"
ARCHIVE_DIR = ROOT / "studies/nepal_2001_2006/data/raw/control_presence_sources_v1"
MANIFEST = ROOT / "studies/research_program/nepal_construct_source_archive_manifest_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extension(url: str) -> str:
    lower = url.lower()
    if ".pdf" in lower:
        return ".pdf"
    return ".html"


def main() -> int:
    with EVIDENCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    sources = {}
    for row in rows:
        sources.setdefault(row["source_id"], {
            "source_id": row["source_id"],
            "source_title": row["source_title"],
            "publisher": row["publisher"],
            "url": row["source_url_or_archive_ref"],
        })

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for source_id in sorted(sources):
        source = sources[source_id]
        target = ARCHIVE_DIR / f"{source_id}{extension(source['url'])}"
        temp = target.with_suffix(target.suffix + ".part")
        if temp.exists():
            temp.unlink()
        headers = ARCHIVE_DIR / f"{source_id}.headers.txt"
        command = [
            "curl.exe", "-L", "--fail", "--silent", "--show-error", "--compressed",
            "--connect-timeout", "15", "--max-time", "90",
            "-A", "Mozilla/5.0 PinelandResearchArchive/1.0",
            "-D", str(headers), "-o", str(temp), source["url"],
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        result = dict(source)
        result.update({
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "curl_exit_code": completed.returncode,
            "curl_stderr": completed.stderr.strip(),
            "archive_path": None,
            "archive_sha256": None,
            "archive_bytes": 0,
            "headers_path": headers.relative_to(ROOT).as_posix() if headers.exists() else None,
            "retrieval_status": "failed",
        })
        if completed.returncode == 0 and temp.exists() and temp.stat().st_size > 0:
            temp.replace(target)
            result.update({
                "archive_path": target.relative_to(ROOT).as_posix(),
                "archive_sha256": sha256(target),
                "archive_bytes": target.stat().st_size,
                "retrieval_status": "archived",
            })
        elif temp.exists():
            temp.unlink()
        results.append(result)

    payload = {
        "schema_version": "pineland.nepal_construct_source_archive_manifest.v1",
        "status": "supplemental_source_archive_not_frozen_case_input",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_csv": EVIDENCE.relative_to(ROOT).as_posix(),
        "evidence_csv_sha256": sha256(EVIDENCE),
        "archive_directory": ARCHIVE_DIR.relative_to(ROOT).as_posix(),
        "source_count": len(results),
        "archived_count": sum(item["retrieval_status"] == "archived" for item in results),
        "failed_count": sum(item["retrieval_status"] != "archived" for item in results),
        "sources": results,
        "rules": [
            "Exact downloaded bytes are hashed; no content normalization or OCR is performed.",
            "Retrieval failure is preserved explicitly and is not replaced by a different document.",
            "This supplemental manifest does not amend historical case inputs or predictive results."
        ]
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_count": payload["source_count"],
        "archived_count": payload["archived_count"],
        "failed_count": payload["failed_count"],
        "manifest": MANIFEST.relative_to(ROOT).as_posix(),
        "sources": [
            {"source_id": item["source_id"], "status": item["retrieval_status"],
             "bytes": item["archive_bytes"], "sha256": item["archive_sha256"],
             "error": item["curl_stderr"]}
            for item in results
        ]
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
