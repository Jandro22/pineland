"""Profile dynamic WorldState field size/copy cost at one Afghanistan week."""
from __future__ import annotations

import argparse
import copy
from dataclasses import fields
import importlib.util
import json
import pickle
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
RUNNER = Path(__file__).with_name(
    "run_afghanistan_filtered_prospective_2005.py"
)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "afghanistan_particle_field_profiler", RUNNER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=13)
    parser.add_argument("--seed", type=int, default=20050111)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = _load_runner()
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    horizon = max(60.0, args.week * 7.0)
    base = runner.generate_pineland(
        runner._config(args.seed, horizon), empirical_geography=case
    )
    runner._precompute_province_lookup(base)
    state = runner.build_initial_particle(
        seed=args.seed,
        particle_index=0,
        taliban_strength=7500.0,
        horizon=horizon,
        case=case,
        inputs=inputs,
        base_world=base,
    ).state
    if args.week:
        state.advance_to(args.week * 7.0)
    rows = []
    for item in fields(state.world):
        value = getattr(state.world, item.name)
        try:
            started = perf_counter()
            raw = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            pickle_seconds = perf_counter() - started
            started = perf_counter()
            copy.deepcopy(value)
            deepcopy_seconds = perf_counter() - started
            rows.append({
                "field": item.name,
                "serialized_bytes": len(raw),
                "pickle_seconds": pickle_seconds,
                "deepcopy_seconds": deepcopy_seconds,
                "type": type(value).__name__,
                "length": len(value) if hasattr(value, "__len__") else None,
            })
        except Exception as exc:
            rows.append({
                "field": item.name,
                "error": repr(exc),
                "type": type(value).__name__,
            })
    rows.sort(
        key=lambda row: row.get("serialized_bytes", -1), reverse=True
    )
    payload = {
        "schema_version": "pineland.performance.particle_fields.v1",
        "scientific_status": "execution-only",
        "week": args.week,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "top": rows[:12],
    }))


if __name__ == "__main__":
    main()
