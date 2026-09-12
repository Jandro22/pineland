#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_v3_module():
    path = HERE / "analyze_distributional_closure_v3.py"
    spec = importlib.util.spec_from_file_location("closure_v3", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def analyze(csv_path: str, out_path: str, recruitment_multiplier: float) -> None:
    source = Path(csv_path)
    df = pd.read_csv(source)
    required = {
        "pair_id",
        "stratum",
        "pre_org_active",
        "final_org_active",
        "pre_logKo",
        "pre_Mstar",
        "pre_active_owner_logF",
        "final_active_owner_logF",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"missing live-support audit columns: {missing}")

    anchor_live = (
        (df.pre_org_active.astype(int) == 1)
        & (df.pre_logKo.astype(float) > 1.0e-12)
        & (df.pre_Mstar.astype(float) > 1.0e-12)
        & (df.pre_active_owner_logF.astype(float) > 1.0e-12)
    )
    all_anchors_live = bool(anchor_live.all())
    pair_meta = df[["pair_id", "stratum"]].drop_duplicates()
    pair_count = int(pair_meta.pair_id.nunique())
    stratum_pair_counts = {
        str(k): int(v)
        for k, v in pair_meta.groupby("stratum").pair_id.nunique().to_dict().items()
    }

    # Reuse the preregistered V3 closure statistics exactly, changing only the
    # semantics of the fielded-force outcome to the corrected active-owner
    # definition.  Anchors are owner-active by construction, so the matching
    # coordinate itself is numerically unchanged on the eligible support.
    corrected = df.copy()
    corrected["final_logF"] = corrected["final_active_owner_logF"].astype(float)
    corrected["pre_logF"] = corrected["pre_active_owner_logF"].astype(float)
    temp = source.with_name(source.stem + ".active_owner_tmp.csv")
    temp_out = Path(out_path).with_name(Path(out_path).stem + ".v3_tmp.json")
    corrected.to_csv(temp, index=False)
    try:
        v3 = load_v3_module()
        v3.analyze(str(temp), str(temp_out))
        base = json.loads(temp_out.read_text(encoding="utf-8"))
    finally:
        temp.unlink(missing_ok=True)
        temp_out.unlink(missing_ok=True)

    strata_present = set(stratum_pair_counts) >= {"low", "mid", "high"}
    enough_pairs = pair_count >= 24
    balanced_enough = strata_present and all(
        stratum_pair_counts.get(s, 0) >= 6 for s in ("low", "mid", "high")
    )
    owner_inactivation_fraction = float((df.final_org_active.astype(int) == 0).mean())
    branch_pair_owner_inactivation = (
        df.assign(owner_inactive=df.final_org_active.astype(int) == 0)
        .groupby(["pair_id", "branch"], sort=True)
        .owner_inactive.any()
    )
    any_side_inactivation_fraction = float(branch_pair_owner_inactivation.mean())

    closure_pass = base.get("status") == "PASS"
    passed = all_anchors_live and enough_pairs and balanced_enough and closure_pass
    base.update(
        {
            "schema_version": "pineland.live_insurgency_closure_recertification_results.v1",
            "status": "PASS" if passed else "FAIL",
            "input": str(source),
            "input_sha256": sha256(source),
            "recruitment_multiplier": float(recruitment_multiplier),
            "fielded_force_outcome_semantics": "active-owner effective force",
            "live_support_validation": {
                "all_selected_anchor_rows_live": all_anchors_live,
                "live_anchor_fraction": float(anchor_live.mean()),
                "pair_count": pair_count,
                "stratum_pair_counts": stratum_pair_counts,
                "at_least_24_pairs": enough_pairs,
                "balanced_live_strata": balanced_enough,
            },
            "continuation_owner_inactivation": {
                "row_fraction_final_owner_inactive": owner_inactivation_fraction,
                "pair_branch_fraction_any_side_inactive": any_side_inactivation_fraction,
                "interpretation": "Owner collapse during the prospective 30-day continuation is retained as a valid future event; no branch is censored.",
            },
            "recertification_gate": {
                "closure_statistics_pass": closure_pass,
                "live_support_pass": all_anchors_live and enough_pairs and balanced_enough,
                "decision_support_recertified_for_tested_support": passed,
            },
            "interpretation_guard": "PASS re-certifies approximate distributional closure only on the prospectively selected persistent live-insurgency synthetic support, corrected active-owner F semantics, tested 30-day horizon, matching design, and outcome set. It is not historical validation or universal Markov sufficiency.",
        }
    )
    Path(out_path).write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": base["status"],
                "candidate": base.get("candidate"),
                "pair_count": pair_count,
                "stratum_pair_counts": stratum_pair_counts,
                "all_anchors_live": all_anchors_live,
                "owner_inactivation_fraction": owner_inactivation_fraction,
                "closure_summary": base.get("summary", {}),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--recruitment-multiplier", type=float, required=True)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out, ns.recruitment_multiplier)
