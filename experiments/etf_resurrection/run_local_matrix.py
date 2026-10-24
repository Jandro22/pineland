"""Run the v6 small-world engineering matrix locally (no ARC) and summarize it.

Each run is one 300-agent / 34-locality world, full horizon, traced with
PINELAND_FUNNEL. Cells: one forcegen-, logistics- and command-constrained
cell at support intensity 0.5. Output: <out>/<tag>/ per run + matrix.csv.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SOURCE = REPO / "studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_autonomy_phase_map_v1.json"
CELLS = {"forcegen": 2, "logistics": 37, "command": 72}
WITHDRAWAL = 120.0


def run_one(job: dict) -> dict:
    out = Path(job["out"]) / job["tag"]
    out.mkdir(parents=True, exist_ok=True)
    contract = out / "contract.json"
    cmd = [
        sys.executable, str(HERE / "make_v6_smoke_contract.py"), "--source", str(SOURCE),
        "--output", str(contract), "--cell-index", str(CELLS[job["cell"]]),
        "--seed", str(job["seed"]), "--rate", str(job["rate"]),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    data = json.loads(contract.read_text(encoding="utf-8"))
    data["cells"][0]["organized_action_architecture"] = job["arch"]
    for key, value in job.get("sets", {}).items():
        data["cells"][0][key] = value
    if job.get("horizons"):
        data["horizons_days"] = job["horizons"]
    contract.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    env = dict(os.environ, PINELAND_FUNNEL="1")
    with (out / "funnel.log").open("w") as err, (out / "stdout.log").open("w") as so:
        subprocess.run(
            [job["binary"], "--stage4-contract", str(contract), "--output", str(out / "world.csv"),
             "--trajectory-output", str(out / "traj.csv"), "--allow-dirty", "--allow-unfrozen", "--execute"],
            check=True, env=env, stdout=so, stderr=err,
        )
    sys.path.insert(0, str(HERE))
    from summarize_v6_smoke import summarize
    summary = summarize(out / "funnel.log", out / "traj.csv", WITHDRAWAL)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    post = summary["trace"]["post_withdrawal_strike_outcome_counts"]
    n = max(sum(post.values()), 1)
    on, off = summary["branches"]["SUPPORT_ON"], summary["branches"]["SUPPORT_OFF"]
    last_ins = last_traj_value(out / "traj.csv", "insurgent_personnel")
    return {
        "tag": job["tag"], "arch": job["arch"], "cell": job["cell"], "seed": job["seed"],
        "rate": job["rate"], "sets": json.dumps(job.get("sets", {})),
        "post_strikes": sum(post.values()),
        "post_unaffordable": post.get("unaffordable", 0) / n,
        "post_dry_hole": post.get("dry_hole", 0) / n,
        "post_engaged": post.get("engaged", 0) / n,
        "contacts_on": on.get("post_contacts"), "contacts_off": off.get("post_contacts"),
        "losses_on": round(on.get("post_military_losses", 0), 1),
        "losses_off": round(off.get("post_military_losses", 0), 1),
        "mil_end_on": round(on.get("last_personnel", 0)), "mil_end_off": round(off.get("last_personnel", 0)),
        "rdy_end_on": on.get("last_readiness"), "rdy_end_off": off.get("last_readiness"),
        "insurgent_end": round(last_ins), **summary["gates"],
    }


def last_traj_value(path: Path, column: str) -> float:
    with path.open(newline="") as f:
        return float(list(csv.DictReader(f))[-1][column])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arch", default="multichannel_v6")
    ap.add_argument("--cells", default="forcegen,logistics,command")
    ap.add_argument("--seeds", default="2026200000,2026200001")
    ap.add_argument("--rates", default="0.04,0.08,0.16")
    ap.add_argument("--set", action="append", default=[], help="cell override key=value")
    ap.add_argument("--horizons", default="7,90")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--label", default="m")
    a = ap.parse_args()
    jobs = []
    for cell in a.cells.split(","):
        for seed in map(int, a.seeds.split(",")):
            for rate in map(float, a.rates.split(",")):
                tag = f"{a.label}_{cell}_s{seed % 1000}_r{int(rate * 100):03d}"
                sets = {k: float(v) for k, v in (x.split("=", 1) for x in a.set)}
                jobs.append(dict(binary=a.binary, out=a.out, tag=tag, cell=cell, seed=seed, rate=rate,
                                 arch=a.arch, sets=sets,
                                 horizons=[float(h) for h in a.horizons.split(",")]))
    rows = []
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for row in (f.result() for f in cf.as_completed([pool.submit(run_one, j) for j in jobs])):
            rows.append(row)
            print(json.dumps(row), flush=True)
    path = Path(a.out) / f"{a.label}_matrix.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", path)


if __name__ == "__main__":
    main()
