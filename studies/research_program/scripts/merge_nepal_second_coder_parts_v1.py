"""Merge blind second-coder shards without consulting first-coder labels."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "studies/research_program/nepal_second_coder_packet_v1.csv"
PARTS = [ROOT / f"studies/research_program/nepal_second_coder_part_{i}_v1.csv" for i in range(1, 5)]
OUT = ROOT / "studies/research_program/nepal_second_coder_completed_v1.csv"
MANIFEST = ROOT / "studies/research_program/nepal_second_coder_merge_manifest_v1.json"
LOCK = ROOT / "studies/research_program/nepal_second_coder_shard_lock_v1.json"


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    packet_rows, fields = read_csv(PACKET)
    expected = {row["blind_id"] for row in packet_rows}
    if not LOCK.exists():
        raise SystemExit(f"missing pre-unblinding shard lock: {LOCK}")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    locked_hashes = lock.get("shard_sha256", {})
    merged = []
    part_meta = []
    for index, path in enumerate(PARTS, 1):
        if not path.exists():
            raise SystemExit(f"missing shard: {path}")
        current_sha = sha(path)
        expected_sha = locked_hashes.get(str(index))
        if not expected_sha or current_sha != expected_sha:
            raise SystemExit(
                f"shard changed after pre-unblinding lock: part={index} "
                f"expected={expected_sha} actual={current_sha}"
            )
        rows, shard_fields = read_csv(path)
        if shard_fields != fields:
            raise SystemExit(f"header mismatch: {path}")
        part_meta.append({"path": path.relative_to(ROOT).as_posix(), "sha256": current_sha, "rows": len(rows)})
        merged.extend(rows)
    ids = [row["blind_id"] for row in merged]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate blind_id across shards")
    if set(ids) != expected:
        raise SystemExit(f"blind_id partition mismatch: missing={sorted(expected-set(ids))} extra={sorted(set(ids)-expected)}")
    required = [
        "coder_date_start", "coder_date_end", "actor_id", "observable", "value_or_category",
        "spatial_scope", "temporal_precision", "confidence", "coding_rationale", "second_coder"
    ]
    incomplete = []
    for row in merged:
        for field in required:
            # NOT_ADMISSIBLE rows still require every field; use explicit N/A where needed.
            if not str(row.get(field, "")).strip():
                incomplete.append({"blind_id": row["blind_id"], "field": field})
    if incomplete:
        raise SystemExit("incomplete coder fields: " + json.dumps(incomplete[:20]))
    order = {row["blind_id"]: i for i, row in enumerate(packet_rows)}
    merged.sort(key=lambda row: order[row["blind_id"]])
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(merged)
    manifest = {
        "schema_version": "pineland.nepal_second_coder_merge_manifest.v1",
        "status": "blind_second_coder_file_locked_before_unblinding",
        "packet_sha256": sha(PACKET),
        "shard_lock": LOCK.relative_to(ROOT).as_posix(),
        "shard_lock_sha256": sha(LOCK),
        "parts": part_meta,
        "completed_path": OUT.relative_to(ROOT).as_posix(),
        "completed_sha256": sha(OUT),
        "row_count": len(merged),
        "unique_blind_ids": len(set(ids)),
        "first_coder_or_blind_key_read_by_merge": False
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
