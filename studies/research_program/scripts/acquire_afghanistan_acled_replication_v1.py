"""Acquire and hash the frozen archival ACLED Afghanistan replication bundle.

This acquisition stage does not extract or inspect event rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT
    / "studies/research_program/afghanistan_acled_independent_measurement_contract_v1.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire(output_dir: Path) -> dict:
    contract_bytes = CONTRACT.read_bytes()
    contract = json.loads(contract_bytes)
    if not contract.get("created_before_replication_event_rows_inspected_for_pineland"):
        raise RuntimeError("ACLED mapping contract is not marked pre-row-inspection")
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = output_dir / "ACLEDPaperReplication.zip"
    metadata = output_dir / "ACLEDMetaData.txt"
    urllib.request.urlretrieve(contract["source"]["bundle_url"], bundle)
    urllib.request.urlretrieve(contract["source"]["metadata_url"], metadata)
    payload = {
        "schema_version": "pineland.afghanistan.acled_acquisition_manifest.v1",
        "event_rows_inspected_by_acquisition": False,
        "contract_path": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "artifacts": {
            "bundle": {
                "path": str(bundle.resolve()),
                "sha256": sha256(bundle),
                "bytes": bundle.stat().st_size
            },
            "metadata": {
                "path": str(metadata.resolve()),
                "sha256": sha256(metadata),
                "bytes": metadata.stat().st_size
            }
        }
    }
    manifest = output_dir / "acquisition_manifest.json"
    manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
