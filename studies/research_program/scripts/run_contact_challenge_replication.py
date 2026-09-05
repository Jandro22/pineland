"""Run the eight-seed synthetic contact/presence challenge without historical data.

Unlike the long transfer ensemble, this is a bounded study-layer run.  It is
allowed to record a stable *uncertified* live-source snapshot, but it never
promotes the result to historical or core-release evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from statistics import mean

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_spatial_factorial_pilot import (  # noqa: E402
    CHALLENGE_CONTRACT_PATH,
    _load_contract,
    run_cell,
    validate_contract,
)
from pineland_sim.reproducibility import (  # noqa: E402
    certified_core_status,
    file_sha256,
    model_sha256,
    repository_state,
)


def build(output: Path) -> dict:
    contract = _load_contract()
    validate_contract(contract)
    design = contract["design"]
    before = repository_state(ROOT)
    source_hash = model_sha256(ROOT)
    cells = []
    for seed in design["seeds"]:
        for memory in design["factors"]["presence_memory"]:
            for destination in design["factors"]["destination_choice"]:
                cells.append(
                    run_cell(
                        contract=contract,
                        seed=int(seed),
                        presence_memory=memory,
                        destination_choice=destination,
                        horizon_days=float(design["horizon_days"]),
                        agent_count=int(design["agent_count"]),
                        locality_count=int(design["locality_count"]),
                        challenge=True,
                    )
                )
    after = repository_state(ROOT)
    by_seed: dict[int, dict[str, dict]] = {}
    for cell in cells:
        by_seed.setdefault(int(cell["seed"]), {})[
            f"{cell['presence_memory']}|{cell['destination_choice']}"
        ] = cell
    contrasts = []
    for seed, seed_cells in sorted(by_seed.items()):
        patrol = seed_cells["government_patrol_only|current_live_policy"]["metrics"]
        memory = seed_cells["symmetric_stationary_formation_memory|current_live_policy"]["metrics"]
        contrasts.append(
            {
                "seed": seed,
                "insurgent_presence_memory_difference": (
                    memory["presence_memory_total_by_actor"]["insurgent"]
                    - patrol["presence_memory_total_by_actor"]["insurgent"]
                ),
                "same_locality_renewal_difference_7d": (
                    memory["same_locality_renewal_rate_7d"]
                    - patrol["same_locality_renewal_rate_7d"]
                    if memory["same_locality_renewal_rate_7d"] is not None
                    and patrol["same_locality_renewal_rate_7d"] is not None
                    else None
                ),
            }
        )
    all_contacts = all(cell["metrics"]["latent_contact_count"] >= 1 for cell in cells)
    memory_contrast = all(
        contrast["insurgent_presence_memory_difference"] > 0 for contrast in contrasts
    )
    integrity = (
        before["commit_hash"] == after["commit_hash"]
        and before["tracked_diff_sha256"] == after["tracked_diff_sha256"]
        and all(cell["manifest_audit"]["valid"] for cell in cells)
        and all(
            cell["manifest"]["extra"]["model_sha256_start"]
            == cell["manifest"]["extra"]["model_sha256_end"]
            for cell in cells
        )
    )
    manifest_path = output.with_name(output.stem + "_manifest.json")
    result = {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "experiment_id": contract["experiment_id"],
        "status": "eight_seed_contact_challenge_synthetic_only_uncertified_core",
        "contract_sha256": file_sha256(CHALLENGE_CONTRACT_PATH),
        "model_sha256": source_hash,
        "core_certificate": certified_core_status(ROOT),
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "seed_count": len(by_seed),
        "cell_count": len(cells),
        "all_seeds_have_latent_contacts": all_contacts,
        "presence_memory_contrast_positive_every_seed": memory_contrast,
        "mean_insurgent_presence_memory_difference": mean(
            contrast["insurgent_presence_memory_difference"] for contrast in contrasts
        ),
        "contrasts": contrasts,
        "integrity_passed": integrity,
        "scientific_acceptance_gate_passed": bool(integrity and all_contacts and memory_contrast),
        "cells": cells,
        "repository_before": before,
        "repository_after": after,
        "provenance_manifest": manifest_path.relative_to(ROOT).as_posix(),
        "interpretation": "Synthetic pathway replication only. It does not validate historical outcomes, identify actor reproduction, or license a core freeze while the live source is uncertified.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0.0",
        "status": "synthetic_replication_provenance_manifest",
        "artifact": {
            "path": output.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(output),
        },
        "builder": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": file_sha256(Path(__file__).resolve()),
        },
        "contract": {
            "path": CHALLENGE_CONTRACT_PATH.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(CHALLENGE_CONTRACT_PATH),
        },
        "model_sha256": source_hash,
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies" / "research_program" / "contact_challenge_eight_seed_replication.json",
    )
    args = parser.parse_args()
    result = build(args.output)
    print(
        json.dumps(
            {
                "status": result["status"],
                "seed_count": result["seed_count"],
                "cell_count": result["cell_count"],
                "integrity_passed": result["integrity_passed"],
                "scientific_acceptance_gate_passed": result["scientific_acceptance_gate_passed"],
                "core_certificate_passed": result["core_certificate"]["passed"],
                "output": args.output.as_posix(),
            },
            indent=2,
        )
    )
    return 0 if result["integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
