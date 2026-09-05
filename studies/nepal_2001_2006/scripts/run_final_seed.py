"""Run one frozen Nepal final-rescore seed in an isolated process."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_untuned_benchmark import atomic_json, run_seed

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
OUT = STUDY / "runs" / "post_structural_repair" / "final_empirical_rescore"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--agent-count", type=int, default=750)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = run_seed(args.seed, args.agent_count, "E_combined")
    path = OUT / f"seed_{args.seed}_agents_{args.agent_count}.json"
    atomic_json(path, payload)
    print(json.dumps({
        "seed": args.seed,
        "runtime_seconds": payload["runtime_seconds"],
        "latent_engagements": payload["realized_contact_count"],
        "recorded_engagements": payload["recorded_realized_contact_count"],
        "output": str(path),
    }), flush=True)


if __name__ == "__main__":
    main()
