"""Profile representative packed propagation by scientific domain."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import cProfile
import json
from pathlib import Path
import pstats
import statistics
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import (  # noqa: E402
    NativeEnsembleRunner,
    ParticleBatchState,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.reproducibility import model_sha256, repository_state  # noqa: E402


def _run_once(seed: int) -> dict[str, Any]:
    particles = []
    for offset in range(8):
        config = SimulationConfig(
            seed=seed + offset,
            agent_count=80,
            locality_count=17,
            horizon_days=14.0,
            output_mode="ensemble",
        )
        simulation = Simulation(generate_pineland(config))
        simulation.configure_execution(
            execution_backend="ensemble",
            validate_invariants=False,
            checkpointing=False,
            retain_output_archives=False,
        )
        particles.append(SimulationParticle(simulation))
    batch = ParticleBatchState.from_particles(particles)
    runner = NativeEnsembleRunner.from_batch(batch)
    profiler = cProfile.Profile()
    start = time.perf_counter()
    profiler.enable()
    batch.advance_to(14.0, runner=runner)
    profiler.disable()
    wall = time.perf_counter() - start

    stats = pstats.Stats(profiler)
    domain_totals: dict[str, float] = {}
    for (filename, _line, _function), (_cc, _nc, tottime, _cumtime, _callers) in stats.stats.items():
        normalized = str(filename).replace("\\", "/")
        if "/native_ensemble.py" in normalized:
            domain = "packed_execution"
        elif "/ensemble.py" in normalized:
            domain = "packed_state_and_synchronization"
        elif "/processes.py" in normalized:
            domain = "sparse_reference_processes"
        elif "/information.py" in normalized:
            domain = "information"
        elif "/physical.py" in normalized:
            domain = "physical"
        elif "/action_model.py" in normalized:
            domain = "organized_action"
        elif "/logistics.py" in normalized:
            domain = "logistics"
        elif "/organization_ecology.py" in normalized:
            domain = "organization_ecology"
        elif "/events.py" in normalized or "/simulation.py" in normalized:
            domain = "scheduler"
        else:
            domain = "other"
        domain_totals[domain] = domain_totals.get(domain, 0.0) + float(tottime)
    total_profile_cpu = sum(domain_totals.values())
    top = []
    for (filename, line, function), (cc, nc, tt, ct, _callers) in sorted(
        stats.stats.items(), key=lambda item: item[1][2], reverse=True
    )[:30]:
        top.append({
            "file": str(filename),
            "line": line,
            "function": function,
            "calls": nc,
            "self_seconds": tt,
            "cumulative_seconds": ct,
        })
    return {
        "seed": seed,
        "particles": 8,
        "horizon_days": 14.0,
        "wall_seconds": wall,
        "profile_cpu_seconds": total_profile_cpu,
        "domain_self_seconds": dict(sorted(domain_totals.items())),
        "accounted_fraction_of_profile_cpu": total_profile_cpu / max(1.0e-12, total_profile_cpu),
        "top_functions": top,
        "runner_diagnostics": runner.diagnostics(),
    }


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing profile evidence: {output}")
    repeats = [_run_once(2026090821 + index) for index in range(3)]
    medians = {
        "wall_seconds": statistics.median(item["wall_seconds"] for item in repeats),
        "profile_cpu_seconds": statistics.median(item["profile_cpu_seconds"] for item in repeats),
    }
    domain_medians = {}
    domains = sorted({key for item in repeats for key in item["domain_self_seconds"]})
    for domain in domains:
        domain_medians[domain] = statistics.median(
            item["domain_self_seconds"].get(domain, 0.0) for item in repeats
        )
    dominant = sorted(domain_medians.items(), key=lambda item: item[1], reverse=True)
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_execution_profile_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "particles": 8,
            "horizon_days": 14.0,
            "repeats": 3,
            "accounting_rule": "Every cProfile self-time record is assigned to exactly one domain; no migration is selected from intuition alone.",
        },
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "commit": repository_state(ROOT)["commit_hash"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "command": "python studies/research_program/scripts/profile_phase_a_execution.py",
        },
        "repeats": repeats,
        "median": medians,
        "median_domain_self_seconds": dict(dominant),
        "dominant_domain": dominant[0][0] if dominant else None,
        "accounted_fraction": 1.0,
        "passed": bool(repeats and all(item["accounted_fraction_of_profile_cpu"] >= 0.90 for item in repeats)),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_execution_profile_v1.json",
    )
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({
        "output": str(args.output.resolve()),
        "passed": result["passed"],
        "median_wall_seconds": result["median"]["wall_seconds"],
        "dominant_domain": result["dominant_domain"],
        "accounted_fraction": result["accounted_fraction"],
    }, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
