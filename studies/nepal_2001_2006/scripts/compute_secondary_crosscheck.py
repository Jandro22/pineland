"""Compare independent INSEC cumulative district totals with UCDP spatial burden."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
DATA = STUDY / "data" / "processed"
OUT = STUDY / "results" / "historical"


def main() -> None:
    insec = pd.read_csv(DATA / "insec_district_totals.csv")
    ucdp = pd.read_csv(DATA / "ucdp_nepal_events.csv")
    ucdp = ucdp[ucdp.district_id.notna()].copy()
    ucdp_counts = ucdp.groupby("district_id").size().rename("ucdp_recorded_events_2001_2006")
    merged = insec.merge(ucdp_counts, on="district_id", how="left")
    merged["ucdp_recorded_events_2001_2006"] = merged.ucdp_recorded_events_2001_2006.fillna(0).astype(int)
    observed = merged[merged.source_status == "observed"].copy()
    rho, pvalue = spearmanr(observed.victim_total_cumulative,
                            observed.ucdp_recorded_events_2001_2006)
    top_n = 10
    insec_top = set(observed.nlargest(top_n, "victim_total_cumulative").district_id)
    ucdp_top = set(observed.nlargest(top_n, "ucdp_recorded_events_2001_2006").district_id)
    result = {
        "schema_version": "1.0.0",
        "secondary_source": "INSEC complete district report",
        "primary_source": "UCDP GED 26.1",
        "comparison": "district spatial burden only; INSEC cumulative 1996-02-13--2006-11-21 vs UCDP recorded events 2001-11-26--2006-11-21",
        "districts_compared": int(len(observed)),
        "districts_excluded_not_listed": int((merged.source_status != "observed").sum()),
        "spearman_rank_correlation": float(rho), "spearman_pvalue": float(pvalue),
        "top_10_overlap_count": int(len(insec_top & ucdp_top)),
        "interpretation": "This is a spatial cross-check, not evidence that either source is ground truth or that cumulative totals are district-week equivalent.",
        "source_hashes": {"insec_totals": __import__("hashlib").sha256((DATA / "insec_district_totals.csv").read_bytes()).hexdigest(),
                          "ucdp_events": __import__("hashlib").sha256((DATA / "ucdp_nepal_events.csv").read_bytes()).hexdigest()},
    }
    merged.to_csv(OUT / "insec_ucdp_district_crosscheck.csv", index=False)
    (OUT / "insec_ucdp_crosscheck.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
