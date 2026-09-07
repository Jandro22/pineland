"""Build an auditable production speedup ledger from canonical run artifacts.

This script intentionally does not manufacture a baseline or infer CPU time
from wall time.  It accepts separately measured cold and warm artifacts for
the frozen baseline and the candidate, validates that they share the
production contract, and emits a comparison only when both sides contain
real timings.  The 80--100x objective is recorded as a target, never as a
result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BASELINE_COMMIT = "6fde02c"
CANONICAL_PARTICLES = 128
CANONICAL_LIKELIHOOD_BRANCHES = 3
CANONICAL_FORECAST_BRANCHES = 3
CANONICAL_FORECAST_END_DAY = 731.0
SCHEMA = "pineland.performance.afghanistan_production_speedup_ledger.v1"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _cache_hit(payload: dict[str, Any]) -> bool | None:
    posterior = payload.get("posterior_cache")
    forecast = payload.get("forecast_cache")
    if not isinstance(posterior, dict) or not isinstance(forecast, dict):
        return None
    return bool(posterior.get("hit")) or bool(forecast.get("hit"))


def _timing(payload: dict[str, Any], path: Path) -> dict[str, float | None]:
    performance = payload.get("performance")
    if not isinstance(performance, dict):
        raise ValueError(f"{path} has no measured performance block")
    wall = performance.get("wall_seconds_before_artifact_write")
    if wall is None:
        wall = performance.get("wall_seconds")
    if wall is None:
        raise ValueError(f"{path} has no measured wall time")
    return {
        "wall_seconds": float(wall),
        "coordinator_cpu_seconds": (
            float(performance["coordinator_cpu_seconds_before_artifact_write"])
            if performance.get("coordinator_cpu_seconds_before_artifact_write")
            is not None else None
        ),
        "resident_worker_cpu_seconds": (
            float(performance["resident_worker_cpu_seconds"])
            if performance.get("resident_worker_cpu_seconds") is not None
            else None
        ),
    }


def _contract(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    expected = {
        "particle_count": CANONICAL_PARTICLES,
        "likelihood_branches": CANONICAL_LIKELIHOOD_BRANCHES,
        "forecast_branches": CANONICAL_FORECAST_BRANCHES,
        "forecast_end_day": CANONICAL_FORECAST_END_DAY,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(
                f"{path} violates canonical contract: {key}={payload.get(key)!r}, "
                f"expected {value!r}"
            )
    cache_hit = _cache_hit(payload)
    if cache_hit is None:
        raise ValueError(f"{path} does not declare posterior and forecast cache status")
    return {
        key: payload.get(key)
        for key in (
            "case_sha256",
            "historical_inputs_sha256",
            "training_observation_sha256",
            "seed",
            "particle_initial_strengths",
        )
    } | {"cache_hit": cache_hit}


def _load_run(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read(path)
    contract = _contract(payload, path)
    timing = _timing(payload, path)
    if timing["wall_seconds"] < 0:
        raise ValueError(f"{path} has negative wall time")
    return {
        "artifact": str(path.resolve()),
        "label": label,
        "source_commit": payload.get("source_commit_at_run"),
        "parallel_workers": payload.get("parallel_workers"),
        "exact_state_equivalence": bool(
            payload.get("exact_state_equivalence")
            or payload.get("exact_execution_state_equivalence")
        ),
        "exact_score_equivalence": bool(payload.get("exact_score_equivalence")),
        "contract": contract,
        "timing": timing,
    }


def _assert_pair_compatible(left: dict[str, Any], right: dict[str, Any]) -> None:
    for key in (
        "case_sha256",
        "historical_inputs_sha256",
        "training_observation_sha256",
        "seed",
        "particle_initial_strengths",
    ):
        if left["contract"].get(key) != right["contract"].get(key):
            raise ValueError(f"canonical artifacts disagree on {key}")


def _comparison(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    _assert_pair_compatible(baseline, candidate)
    baseline_wall = float(baseline["timing"]["wall_seconds"])
    candidate_wall = float(candidate["timing"]["wall_seconds"])
    speedup = baseline_wall / candidate_wall if candidate_wall > 0 else None
    exact = (
        baseline["exact_state_equivalence"]
        and candidate["exact_state_equivalence"]
        and baseline["exact_score_equivalence"]
        and candidate["exact_score_equivalence"]
    )
    return {
        "baseline_wall_seconds": baseline_wall,
        "candidate_wall_seconds": candidate_wall,
        "speedup": speedup,
        "candidate_worker_count": candidate.get("parallel_workers"),
        "exact_state_equivalence_required": True,
        "exact_equivalence_certified": exact,
        "claimable": speedup is not None and speedup >= 80.0 and exact,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-cold", type=Path, required=True)
    parser.add_argument("--baseline-warm", type=Path, required=True)
    parser.add_argument("--candidate-cold", type=Path, required=True)
    parser.add_argument("--candidate-warm", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runs = {
        "baseline_cold": _load_run(args.baseline_cold, label="baseline_cold"),
        "baseline_warm": _load_run(args.baseline_warm, label="baseline_warm"),
        "candidate_cold": _load_run(args.candidate_cold, label="candidate_cold"),
        "candidate_warm": _load_run(args.candidate_warm, label="candidate_warm"),
    }
    baseline_commits = {
        runs["baseline_cold"]["source_commit"],
        runs["baseline_warm"]["source_commit"],
    }
    if not all(str(commit).startswith(BASELINE_COMMIT) for commit in baseline_commits):
        raise ValueError(
            f"baseline artifacts must come from canonical commit {BASELINE_COMMIT}"
        )
    for cold_key, warm_key in (
        ("baseline_cold", "baseline_warm"),
        ("candidate_cold", "candidate_warm"),
    ):
        if runs[cold_key]["source_commit"] != runs[warm_key]["source_commit"]:
            raise ValueError(f"{cold_key} and {warm_key} use different commits")
        if runs[cold_key]["parallel_workers"] != runs[warm_key]["parallel_workers"]:
            raise ValueError(f"{cold_key} and {warm_key} use different worker counts")
    if any(runs[key]["contract"]["cache_hit"] for key in ("baseline_cold", "candidate_cold")):
        raise ValueError("cold artifacts must have no posterior or forecast cache hit")
    if not all(runs[key]["contract"]["cache_hit"] for key in ("baseline_warm", "candidate_warm")):
        raise ValueError("warm artifacts must report a cache hit")
    _assert_pair_compatible(runs["baseline_cold"], runs["baseline_warm"])
    _assert_pair_compatible(runs["candidate_cold"], runs["candidate_warm"])

    payload = {
        "schema_version": SCHEMA,
        "scientific_status": "execution-only; no empirical score or historical claim",
        "canonical_contract": {
            "baseline_commit": BASELINE_COMMIT,
            "particles": CANONICAL_PARTICLES,
            "likelihood_branches": CANONICAL_LIKELIHOOD_BRANCHES,
            "forecast_branches": CANONICAL_FORECAST_BRANCHES,
            "forecast_end_day": CANONICAL_FORECAST_END_DAY,
            "same_seed_data_and_config_required": True,
        },
        "target_speedup_range": [80.0, 100.0],
        "runs": runs,
        "comparisons": {
            "cold": _comparison(runs["baseline_cold"], runs["candidate_cold"]),
            "warm": _comparison(runs["baseline_warm"], runs["candidate_warm"]),
        },
        "primary_claim": {
            "uses_cold_run": True,
            "cache_hits_excluded": True,
            "speedup": _comparison(
                runs["baseline_cold"], runs["candidate_cold"]
            )["speedup"],
            "status": "measured_only; exact equivalence must be independently certified",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "cold_speedup": payload["comparisons"]["cold"]["speedup"],
        "warm_speedup": payload["comparisons"]["warm"]["speedup"],
    }))


if __name__ == "__main__":
    main()
