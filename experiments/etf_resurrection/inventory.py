"""Audit immutable Stage-4 shards before scoring or running new worlds.

No third-party dependencies. The raw input directory remains read-only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

BASE = Path("studies/research_program/general_theory_v1/partner_force_autonomy")
RAW_COMPONENTS = {
    "force_generation": ["interval_indigenous_recruits", "interval_indigenous_graduates",
                         "interval_external_forcegen_graduates", "interval_military_losses"],
    "logistics": ["interval_indigenous_logistics_produced", "interval_indigenous_logistics_delivered",
                  "interval_indigenous_logistics_consumed", "interval_military_logistics_demanded",
                  "interval_external_logistics_delivered", "supply_stock", "supply_capacity"],
    "command": ["command_reliability", "command_latency_hours", "interval_command_opportunities",
                "interval_command_indigenous_service", "interval_command_supported_service"],
    "state": ["military_personnel", "operational_formations", "covered_localities", "readiness"],
    "combat": ["insurgent_personnel", "insurgent_active_formations", "contested_localities",
               "interval_contacts", "interval_organized_actions", "interval_military_losses"],
}
FIELDS = sorted({f for fields in RAW_COMPONENTS.values() for f in fields})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def audit(input_dir: Path, contract_path: Path, output_dir: Path) -> dict:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    start = contract["environment"]["observation_start_days"]
    split = contract["environment"]["withdrawal_time_days"]
    pre_times = {float(start), float(split)}
    t = start + 7.0
    while t < split - 1e-9:
        pre_times.add(float(t))
        t += 7
    horizons = contract["horizons_days"]
    post_offsets = {float(h) for h in horizons}
    t = 7.0
    while t < max(horizons) - 1e-9:
        post_offsets.add(t)
        t += 7
    expected_grid = {("PRE_SUPPORTED", x) for x in pre_times}
    expected_grid |= {(phase, split + x) for phase in ("SUPPORT_ON", "SUPPORT_OFF") for x in post_offsets}
    expected = {(c["cell_id"], contract["seed_base"] + i) for c in contract["cells"]
                for i in range(contract["default_seed_count"])}
    seen: Counter = Counter()
    errors, records = [], []
    headers: Counter = Counter()
    totals: Counter = Counter()
    extrema = {field: [math.inf, -math.inf] for field in FIELDS}
    for path in sorted(input_dir.glob("*.trajectory.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers[tuple(reader.fieldnames or [])] += 1
            missing = set(FIELDS) - set(reader.fieldnames or [])
            if missing:
                errors.append(f"{path.name}: missing {sorted(missing)}")
                continue
            rows = list(reader)
        if not rows:
            errors.append(f"{path.name}: empty")
            continue
        cell, seed = rows[0]["cell_id"], int(rows[0]["seed"])
        seen[(cell, seed)] += 1
        stem = path.name.removesuffix(".trajectory.csv")
        meta_path, primary_path = input_dir / (stem + ".json"), input_dir / (stem + ".csv")
        rec = {"cell_id": cell, "seed": seed, "trajectory_file": path.name, "rows": len(rows),
               "trajectory_sha256": sha256(path), "primary_sha256": None, "metadata_verified": False}
        if meta_path.exists() and primary_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            rec["primary_sha256"] = sha256(primary_path)
            rec["metadata_verified"] = (
                meta["trajectory_sha256"] == rec["trajectory_sha256"]
                and meta["output_sha256"] == rec["primary_sha256"]
                and meta["git_commit"] == rows[0]["git_commit"]
                and meta["seed"] == seed
                and meta["stage4_contract_sha256"] == sha256(contract_path)
            )
        if not rec["metadata_verified"]:
            errors.append(f"{path.name}: metadata/hash mismatch or missing primary/metadata")
        grid = [(r["phase"], float(r["time_days"])) for r in rows]
        if len(set(grid)) != len(grid) or set(grid) != expected_grid:
            errors.append(f"{path.name}: incomplete/duplicate interval grid")
        for row in rows:
            if (row["cell_id"], int(row["seed"])) != (cell, seed):
                errors.append(f"{path.name}: mixed world identities")
            for field in FIELDS:
                val = float(row[field])
                if not math.isfinite(val):
                    errors.append(f"{path.name}: nonfinite {field}")
                extrema[field][0] = min(extrema[field][0], val)
                extrema[field][1] = max(extrema[field][1], val)
            phase = row["phase"]
            for field in ("interval_contacts", "interval_organized_actions", "interval_military_losses",
                          "interval_indigenous_graduates", "interval_indigenous_logistics_delivered"):
                value = float(row[field])
                totals[f"{phase}.{field}"] += value
                rec[f"{phase}.{field}"] = rec.get(f"{phase}.{field}", 0.0) + value
            totals[f"{phase}.rows"] += 1
            totals[f"{phase}.rows_with_active_insurgents"] += int(float(row["insurgent_active_formations"]) > 0)
            totals[f"{phase}.rows_with_contested_localities"] += int(float(row["contested_localities"]) > 0)
        records.append(rec)
    missing_worlds = sorted(expected - set(seen))
    unexpected = sorted(set(seen) - expected)
    duplicates = [list(key) for key, n in seen.items() if n > 1]
    status = "PASS" if not (errors or missing_worlds or unexpected or duplicates) else "FAIL"
    out = {
        "schema_version": "pineland.etf.telemetry_inventory.v1", "status": status,
        "module": contract["experiment_id"], "input_directory": str(input_dir.resolve()),
        "contract": str(contract_path), "contract_sha256": sha256(contract_path),
        "expected_worlds": len(expected), "observed_worlds": len(seen),
        "verified_worlds": sum(r["metadata_verified"] for r in records),
        "expected_rows_per_world": len(expected_grid), "trajectory_rows": sum(r["rows"] for r in records),
        "missing_worlds": missing_worlds, "unexpected_worlds": unexpected, "duplicate_worlds": duplicates,
        "errors": errors, "raw_components": RAW_COMPONENTS, "component_extrema": extrema,
        "schemas": [{"worlds": count, "fields": list(header)} for header, count in headers.items()],
        "phase_totals": dict(totals),
        "phase2_requires_new_simulation_for_logged_components": status != "PASS",
        "limits": ["Coverage is specific to the named module and contract.",
                   "The first day-60 row is a state snapshot with zero interval flows, not a measured interval.",
                   "Force generation is logged as recruits/graduates, logistics in model supply units, latency in hours.",
                   "Raw readiness is personnel-weighted formation readiness over all military formations. It is not the availability-weighted effective readiness over operational domestic formations used by the composite assay.",
                   "The original composite uses the own withdrawal-day baseline, not a temporal supported peak.",
                   "The old trajectory has no hashes of the two clones at the exact split and no contact-funnel counters."],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in records for key in row})
    with (output_dir / "inventory_worlds.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    write_json(output_dir / "telemetry_inventory.json", out)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", required=True, type=Path)
    p.add_argument("--contract", type=Path, default=BASE / "contracts/stage4_autonomy_phase_map_v1.json")
    p.add_argument("--output-dir", type=Path, default=Path("experiments/etf_resurrection/results"))
    ns = p.parse_args()
    result = audit(ns.input_dir, ns.contract, ns.output_dir)
    print(json.dumps({k: result[k] for k in ("status", "expected_worlds", "observed_worlds", "verified_worlds", "trajectory_rows", "phase_totals", "errors")}, indent=2))
    raise SystemExit(result["status"] != "PASS")
