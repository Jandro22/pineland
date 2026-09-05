"""Run and summarize the frozen, untuned opportunity-structure comparison."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from run_untuned_benchmark import DEFAULT_SEEDS, atomic_json, run_seed

STUDY = ROOT / "studies" / "nepal_2001_2006"
OUT = STUDY / "runs" / "post_structural_repair" / "opportunity_nested"
RESULTS = STUDY / "results" / "post_structural_repair" / "opportunity_structure"
VARIANTS = ("A_prior_repaired", "B_persistence", "C_decomposition",
            "D_contact_semantics", "E_combined")


def summarize(rows: list[dict]) -> dict:
    attempts = [len(row["contacts"]) for row in rows]
    latent = [row["realized_contact_count"] for row in rows]
    recorded = [row["recorded_realized_contact_count"] for row in rows]
    active_cells = []
    recorded_active_cells = []
    for row in rows:
        cells = {(item["district_id"], int(item["day"] // 7))
                 for item in row["contacts"] if item["realized"]}
        recorded_cells = {(item["district_id"], int(item["day"] // 7))
                          for item in row["contacts"] if item["realized"] and item["recorded"]}
        assert len(recorded_cells) <= row["recorded_realized_contact_count"] <= row["realized_contact_count"]
        active_cells.append(len(cells))
        recorded_active_cells.append(len(recorded_cells))
    initial_insurgent = [sum(f["organization_id"] == "insurgent"
                             for f in row["initial_formations"]) for row in rows]
    final_active = [sum(f["organization_id"] == "insurgent" and
                        f["organization_status"] == "active"
                        for f in row["final_formations"]) for row in rows]
    return {
        "trajectories": len(rows), "scheduled_opportunities": sum(attempts),
        "mean_opportunities_per_trajectory": sum(attempts) / len(rows),
        "latent_engagements": sum(latent), "recorded_engagements": sum(recorded),
        "latent_active_district_weeks": sum(active_cells),
        "mean_latent_active_district_weeks_per_trajectory": sum(active_cells) / len(rows),
        "mean_latent_active_district_week_share": sum(active_cells) / (len(rows) * 75 * 261),
        "recorded_active_district_weeks": sum(recorded_active_cells),
        "mean_recorded_active_district_weeks_per_trajectory": sum(recorded_active_cells) / len(rows),
        "mean_recorded_active_district_week_share": sum(recorded_active_cells) / (len(rows) * 75 * 261),
        "zero_engagement_trajectories": sum(value == 0 for value in latent),
        "initial_insurgent_formations": sorted(set(initial_insurgent)),
        "final_active_insurgent_formations": final_active,
        "runtime_seconds_sum": sum(row["runtime_seconds"] for row in rows),
    }


def historical_contract() -> dict:
    path = STUDY / "data" / "processed" / "district_week_panel.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    counts = [int(row["government_maoist_state_based_events"]) for row in rows]
    return {
        "common_estimand": "district-week any state-based government-CPN-M event",
        "raw_ged_row_count_diagnostic_only": sum(counts),
        "active_district_weeks": sum(value > 0 for value in counts),
        "total_district_weeks": len(counts),
        "active_share": sum(value > 0 for value in counts) / len(counts),
        "reason": "Pineland formation engagement and UCDP GED row multiplicity lack an identified one-to-one bridge.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--agent-count", type=int, default=750)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    jobs = []
    for variant in VARIANTS:
        directory = OUT / variant
        directory.mkdir(parents=True, exist_ok=True)
        for seed in DEFAULT_SEEDS:
            path = directory / f"seed_{seed}_agents_{args.agent_count}.json"
            if args.force or not path.exists():
                jobs.append((variant, seed, path))
    started = time.perf_counter()
    if jobs:
        with ProcessPoolExecutor(max_workers=min(args.workers, len(jobs))) as pool:
            futures = {pool.submit(run_seed, seed, args.agent_count, variant): (variant, seed, path)
                       for variant, seed, path in jobs}
            for future in as_completed(futures):
                variant, seed, path = futures[future]
                payload = future.result()
                atomic_json(path, payload)
                print(json.dumps({"variant": variant, "seed": seed,
                                  "runtime_seconds": payload["runtime_seconds"],
                                  "latent": payload["realized_contact_count"]}), flush=True)
    nested = {}
    for variant in VARIANTS:
        rows = [json.loads((OUT / variant / f"seed_{seed}_agents_{args.agent_count}.json").read_text())
                for seed in DEFAULT_SEEDS]
        nested[variant] = summarize(rows)
    payload = {
        "schema_version": "1.0.0", "parameter_fit": False,
        "formulation_tag": "post_structural_repair_v1",
        "selection_rule": "E was selected before outcomes as the theory-preferred combination",
        "agent_count": args.agent_count, "seeds": list(DEFAULT_SEEDS),
        "wall_seconds": time.perf_counter() - started,
        "historical_measurement_contract": historical_contract(),
        "variants": nested,
    }
    atomic_json(RESULTS / "nested_untuned_summary.json", payload)
    print(json.dumps({"output": str(RESULTS / "nested_untuned_summary.json"),
                      "wall_seconds": payload["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
