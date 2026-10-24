"""Multi-seed paired validation: ON vs OFF per cell at full horizon (background)."""
import argparse, concurrent.futures as cf, csv, json, subprocess, statistics as st
from pathlib import Path
HERE = Path(__file__).resolve().parent
FAST = HERE / "results/local_v6/fast"

def run(job):
    out = Path(job["dir"]); out.mkdir(parents=True, exist_ok=True)
    d = json.loads((FAST / f"c_{job['cell']}_s0_r008/contract.json").read_text())
    d["seed_base"] = job["seed"]; d["horizons_days"] = [90.0, 180.0, 360.0]
    k = job.get("dose", 1.0)
    c = d["cells"][0]
    for f in ("logistics_rate", "logistics_capacity", "forcegen_training_rate_boost", "command_reliability_boost", "air_intensity"):  # clamped below
        c[f] = c[f] * k
    c["command_latency_reduction_fraction"] = min(0.9, c["command_latency_reduction_fraction"] * k)
    c["command_reliability_boost"] = min(0.95, c["command_reliability_boost"])
    if job.get("patch"):
        c["config_patch"] = json.loads(job["patch"])
    if job.get("withdrawal"):
        d["environment"]["withdrawal_time_days"] = job["withdrawal"]
    (out / "c.json").write_text(json.dumps(d))
    if not (out / "w.csv").exists():
      subprocess.run([job["bin"], "--stage4-contract", str(out / "c.json"), "--output", str(out / "w.csv"),
                    "--trajectory-output", str(out / "t.csv"), "--allow-dirty", "--allow-unfrozen",
                    "--disable-diagnostic-telemetry", "--execute"], check=True, capture_output=True, timeout=3600)
    rows = {(r["branch"], float(r["horizon_days"])): r for r in csv.DictReader(open(out / "w.csv"))}
    res = []
    for h in (90.0, 180.0, 360.0):
        on, off = rows[("SUPPORT_ON", h)], rows[("SUPPORT_OFF", h)]
        f = lambda r, k: float(r[k])
        res.append(dict(cell=job["cell"], seed=job["seed"], dose=job.get("dose", 1.0), h=str(h),
            d_comp=f(on, "composite_capability") - f(off, "composite_capability"),
            d_gov=f(on, "c_government_control") - f(off, "c_government_control"),
            d_mil=f(on, "c_military_personnel_retention") - f(off, "c_military_personnel_retention")))
    return res

ap = argparse.ArgumentParser()
ap.add_argument("--bin", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--seeds", type=int, default=4); ap.add_argument("--workers", type=int, default=6)
ap.add_argument("--cells", default="forcegen,logistics,command")
ap.add_argument("--dose", type=float, default=1.0)
ap.add_argument("--patch", default="")
ap.add_argument("--withdrawal", type=float, default=0.0)
a = ap.parse_args()
jobs = [dict(bin=a.bin, cell=c, seed=2026500000 + s, dose=a.dose, patch=a.patch, withdrawal=a.withdrawal, dir=f"{a.out}/{c}_{s}") for c in a.cells.split(",") for s in range(a.seeds)]
rows = []
with cf.ThreadPoolExecutor(a.workers) as p:
    for r in p.map(run, jobs):
        rows += r; print("done", r[0]["cell"], r[0]["seed"], flush=True)
with open(f"{a.out}/summary.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for c in a.cells.split(","):
    for h in ("90.0", "180.0", "360.0"):
        x = [r for r in rows if r["cell"] == c and r["h"] == h]
        print(c, h, "n=%d" % len(x), *("%s mean %.3f sd %.3f pos %d/%d" % (k, st.mean(r[k] for r in x), st.pstdev(r[k] for r in x), sum(r[k] > 0 for r in x), len(x)) for k in ("d_comp", "d_gov", "d_mil")))
