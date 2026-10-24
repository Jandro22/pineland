"""Morris elementary-effects screening of the v6 free parameters (local, small worlds).

Each run is one 300-agent / 34-locality paired world (SUPPORT_ON vs SUPPORT_OFF)
with a single post-withdrawal horizon. Parameters are applied through the
harness ``config_patch`` cell field. Outputs per horizon row of world.csv:

  d_composite  = composite_capability(ON) - composite_capability(OFF)
  d_gov        = c_government_control(ON) - c_government_control(OFF)
  mil_ret_off  = c_military_personnel_retention in the withdrawn branch

For each parameter and output we report mu* (mean |elementary effect|, the
importance ranking) and sigma (interaction / nonlinearity) — Morris (1991),
Campolongo et al. (2007).

Usage:
  python sensitivity_morris.py --binary rust/target/release/examples/partner_force_autonomy_stage3.exe \
      --out results/local_v6/morris --trajectories 6 --workers 8 [--cell logistics]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import random
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACTS = HERE / "results/local_v6/fast"

# (path in SimulationConfig JSON, low, high). Ranges bracket the defaults.
PARAMETERS = [
    ("organized_action_rate", 0.04, 0.16),
    ("combat.strike_fraction", 0.05, 0.30),
    ("combat.strike_report_decay_days", 3.0, 21.0),
    ("logistics.security_pursuit_weight", 0.0, 1.0),
    ("combat.defection_base_hazard_per_day", 0.0005, 0.006),
    ("combat.defection_pressure_slope", 4.0, 12.0),
    ("combat.insurgent_tempo_sensitivity", 0.0, 2.0),
    ("organization_ecology.cohesion_loss_memory", 0.1, 0.4),
]
LEVELS = 4
OUTPUTS = ("d_composite", "d_gov", "mil_ret_off", "contacts")


def patch_for(point: list[float]) -> dict:
    patch: dict = {}
    for (path, lo, hi), x in zip(PARAMETERS, point):
        value = lo + (hi - lo) * x
        node = patch
        *parents, leaf = path.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return patch


def trajectories(r: int, k: int, rng: random.Random) -> list[list[list[float]]]:
    delta = LEVELS / (2 * (LEVELS - 1))
    grid = [i / (LEVELS - 1) for i in range(LEVELS) if i / (LEVELS - 1) + delta <= 1.0 + 1e-9]
    out = []
    for _ in range(r):
        x = [rng.choice(grid) for _ in range(k)]
        path = [list(x)]
        for j in rng.sample(range(k), k):
            x = list(x)
            x[j] = x[j] + delta if x[j] + delta <= 1.0 + 1e-9 else x[j] - delta
            path.append(x)
        out.append(path)
    return out


def run(job: dict) -> dict:
    out = Path(job["dir"])
    out.mkdir(parents=True, exist_ok=True)
    contract = json.loads((CONTRACTS / f"c_{job['cell']}_s0_r008/contract.json").read_text())
    contract["seed_base"] = job["seed"]
    contract["horizons_days"] = [float(job["horizon"])]
    contract["cells"][0]["config_patch"] = patch_for(job["point"])
    path = out / "contract.json"
    path.write_text(json.dumps(contract))
    subprocess.run(
        [job["binary"], "--stage4-contract", str(path), "--output", str(out / "w.csv"),
         "--trajectory-output", str(out / "t.csv"), "--allow-dirty", "--allow-unfrozen",
         "--disable-diagnostic-telemetry", "--execute"],
        check=True, capture_output=True, timeout=1800,
    )
    rows = {r["branch"]: r for r in csv.DictReader(open(out / "w.csv"))}
    on, off = rows["SUPPORT_ON"], rows["SUPPORT_OFF"]
    f = lambda r, k: float(r[k])
    return {
        **job,
        "d_composite": f(on, "composite_capability") - f(off, "composite_capability"),
        "d_gov": f(on, "c_government_control") - f(off, "c_government_control"),
        "mil_ret_off": f(off, "c_military_personnel_retention"),
        "contacts": f(off, "post_military_losses"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cell", default="logistics", choices=["forcegen", "logistics", "command"])
    ap.add_argument("--trajectories", type=int, default=6)
    ap.add_argument("--horizon", type=float, default=90.0)
    ap.add_argument("--seed", type=int, default=2026300000)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    k = len(PARAMETERS)
    paths = trajectories(a.trajectories, k, random.Random(a.seed))
    jobs = []
    for t, path in enumerate(paths):
        for s, point in enumerate(path):
            jobs.append(dict(binary=a.binary, cell=a.cell, horizon=a.horizon, point=point,
                             seed=a.seed + t, traj=t, step=s, dir=str(a.out / f"t{t}_s{s}")))
    results = {}
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for res in pool.map(run, jobs):
            results[(res["traj"], res["step"])] = res
            print(f"done t{res['traj']} s{res['step']}", flush=True)
    effects = {p[0]: {o: [] for o in OUTPUTS} for p in PARAMETERS}
    delta = LEVELS / (2 * (LEVELS - 1))
    for t, path in enumerate(paths):
        for s in range(1, len(path)):
            j = next(i for i in range(k) if path[s][i] != path[s - 1][i])
            sign = 1.0 if path[s][j] > path[s - 1][j] else -1.0
            for o in OUTPUTS:
                ee = sign * (results[(t, s)][o] - results[(t, s - 1)][o]) / delta
                effects[PARAMETERS[j][0]][o].append(ee)
    table = a.out / f"morris_{a.cell}.csv"
    with table.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["parameter", "output", "mu_star", "mu", "sigma", "n"])
        for name, per in effects.items():
            for o, ee in per.items():
                n = len(ee)
                mu = sum(ee) / n
                mu_star = sum(abs(e) for e in ee) / n
                sigma = (sum((e - mu) ** 2 for e in ee) / max(n - 1, 1)) ** 0.5
                w.writerow([name, o, f"{mu_star:.5f}", f"{mu:.5f}", f"{sigma:.5f}", n])
    with (a.out / f"morris_{a.cell}_runs.json").open("w") as fh:
        json.dump([{k2: v for k2, v in r.items() if k2 != "binary"} for r in results.values()], fh, indent=1)
    print("wrote", table)


if __name__ == "__main__":
    main()
