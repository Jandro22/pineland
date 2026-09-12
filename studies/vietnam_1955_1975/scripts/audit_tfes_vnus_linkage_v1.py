from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default=str(ROOT / "studies/vietnam_1955_1975/data/derived/tfes_vnus_linkage_audit_v1.json"),
    )
    ns = ap.parse_args()

    t = pd.read_parquet(ROOT / "studies/vietnam_1955_1975/data/derived/tfes_direct_unit_month_1970_1972.parquet")
    v = pd.read_parquet(ROOT / "studies/vietnam_1955_1975/data/derived/vnus_direct_unit_month_1971_1972.parquet")
    t = t[t.stat_code.eq("0")].copy()
    t["month_key"] = pd.to_datetime(t.report_month).dt.to_period("M").astype(str)
    v = v[v.date_status.eq("valid_source_date")].copy()
    v["month_key"] = pd.to_datetime(v.report_date).dt.to_period("M").astype(str)
    overlap = sorted(set(t.month_key) & set(v.month_key))
    t = t[t.month_key.isin(overlap)].copy()
    v = v[v.month_key.isin(overlap)].copy()

    t["key_series"] = t.district_id.astype(str) + ":" + t.unit_type.astype(str) + ":" + t.unit_series.astype(str)
    t["key_num_last3"] = t.district_id.astype(str) + ":" + t.unit_type.astype(str) + ":" + t.unit_number.astype(str).str[-3:]
    t["key_num_first3"] = t.district_id.astype(str) + ":" + t.unit_type.astype(str) + ":" + t.unit_number.astype(str).str[:3]
    numeric_unit = pd.to_numeric(t.unit_number, errors="coerce")
    numeric_key = numeric_unit.fillna(-1).astype(int).astype(str).str.zfill(3).str[-3:]
    t["key_num_numeric3"] = t.district_id.astype(str) + ":" + t.unit_type.astype(str) + ":" + numeric_key
    v["key_vnus"] = v.logical_unit_id_vnus.astype(str)

    candidates = {}
    v_pairs = list(zip(v.month_key, v.key_vnus))
    v_pair_set = set(v_pairs)
    for name in ["key_series", "key_num_last3", "key_num_first3", "key_num_numeric3"]:
        t_pairs = list(zip(t.month_key, t[name]))
        t_pair_set = set(t_pairs)
        vmatch = np.array([x in t_pair_set for x in v_pairs], dtype=bool)
        tmatch = np.array([x in v_pair_set for x in t_pairs], dtype=bool)
        candidates[name] = {
            "vnus_rows": int(len(v)),
            "vnus_rows_matched_same_month": int(vmatch.sum()),
            "vnus_match_rate": float(vmatch.mean()),
            "tfes_rows": int(len(t)),
            "tfes_rows_matched_same_month": int(tmatch.sum()),
            "tfes_match_rate": float(tmatch.mean()),
            "tfes_unique_candidate_ids": int(t[name].nunique()),
            "vnus_unique_ids": int(v.key_vnus.nunique()),
        }

    best = max(candidates, key=lambda k: candidates[k]["vnus_match_rate"])
    best_pair_set = set(zip(t.month_key, t[best]))
    v["matched_best"] = [x in best_pair_set for x in zip(v.month_key, v.key_vnus)]
    per_month = []
    for month in overlap:
        g = v[v.month_key.eq(month)]
        per_month.append(
            {
                "month": month,
                "vnus_rows": int(len(g)),
                "matched_rows": int(g.matched_best.sum()),
                "match_rate": float(g.matched_best.mean()) if len(g) else None,
            }
        )
    type_rates = []
    for typ, g in v.groupby("unit_type", dropna=False):
        type_rates.append(
            {
                "unit_type": str(typ),
                "vnus_rows": int(len(g)),
                "matched_rows": int(g.matched_best.sum()),
                "match_rate": float(g.matched_best.mean()),
            }
        )
    type_rates.sort(key=lambda x: x["vnus_rows"], reverse=True)

    # Linkage is frozen on identity coverage only. No outcome/quality columns are
    # read into the candidate selection logic above.
    result = {
        "schema_version": "pineland.vietnam_tfes_vnus_linkage_audit.v1",
        "status": "IDENTITY_ONLY_LINKAGE_AUDIT",
        "overlap_months": overlap,
        "candidate_key_definitions": {
            "key_series": "TFES district_id + unit_type + unit_series versus VNUS district + unit_type + three-digit unit id",
            "key_num_last3": "TFES district_id + unit_type + final 3 chars of unit_number",
            "key_num_first3": "TFES district_id + unit_type + first 3 chars of unit_number",
            "key_num_numeric3": "TFES district_id + unit_type + numeric unit_number reduced to 3-digit suffix",
        },
        "candidates": candidates,
        "best_identity_candidate": best,
        "best_candidate_per_month": per_month,
        "best_candidate_by_vnus_unit_type": type_rates,
        "selection_guard": "Best key selected only by same-month identifier overlap. No TFES quality/manpower fields or VNUS operations/casualty outcomes enter mapping selection.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
