"""Acquire and hash the Afghan War Diary without inspecting event rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
import urllib.request


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT
    / "studies/research_program/afghanistan_awd_2007_independent_holdout_contract_v1.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate_file(metadata: dict) -> dict:
    files = list(metadata.get("files") or [])
    candidates = []
    for row in files:
        name = str(row.get("name") or "")
        lower = name.casefold()
        if not lower.endswith((".7z", ".zip", ".csv")):
            continue
        if any(token in lower for token in ("meta", "thumb", "sqlite")):
            continue
        size = int(row.get("size") or 0)
        score = (
            int("afg" in lower or "afghan" in lower),
            int(lower.endswith(".7z")),
            size,
        )
        candidates.append((score, row))
    if not candidates:
        raise RuntimeError("Internet Archive item contains no CSV/archive candidate")
    return max(candidates, key=lambda item: item[0])[1]


def acquire(output_dir: Path) -> dict:
    contract_bytes = CONTRACT.read_bytes()
    contract = json.loads(contract_bytes)
    if not contract.get(
        "created_before_war_diary_event_rows_acquired_for_pineland"
    ):
        raise RuntimeError("War Diary mapping contract is not pre-acquisition")
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_url = contract["source"]["archive_metadata_url"]
    with urllib.request.urlopen(metadata_url) as response:
        metadata_bytes = response.read()
    metadata = json.loads(metadata_bytes)
    selected = _candidate_file(metadata)
    name = selected["name"]
    destination = output_dir / Path(name).name
    download_url = (
        contract["source"]["archive_download_base"]
        + quote(name)
    )
    urllib.request.urlretrieve(download_url, destination)
    payload = {
        "schema_version": "pineland.afghanistan.awd_acquisition_manifest.v1",
        "event_rows_inspected_by_acquisition": False,
        "contract_path": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "selected_archive_member": {
            "name": name,
            "declared_size": int(selected.get("size") or 0),
        },
        "artifact": {
            "path": str(destination.resolve().relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(destination),
            "bytes": destination.stat().st_size,
        },
    }
    manifest = output_dir / "acquisition_manifest.json"
    manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
