"""Snapshot-bound Nepal contact diagnostics, joined by district/week identity.

Path hazard is a descriptive exposure score, not an unconditional forecast:
later opportunities depend on earlier simulated engagement outcomes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from run_aligned_predictive_competition import ROOT, frozen_core, sha256, validate_member


def member_cells(run):
    cells = defaultdict(lambda: dict(opportunity=0., expected_count=0., survival=1.,
                                    latent=0., recorded=0.))
    seen = set()
    for event in run["contacts"]:
        if event["event_id"] in seen:
            raise ValueError("duplicate contact event")
        seen.add(event["event_id"])
        cell = cells[(str(event["district_id"]), int(float(event["day"]) // 7))]
        trace = event["latent_details"].get("contact_funnel", {})
        draws = trace.get("gate_counts", {}).get("engagement_hazard_draws", 0)
        if draws:
            if draws != 1 or trace.get("hazard_draw") is None:
                raise ValueError("expected one auditable Bernoulli draw per event")
            p = float(trace["contact_hazard"])
            if not 0 <= p <= 1:
                raise ValueError("invalid hazard probability")
            cell["opportunity"] += 1
            cell["expected_count"] += p
            cell["survival"] *= 1 - p
        cell["latent"] = max(cell["latent"], float(event["realized"]))
        cell["recorded"] = max(cell["recorded"], float(event["realized"] and event["recorded"]))
    return cells


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    files = sorted(args.run_dir.glob("seed_*_agents_750.json"))
    if len(files) != 8:
        raise ValueError("requires all eight frozen Nepal seeds")
    model, diff = frozen_core()
    panel_path = ROOT / "studies/nepal_2001_2006/data/processed/district_week_panel.csv"
    panel = pd.read_csv(panel_path)
    panel["week"] = ((pd.to_datetime(panel.week_start) - pd.Timestamp("2001-11-26")).dt.days // 7)
    panel["observed_active"] = (panel.government_maoist_state_based_events > 0).astype(int)
    keys = list(zip(panel.district_id, panel.week))
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate panel cells")
    layers = ["opportunity", "expected_count", "path_hazard", "latent", "recorded"]
    accum = {name: np.zeros(len(panel)) for name in layers}
    seeds = []
    for path in files:
        run = validate_member(path, model, diff)
        if run["horizon_days"] < 1821:
            raise ValueError("incomplete horizon")
        cells = member_cells(run)
        if set(cells) - set(keys):
            raise ValueError("run contains cells outside historical panel")
        for i, key in enumerate(keys):
            cell = cells.get(key)
            if cell is None:
                continue
            for layer in layers:
                accum[layer][i] += 1 - cell["survival"] if layer == "path_hazard" else cell[layer]
        seeds.append({"seed": run["seed"], "draws": sum(c["opportunity"] for c in cells.values()),
                      "expected_contacts": sum(c["expected_count"] for c in cells.values()),
                      "realized_contacts": run["realized_contact_count"],
                      "recorded_contacts": run["recorded_realized_contact_count"]})
    for layer in layers:
        panel[layer] = accum[layer] / len(files)
    rows = []
    for split, group in panel.groupby("split"):
        y = group.observed_active
        for layer in layers:
            score = group[layer]
            support = score > 0
            rows.append(dict(split=split, layer=layer, rows=len(group), positives=int(y.sum()),
                             roc_auc=float(roc_auc_score(y, score)),
                             average_precision=float(average_precision_score(y, score)),
                             supported_cells=int(support.sum()),
                             positive_support_recall=float(y[support].sum() / y.sum()),
                             mean_score=float(score.mean())))
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out / "cell_layers.csv", index=False)
    pd.DataFrame(rows).to_csv(out / "layer_scores.csv", index=False)
    report = {"schema_version": "pineland.contact_signal_decomposition.v1", "seeds": seeds,
              "interpretation_limits": [
                  "Opportunity is eligible engagement draws, not all unscheduled potential encounters.",
                  "Path hazard = mean across seeds of 1-product(1-p) along realized paths; not an unconditional forecast or exact Rao-Blackwellization.",
                  "Zero ensemble support does not prove structural impossibility with eight seeds.",
                  "Rank metrics and support are exploratory diagnostics, not a new predictive competition.",
                  "Recorded layer follows existing realized-and-recorded bridge; false reports excluded."],
              "historical_parameter_fitting": False, "coin_science_authorized": False,
              "model_sha256": model, "tracked_diff_sha256": diff,
              "input_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in [panel_path, *[p.resolve() for p in files]]},
              "script_sha256": sha256(Path(__file__)),
              "output_sha256": {name: sha256(out / name) for name in ["cell_layers.csv", "layer_scores.csv"]}}
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
