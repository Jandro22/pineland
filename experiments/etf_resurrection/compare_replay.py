"""Require exact CSV bytes; report numeric and state differences without tolerating them."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from inventory import sha256, write_json


def compare(original: Path, replay: Path) -> dict:
    original_bytes, replay_bytes = original.read_bytes(), replay.read_bytes()
    a = list(csv.DictReader(io.StringIO(original_bytes.decode("utf-8"))))
    b = list(csv.DictReader(io.StringIO(replay_bytes.decode("utf-8"))))
    fields: dict = {}
    for i, (left, right) in enumerate(zip(a, b)):
        for field in sorted(set(left) | set(right)):
            if left.get(field) == right.get(field):
                continue
            rec = fields.setdefault(field, {"differing_rows": 0, "first_row": i + 2,
                                            "original": left.get(field), "replay": right.get(field)})
            rec["differing_rows"] += 1
            try:
                delta = abs(float(left[field]) - float(right[field]))
                rec["max_absolute_difference"] = max(delta, rec.get("max_absolute_difference", 0.0))
            except (ValueError, TypeError):
                pass
    return {"bit_for_bit": original_bytes == replay_bytes,
            "original": str(original), "replay": str(replay),
            "original_sha256": sha256(original), "replay_sha256": sha256(replay),
            "original_rows": len(a), "replay_rows": len(b), "differing_fields": fields}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-dir", required=True, type=Path)
    p.add_argument("--replay-dir", required=True, type=Path)
    p.add_argument("--stem", default="task_0_cell_0_seed_2026200000")
    p.add_argument("--output", required=True, type=Path)
    ns = p.parse_args()
    results = {suffix: compare(ns.original_dir / (ns.stem + suffix), ns.replay_dir / (ns.stem + suffix))
               for suffix in (".csv", ".trajectory.csv")}
    out = {"schema_version": "pineland.etf.determinism.v1", "status": "PASS" if all(
        x["bit_for_bit"] for x in results.values()) else "FAIL", "files": results}
    write_json(ns.output, out)
    print(json.dumps({"status": out["status"], "files": {suffix: {
        "bit_for_bit": result["bit_for_bit"], "original_sha256": result["original_sha256"],
        "replay_sha256": result["replay_sha256"], "differing_fields": list(result["differing_fields"])}
        for suffix, result in results.items()}}, indent=2))
    raise SystemExit(out["status"] != "PASS")
