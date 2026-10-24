"""Sequenced-withdrawal experiment: which support channel should go last?

For each constraint cell, runs paired worlds where the SUPPORT_OFF branch
withdraws every channel at T except one, which stays for --delay days
(partner_force_support.<channel>_withdrawal_delay_days via config_patch).
Variants: immediate (all at T), keep_logistics, keep_command,
keep_force_generation, keep_air (only meaningful when the cell has air), and
keep_all (all channels delayed: equivalent to a later withdrawal date).

Outcome per variant at each horizon: withdrawn-branch military personnel
retention, government control, and the ON-OFF composite gap. Run in the
background; each world is a full-horizon small world (~4 min single-threaded).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACTS = HERE / "results/local_v6/fast"
CHANNELS = ("air", "logistics", "command", "force_generation")


def variants(delay: float) -> dict[str, dict]:
    out = {"immediate": {}}
    for c in CHANNELS:
        out[f"keep_{c}"] = {f"{c}_withdrawal_delay_days": delay}
    out["keep_all"] = {f"{c}_withdrawal_delay_days": delay for c in CHANNELS}
    return out


def run(job: dict) -> list[dict]:
    out = Path(job["dir"])
    out.mkdir(parents=True, exist_ok=True)
    contract = json.loads((CONTRACTS / f"c_{job['cell']}_s0_r008/contract.json").read_text())
    contract["seed_base"] = job["seed"]
    contract["horizons_days"] = job["horizons"]
    if job["patch"]:
        contract["cells"][0]["config_patch"] = {"partner_force_support": job["patch"]}
    path = out / "contract.json"
    path.write_text(json.dumps(contract))
    subprocess.run(
        [job["binary"], "--stage4-contract", str(path), "--output", str(out / "w.csv"),
         "--trajectory-output", str(out / "t.csv"), "--allow-dirty", "--allow-unfrozen",
         "--disable-diagnostic-telemetry", "--execute"],
        check=True, capture_output=True, timeout=3600,
    )
    rows = list(csv.DictReader(open(out / "w.csv")))
    by = {(r["branch"], r["horizon_days"]): r for r in rows}
    result = []
    for h in sorted({r["horizon_days"] for r in rows}, key=float):
        on, off = by[("SUPPORT_ON", h)], by[("SUPPORT_OFF", h)]
        result.append({
            "cell": job["cell"], "seed": job["seed"], "variant": job["variant"], "horizon": h,
            "off_mil_retention": off["c_military_personnel_retention"],
            "off_gov_control": off["c_government_control"],
            "gap_composite": float(on["composite_capability"]) - float(off["composite_capability"]),
            "off_donor_cost": off["post_donor_cost"],
        })
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cells", default="forcegen,logistics,command")
    ap.add_argument("--seeds", default="2026400000")
    ap.add_argument("--delay", type=float, default=180.0)
    ap.add_argument("--horizons", default="90,180,360")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    horizons = [float(h) for h in a.horizons.split(",")]
    jobs = []
    for cell in a.cells.split(","):
        for seed in map(int, a.seeds.split(",")):
            for name, patch in variants(a.delay).items():
                jobs.append(dict(binary=a.binary, cell=cell, seed=seed, variant=name, patch=patch,
                                 horizons=horizons, dir=str(a.out / f"{cell}_{seed}_{name}")))
    rows = []
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for res in pool.map(run, jobs):
            rows.extend(res)
            print(f"done {res[0]['cell']} {res[0]['variant']}", flush=True)
    path = a.out / "sequencing.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("wrote", path)


if __name__ == "__main__":
    main()
