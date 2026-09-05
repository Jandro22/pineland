"""Acquire the public Nepal GeoNames gazetteer used for settlement anchors."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
RAW = STUDY / "data" / "raw"
PROCESSED = STUDY / "data" / "processed"
URL = "https://download.geonames.org/export/dump/NP.zip"
DESTINATION = RAW / "geonames_NP.zip"
MANIFEST = PROCESSED / "geonames_manifest.json"
LEGACY_MANIFEST = RAW / "geonames_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    previous_path = MANIFEST if MANIFEST.exists() else LEGACY_MANIFEST
    previous = (json.loads(previous_path.read_text(encoding="utf-8"))
                if previous_path.exists() else {})
    downloaded = False
    if args.force or not DESTINATION.exists():
        temporary = DESTINATION.with_suffix(".tmp")
        urllib.request.urlretrieve(URL, temporary)
        temporary.replace(DESTINATION)
        downloaded = True
    with zipfile.ZipFile(DESTINATION) as archive:
        if "NP.txt" not in archive.namelist():
            raise RuntimeError("GeoNames Nepal archive does not contain NP.txt")
    payload = {
        "schema_version": "1.0.0",
        "source": "GeoNames Nepal country dump",
        "url": URL,
        "retrieved_at_utc": (now if downloaded else previous.get("retrieved_at_utc")),
        "verified_at_utc": now,
        "downloaded_this_invocation": downloaded,
        "sha256": sha256(DESTINATION),
        "use_in_study": (
            "settlement names, coordinates, feature class/code, and administrative "
            "codes only; GeoNames population is excluded from model weighting"
        ),
        "study_period_outcomes_used": False,
    }
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
