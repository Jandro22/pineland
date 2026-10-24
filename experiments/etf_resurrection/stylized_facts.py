"""Pattern-oriented check of Pineland v6 trajectories against historical stylized facts.

Reads one or more diagnostic trajectory CSVs (harness --trajectory-output) and,
per paired world, computes for the SUPPORT_OFF and SUPPORT_ON branches:

  collapse_days       days after withdrawal until military personnel falls
                      below 50% of its withdrawal-day value (inf if never)
  personnel_change    military personnel at end / at withdrawal
  gov_control_change  government_control end - withdrawal
  ins_control_change  insurgent_territorial_control end - withdrawal
  sec_loss_rate       security losses per 1,000 personnel per 30 days
  exchange_ratio      security losses / insurgent personnel decline (post)
  branch_gap          OFF - ON on personnel_change and gov_control_change

and checks each against the ANCHORS table. Anchor values are approximate,
drawn from widely reported figures. They are pattern targets (order of
magnitude / direction), NOT calibration targets, and every source must be
verified before citing.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

# name: (low, high, description, source note — VERIFY before citing)
ANCHORS = {
    "sec_loss_rate": (
        1.0, 15.0,
        "security-force losses (KIA+WIA+captured+deserted) per 1,000 per month in an active insurgency",
        "TODO-verify: ANDSF ~2,000-3,000 KIA/month peaks on ~300k nominal force (SIGAR, 2019-2021); "
        "attrition incl. desertion ~2-3%/month (SIGAR quarterly reports)",
    ),
    "collapse_days_vulnerable": (
        20.0, 180.0,
        "time from loss of external enablers to collapse of a dependent partner force",
        "TODO-verify: ARVN 1975 ~55 days from Ban Me Thuot to Saigon; ANDSF 2021 ~4 months from US "
        "withdrawal start (May 1) to Kabul (Aug 15); Iraqi Army Mosul 2014 within days",
    ),
    "exchange_ratio": (
        0.3, 5.0,
        "security losses per insurgent loss",
        "TODO-verify: highly case dependent; COIN datasets (e.g. Lyall & Wilson) show wide ranges",
    ),
}


def load(path: Path):
    worlds = defaultdict(lambda: defaultdict(list))
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            worlds[(r["cell_id"], r["seed"])][r["phase"]].append(r)
    return worlds


def branch_metrics(rows: list[dict], withdrawal: float) -> dict:
    rows = sorted(rows, key=lambda r: float(r["time_days"]))
    f = lambda r, k: float(r[k])
    start, end = rows[0], rows[-1]
    p0 = f(start, "military_personnel")
    collapse = math.inf
    for r in rows:
        if f(r, "military_personnel") < 0.5 * p0:
            collapse = f(r, "time_days") - withdrawal
            break
    losses = sum(f(r, "interval_military_losses") for r in rows[1:])
    months = max((f(end, "time_days") - f(start, "time_days")) / 30.0, 1e-9)
    mean_personnel = sum(f(r, "military_personnel") for r in rows) / len(rows)
    ins_decline = max(f(start, "insurgent_personnel") - f(end, "insurgent_personnel"), 1e-9)
    return {
        "collapse_days": collapse,
        "personnel_change": f(end, "military_personnel") / max(p0, 1e-9),
        "gov_control_change": f(end, "government_control") - f(start, "government_control"),
        "ins_control_change": f(end, "insurgent_territorial_control") - f(start, "insurgent_territorial_control"),
        "sec_loss_rate": 1000.0 * losses / max(mean_personnel, 1e-9) / months,
        "exchange_ratio": losses / ins_decline,
    }


def verdict(value: float, low: float, high: float) -> str:
    if math.isinf(value):
        return "never"
    return "in-range" if low <= value <= high else ("low" if value < low else "high")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trajectories", nargs="+", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    out_rows = []
    for path in a.trajectories:
        for (cell, seed), phases in load(path).items():
            withdrawal = float(phases["SUPPORT_OFF"][0]["withdrawal_time_days"])
            m = {b: branch_metrics(phases[b], withdrawal) for b in ("SUPPORT_ON", "SUPPORT_OFF")}
            off, on = m["SUPPORT_OFF"], m["SUPPORT_ON"]
            row = {"file": path.name, "cell": cell, "seed": seed}
            for k, v in off.items():
                row[f"off_{k}"] = round(v, 4) if not math.isinf(v) else "inf"
            row["gap_personnel"] = round(off["personnel_change"] - on["personnel_change"], 4)
            row["gap_gov_control"] = round(off["gov_control_change"] - on["gov_control_change"], 4)
            row["check_sec_loss_rate"] = verdict(off["sec_loss_rate"], *ANCHORS["sec_loss_rate"][:2])
            row["check_exchange_ratio"] = verdict(off["exchange_ratio"], *ANCHORS["exchange_ratio"][:2])
            row["check_collapse_days"] = verdict(off["collapse_days"], *ANCHORS["collapse_days_vulnerable"][:2])
            out_rows.append(row)
    if not out_rows:
        raise SystemExit("no paired worlds found")
    for r in out_rows:
        print(r)
    print("\nAnchors (approximate; verify sources before citing):")
    for k, (lo, hi, desc, src) in ANCHORS.items():
        print(f"  {k}: [{lo}, {hi}]  {desc}\n      {src}")
    if a.out:
        with a.out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
            w.writeheader()
            w.writerows(out_rows)
        print("wrote", a.out)


if __name__ == "__main__":
    main()
