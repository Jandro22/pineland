"""Build the Stage-4 "autonomy trap" ARC campaign: variant contracts + task list.

One task = one paired world (cell, seed) of one variant contract, run by the
Stage-4 harness in sharded single-world mode (--cell-index/--seed), which defers
the ensemble degeneracy alarm to collection.

Blocks (all at production scale from the frozen design: 1000 agents, 72 localities):
  A  phase map x learning     every design cell x learning rate {0, .1, .25, .5, 1}
  B  support duration         withdrawal day {90, 240, 360} x learning {0, .25}
  C  reference share          learning .25 x reference share {.75, .95}
  D  dose extension           support dose x{4, 16} x learning {0, .25}
  S  sequenced exit         one channel kept 180 days after the rest, learning .25
  G  development remedy       developmental assistance on the binding channel x learning {0, .25}
  E  showcase maps            locality output for map figures
Blocks B-D and G use the support-intensity-1.0 cells (one per structure x capacity).

Usage:
  python build_campaign.py --design <stage4_autonomy_phase_map_v1.json> --out campaigns/autonomy_trap_v1 \
      [--seeds 32] [--quick]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

LEARNING = [0.0, 0.1, 0.25, 0.5, 1.0]
DEV_CHANNEL = {"forcegen_constrained": "forcegen", "logistics_constrained": "logistics",
               "command_constrained": "command", "balanced_capacity": None}
DOSE_FIELDS = ("logistics_rate", "logistics_capacity", "forcegen_training_rate_boost",
               "command_reliability_boost", "air_intensity")


def patch(cell: dict, **pf) -> dict:
    cell = copy.deepcopy(cell)
    cell.setdefault("config_patch", {}).setdefault("partner_force_support", {}).update(pf)
    return cell


def dose(cell: dict, k: float) -> dict:
    cell = copy.deepcopy(cell)
    for f in DOSE_FIELDS:
        cell[f] = cell.get(f, 0.0) * k
    cell["command_reliability_boost"] = min(0.95, cell["command_reliability_boost"])
    cell["command_latency_reduction_fraction"] = min(0.9, cell.get("command_latency_reduction_fraction", 0.0) * k)
    return cell


def develop(cell: dict, rate: float) -> dict:
    cell = copy.deepcopy(cell)
    channel = DEV_CHANNEL[cell["factor_structure"]]
    channels = [channel] if channel else ["forcegen", "logistics", "command"]
    for c in channels:
        cell[f"development_{c}_rate_per_30d"] = rate / len(channels)
    cell["development_cost_per_day"] = 200.0
    return cell


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--design", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=64)
    ap.add_argument("--seed-base", type=int, default=2026700000)
    ap.add_argument("--local", action="store_true", help="4 core cells at 300-agent scale, no C/D blocks")
    ap.add_argument("--robust", action="store_true", help="with --local: only the learning-rate x reference-share robustness block")
    ap.add_argument("--devsweep", action="store_true", help="with --local --robust: development-dose sweep instead")
    ap.add_argument("--confirm", action="store_true", help="with --local --robust: A_lr0 / A_lr0.25 only (use with many seeds)")
    ap.add_argument("--allcore", action="store_true", help="with --local: keep every capacity level of the intensity-1.0 cells")
    ap.add_argument("--quick", action="store_true", help="tiny local smoke campaign (2 cells, 1 seed, 300 agents)")
    a = ap.parse_args()

    design = json.loads(a.design.read_text())
    base_cells = design["cells"]
    for c in base_cells:
        c["organized_action_architecture"] = "multichannel_v6"
    core = [c for c in base_cells if c["factor_support_intensity"] == 1.0]
    seeds = [a.seed_base + i for i in range(a.seeds)]
    if a.quick:
        base_cells, core, seeds = base_cells[4:5], core[:1], seeds[:1]
        design["environment"].update(agent_count=300, locality_count=34)
    learning = LEARNING
    if a.local and not a.allcore:
        # One mid-capacity, design-intensity cell per structure, at local (300-agent) scale.
        core = [cand[len(cand) // 2] for cand in
                ([c for c in core if c["factor_structure"] == st] for st in
                 ("forcegen_constrained", "command_constrained", "logistics_constrained", "balanced_capacity"))
                if cand]
        base_cells, learning = core, [0.0, 0.25, 1.0]
    if a.local and a.allcore:
        base_cells = core
    if a.local:
        design["environment"].update(agent_count=300, locality_count=34)

    variants: dict[str, dict] = {}
    if a.local and a.robust:
        learning = []

    def add(name: str, cells: list[dict], withdrawal: float | None = None, locality: bool = False):
        d = copy.deepcopy(design)
        d["cells"] = cells
        d["cells_count"] = len(cells)
        d["experiment_id"] = f"{design['experiment_id']}__{name}"
        if withdrawal is not None:
            d["environment"]["withdrawal_time_days"] = withdrawal
        variants[name] = dict(design=d, locality=locality)

    if a.local and a.robust:
        for lr in ((0.0, 0.25) if a.confirm else ()):
            add(f"A_lr{lr:g}", [patch(c, learning_rate_per_30d=lr) for c in base_cells])
        for rate in ((0.0125, 0.025, 0.1, 0.2) if a.devsweep and not a.confirm else ()):
            add(f"G_dev{rate:g}_lr0.25", [patch(develop(c, rate), learning_rate_per_30d=0.25) for c in core])
        for lr, ref in (() if (a.devsweep or a.confirm) else ((0.1, 0.9), (0.5, 0.9), (0.25, 0.7), (0.25, 0.8), (0.25, 0.95))):
            add(f"R_lr{lr:g}_ref{ref:g}", [patch(c, learning_rate_per_30d=lr, learning_reference_share=ref) for c in core])
        learning = []
    for lr in learning:
        add(f"A_lr{lr:g}", [patch(c, learning_rate_per_30d=lr) for c in base_cells])
    for t in (() if a.robust else (90.0, 240.0, 360.0)):
        for lr in (0.0, 0.25):
            add(f"B_T{t:g}_lr{lr:g}", [patch(c, learning_rate_per_30d=lr) for c in core], withdrawal=t)
    for ref in (() if a.local else (0.75, 0.95)):
        add(f"C_ref{ref:g}", [patch(c, learning_rate_per_30d=0.25, learning_reference_share=ref) for c in core])
    for k in (() if a.local else (4.0, 16.0)):
        for lr in (0.0, 0.25):
            add(f"D_dose{k:g}_lr{lr:g}", [patch(dose(c, k), learning_rate_per_30d=lr) for c in core])
    for channel in (() if a.robust else ("logistics", "command", "force_generation")):
        add(f"S_keep_{channel}", [patch(c, learning_rate_per_30d=0.25, **{f"{channel}_withdrawal_delay_days": 180.0})
                                  for c in core])
    for lr in (() if a.robust else (0.0, 0.25)):
        add(f"G_dev_lr{lr:g}", [patch(develop(c, 0.05), learning_rate_per_30d=lr) for c in core])
    showcase = []
    for structure in ("forcegen_constrained", "command_constrained", "logistics_constrained", "balanced_capacity"):
        cand = [c for c in core if c["factor_structure"] == structure]
        if cand:
            showcase.append(cand[len(cand) // 2])
    for lr in (() if a.robust else (0.0, 0.25)):
        add(f"E_map_lr{lr:g}", [patch(c, learning_rate_per_30d=lr) for c in showcase], locality=True)

    out = a.out
    (out / "contracts").mkdir(parents=True, exist_ok=True)
    tasks = []
    for name, v in variants.items():
        path = out / "contracts" / f"{name}.json"
        path.write_text(json.dumps(v["design"], indent=1))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        use_seeds = seeds[:2] if name.startswith("E_") else seeds
        for i in range(len(v["design"]["cells"])):
            for s in use_seeds:
                tasks.append(dict(id=len(tasks), variant=name, contract=f"contracts/{name}.json",
                                  contract_sha=digest, cell_index=i, cell_id=v["design"]["cells"][i]["cell_id"],
                                  seed=s, locality=v["locality"]))
    # Task ids are fixed by generation order (they name the scratch directories, so
    # finished work is recognised across resubmissions); the run order is a fixed
    # shuffle so any partially finished campaign samples every block evenly.
    import random
    order = list(tasks)
    random.Random(20261024).shuffle(order)
    tasks = order
    with (out / "tasks.jsonl").open("w") as fh:
        for t in tasks:
            fh.write(json.dumps(t) + "\n")
    summary = {name: sum(1 for t in tasks if t["variant"] == name) for name in variants}
    (out / "campaign.json").write_text(json.dumps(dict(
        campaign=out.name, tasks=len(tasks), seeds=len(seeds), variants=summary,
        environment=design["environment"], horizons=design["horizons_days"]), indent=1))
    print(f"{len(tasks)} tasks in {len(variants)} variants -> {out}")
    for k, v in summary.items():
        print(f"  {k:22s} {v}")


if __name__ == "__main__":
    main()
