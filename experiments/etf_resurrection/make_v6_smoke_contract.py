"""Create a reproducible single-cell Stage-4 v6 engineering-smoke contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cell-index", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2_026_200_000)
    parser.add_argument("--rate", type=float, default=0.08)
    parser.add_argument("--agent-count", type=int, default=300)
    parser.add_argument("--locality-count", type=int, default=34)
    args = parser.parse_args()

    if not 0.0 <= args.rate <= 1.0:
        parser.error("--rate must be between 0 and 1")
    if args.agent_count <= 0 or args.locality_count <= 0:
        parser.error("agent and locality counts must be positive")

    contract = json.loads(args.source.read_text(encoding="utf-8"))
    source_cells = contract.get("cells")
    if not isinstance(source_cells, list) or not 0 <= args.cell_index < len(source_cells):
        parser.error(f"cell index {args.cell_index} is outside the source contract")

    cell = dict(source_cells[args.cell_index])
    cell["organized_action_architecture"] = "multichannel_v6"
    cell["organized_action_rate"] = args.rate
    contract["cells"] = [cell]
    contract["cells_count"] = 1
    contract["seed_base"] = args.seed
    contract["default_seed_count"] = 1
    contract["experiment_id"] = (
        f"stage4_v6_smoke_{cell['cell_id']}_rate_{int(round(args.rate * 100)):03d}"
    )
    environment = dict(contract.get("environment", {}))
    environment["agent_count"] = args.agent_count
    environment["locality_count"] = args.locality_count
    contract["environment"] = environment

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Created {args.output}: cell={cell['cell_id']} seed={args.seed} "
        f"rate={args.rate:g} agents={args.agent_count} localities={args.locality_count}"
    )


if __name__ == "__main__":
    main()
