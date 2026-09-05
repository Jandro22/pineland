"""Profile compact Nepal ensemble trajectories without changing model dynamics."""
from __future__ import annotations

import argparse
import cProfile
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import pstats
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
CASE = STUDY / "config" / "case_environment_repaired.json"
OUT = STUDY / "results" / "reproducibility"


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def memory_counters() -> dict[str, int]:
    if sys.platform != "win32":
        return {}
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        handle, ctypes.byref(counters), counters.cb
    )
    if not ok:
        return {}
    return {
        "working_set_bytes": int(counters.WorkingSetSize),
        "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
        "pagefile_bytes": int(counters.PagefileUsage),
        "peak_pagefile_bytes": int(counters.PeakPagefileUsage),
    }


def top_profile_rows(profile: cProfile.Profile, limit: int = 20) -> list[dict]:
    stats = pstats.Stats(profile)
    rows = []
    for (filename, line, function), values in stats.stats.items():
        primitive_calls, total_calls, self_seconds, cumulative_seconds, _ = values
        rows.append({
            "file": Path(filename).name,
            "line": line,
            "function": function,
            "primitive_calls": primitive_calls,
            "total_calls": total_calls,
            "self_seconds": self_seconds,
            "cumulative_seconds": cumulative_seconds,
        })
    rows.sort(key=lambda row: (-row["cumulative_seconds"], -row["self_seconds"]))
    return rows[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--agents", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20_011_126)
    parser.add_argument("--no-cprofile", action="store_true")
    args = parser.parse_args()
    if args.days < 1 or args.agents < 1:
        parser.error("days and agents must be positive")

    sys.path.insert(0, str(ROOT / "src"))
    from pineland_sim.config import SimulationConfig
    from pineland_sim.generator import generate_pineland
    from pineland_sim.reproducibility import (
        canonical_sha256, decision_state_sha256, file_sha256, model_sha256,
        parameter_registry_sha256, trajectory_sha256,
    )
    from pineland_sim.simulation import Simulation

    case = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(
        seed=args.seed,
        horizon_days=float(args.days),
        agent_count=args.agents,
        locality_count=len(case["localities"]),
        output_mode="ensemble",
    )
    config.information.observation_retention_days = 90.0
    config.organization_ecology.observed_active_intervals = {
        "insurgent": [[0.0, float(args.days)]]
    }
    config.validate()

    model_hash_start = model_sha256(ROOT)
    before = memory_counters()
    profile = cProfile.Profile()
    started = time.perf_counter()
    if not args.no_cprofile:
        profile.enable()
    world = Simulation(generate_pineland(config, empirical_geography=case)).run().world
    if not args.no_cprofile:
        profile.disable()
    wall_seconds = time.perf_counter() - started
    after = memory_counters()
    model_hash_end = model_sha256(ROOT)
    payload = {
        "schema_version": "1.0.0",
        "days": args.days,
        "agents": args.agents,
        "seed": args.seed,
        "output_mode": config.output_mode,
        "observation_retention_days": config.information.observation_retention_days,
        "wall_seconds": wall_seconds,
        "cprofile_enabled": not args.no_cprofile,
        "memory_before": before,
        "memory_after": after,
        "peak_working_set_bytes": after.get("peak_working_set_bytes"),
        "case_sha256": file_sha256(CASE),
        "config_sha256": canonical_sha256(config.to_dict()),
        "parameter_registry_sha256": parameter_registry_sha256(config),
        "model_sha256_start": model_hash_start,
        "model_sha256_end": model_hash_end,
        "model_stable_during_run": model_hash_start == model_hash_end,
        "decision_state_sha256": decision_state_sha256(world),
        "trajectory_sha256": trajectory_sha256(world),
        "event_counts": dict(world.event_counts),
        "observations_retained": len(world.observations),
        "active_information_relays": len(world.active_information_relays),
        "formations": len(world.formations),
        "engagements": len(world.engagements),
        "top_cumulative_functions": (
            top_profile_rows(profile) if not args.no_cprofile else []
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"profile_{args.days}d_{args.agents}agents.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(path),
        "wall_seconds": wall_seconds,
        "peak_working_set_bytes": payload["peak_working_set_bytes"],
        "model_stable_during_run": payload["model_stable_during_run"],
        "decision_state_sha256": payload["decision_state_sha256"],
    }))


if __name__ == "__main__":
    main()
