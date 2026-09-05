"""Materialize outcome-blind geographic holdout IDs from frozen boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[3]


def select(ids: list[str]) -> tuple[list[str], str]:
    selected = []
    for value in sorted(set(ids)):
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        if int(digest[:8], 16) % 5 == 0:
            selected.append(value)
    rule_hash = hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()
    return selected, rule_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--id-field", default="GID_2")
    args = parser.parse_args()
    case_root = args.case if args.case.is_absolute() else ROOT / args.case
    archives = list((case_root / "data" / "raw").glob("gadm*.zip"))
    if len(archives) != 1:
        raise SystemExit("expected exactly one GADM archive")
    with zipfile.ZipFile(archives[0]) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".json"))
        features = json.load(archive.open(member))["features"]
    ids = [str(feature["properties"][args.id_field]) for feature in features]
    selected, boundary_hash = select(ids)
    contract = json.loads((case_root / "config" / "case_contract.json").read_text(encoding="utf-8"))
    payload = {
        "schema_version": "1.0.0",
        "case_id": contract["case_id"],
        "status": "frozen_materialized",
        "selection_rule": "SHA-256 canonical geography ID modulo 5 equals 0; outcome-blind",
        "id_field": args.id_field,
        "all_units": sorted(set(ids)),
        "selected_holdout_units": selected,
        "selected_count": len(selected),
        "unit_count": len(set(ids)),
        "boundary_id_list_sha256": boundary_hash,
        "temporal": contract["holdouts"]["temporal"],
        "joint": contract["holdouts"]["joint"],
        "refit": False,
    }
    path = case_root / "config" / "holdout_manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "selected_count": len(selected), "unit_count": len(set(ids))}, indent=2))


if __name__ == "__main__":
    main()
