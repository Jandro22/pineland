"""Run a preregistered synthetic ensemble of locality-reproduction genealogies.

This is a study-layer diagnostic. It never reads historical outcomes and does
not alter model parameters in response to results. Each run estimates a typed
next-generation operator from the observation-only activation genealogy and
reports both its declared-parent lower Perron root and a conservative upper
root for unresolved parentage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (SRC, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pineland_sim import SimulationConfig  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256  # noqa: E402
from trace_locality_activation_genealogy import trace_simulation  # noqa: E402
from estimate_insurgent_reproduction import (  # noqa: E402
    estimate,
    estimate_multitype_reproduction,
)


DEFAULT_SEEDS = tuple(range(2026090501, 2026090509))


def run_ensemble(
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    agent_count: int = 800,
    locality_count: int = 34,
    horizon_days: float = 90.0,
    reproduction_horizon_days: float = 30.0,
    parent_overlap_days: float = 7.0,
) -> dict[str, Any]:
    if not seeds:
        raise ValueError("at least one seed is required")
    if reproduction_horizon_days <= 0 or horizon_days <= reproduction_horizon_days:
        raise ValueError("run horizon must exceed the positive reproduction horizon")
    if parent_overlap_days < 0:
        raise ValueError("parent overlap cannot be negative")

    source_hash_start = model_sha256(ROOT)
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        if model_sha256(ROOT) != source_hash_start:
            raise RuntimeError("model source changed during reproduction ensemble; ensemble rejected")
        config = SimulationConfig(
            agent_count=agent_count,
            locality_count=locality_count,
            horizon_days=horizon_days,
            seed=int(seed),
            output_mode="ensemble",
            random_stream_namespace="baseline",
        )
        genealogy = trace_simulation(config, until=horizon_days)
        scalar = estimate(
            genealogy["episodes"],
            parent_edges=genealogy["parent_edges"],
            horizon_days=reproduction_horizon_days,
            bootstrap=0,
            minimum_parent_overlap_days=parent_overlap_days,
        )
        typed = estimate_multitype_reproduction(
            genealogy["episodes"],
            genealogy["parent_edges"],
            horizon_days=reproduction_horizon_days,
            minimum_parent_overlap_days=parent_overlap_days,
        )
        coverage = genealogy["parentage_coverage"]
        nonroot = int(coverage["nonroot_episodes"])
        parented = int(coverage["parented_nonroot_episodes"])
        rows.append({
            "seed": int(seed),
            "episode_counts": genealogy["episode_counts"],
            "cause_counts": genealogy["cause_counts"],
            "parentage_coverage": {
                **coverage,
                "fraction": parented / nonroot if nonroot else 1.0,
            },
            "scalar_R_I": {
                "gross": scalar["gross_estimate"],
                "net": scalar["estimate"],
                "root_weight": scalar["root_viable_activation_weight"],
                "unattributed_weight": scalar["unattributed_viable_child_weight"],
                "same_time_cross_type_weight": scalar[
                    "same_time_cross_type_transition_weight_excluded_from_scalar_R_I"
                ],
            },
            "typed_R_I": {
                "matrix": typed["matrix"],
                "lower_spectral_radius": typed["spectral_radius_lower_bound"],
                "conservative_upper_spectral_radius": typed[
                    "conservative_upper_bound_spectral_radius"
                ],
                "criticality_identification": typed["criticality_identification"],
                "unresolved_nonroot_viable_activation_count": typed[
                    "unresolved_nonroot_viable_activation_count"
                ],
                "unresolved_temporally_parentable_activation_count": typed[
                    "unresolved_temporally_parentable_activation_count"
                ],
            },
        })

    source_hash_end = model_sha256(ROOT)
    if source_hash_end != source_hash_start:
        raise RuntimeError("model source changed during reproduction ensemble; ensemble rejected")

    lowers = [row["typed_R_I"]["lower_spectral_radius"] for row in rows]
    uppers = [row["typed_R_I"]["conservative_upper_spectral_radius"] for row in rows]
    coverage_values = [row["parentage_coverage"]["fraction"] for row in rows]
    identifications = [row["typed_R_I"]["criticality_identification"] for row in rows]
    return {
        "schema_version": "pineland.locality_reproduction.synthetic_ensemble.v1",
        "scientific_status": "synthetic_robustness_diagnostic_not_general_theory_claim",
        "historical_outcomes_used": False,
        "empirical_parameter_fitting": False,
        "negative_results_must_be_preserved": True,
        "predeclared_design": {
            "seeds": list(seeds),
            "agent_count": agent_count,
            "locality_count": locality_count,
            "horizon_days": horizon_days,
            "reproduction_horizon_days": reproduction_horizon_days,
            "parent_overlap_days": parent_overlap_days,
        },
        "model_sha256_start": source_hash_start,
        "model_sha256_end": source_hash_end,
        "script_sha256": file_sha256(Path(__file__)),
        "runs": rows,
        "summary": {
            "run_count": len(rows),
            "identified_subcritical_count": identifications.count("identified_subcritical"),
            "identified_supercritical_count": identifications.count("identified_supercritical"),
            "partially_identified_count": identifications.count(
                "partially_identified_across_criticality_threshold"
            ),
            "lower_spectral_radius_mean": mean(lowers),
            "lower_spectral_radius_median": median(lowers),
            "lower_spectral_radius_max": max(lowers),
            "conservative_upper_spectral_radius_mean": mean(uppers),
            "conservative_upper_spectral_radius_median": median(uppers),
            "conservative_upper_spectral_radius_max": max(uppers),
            "parentage_coverage_mean": mean(coverage_values),
            "all_runs_conservative_upper_below_one": all(value < 1.0 for value in uppers),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(DEFAULT_SEEDS))
    parser.add_argument("--agents", type=int, default=800)
    parser.add_argument("--localities", type=int, default=34)
    parser.add_argument("--days", type=float, default=90.0)
    parser.add_argument("--reproduction-horizon-days", type=float, default=30.0)
    parser.add_argument("--parent-overlap-days", type=float, default=7.0)
    args = parser.parse_args()
    report = run_ensemble(
        seeds=tuple(args.seeds),
        agent_count=args.agents,
        locality_count=args.localities,
        horizon_days=args.days,
        reproduction_horizon_days=args.reproduction_horizon_days,
        parent_overlap_days=args.parent_overlap_days,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
