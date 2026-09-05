"""Training-only probabilistic competitors for binary district-week incidence."""
from __future__ import annotations
from collections import Counter
from datetime import date
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score,average_precision_score
from sklearn.linear_model import LogisticRegression

ROOT=Path(__file__).resolve().parents[3]; STUDY=ROOT/"studies/nepal_2001_2006"
OUT=STUDY/"results/residual_diagnosis"; START=date(2001,11,26)
SEEDS=(20011126,20021133,20031140,20041147,20051154,20061161,20071168,20081175)

def scores(y,p):
    p=np.clip(np.asarray(p,float),1e-9,1-1e-9); y=np.asarray(y,float)
    logits=np.log(p/(1-p)).reshape(-1,1)
    calibration=LogisticRegression(C=1e9).fit(logits,y) if len(set(y))>1 else None
    bins=np.minimum(4,(p*5).astype(int)); reliability=[{"bin":int(b),"n":int((bins==b).sum()),
        "predicted":float(p[bins==b].mean()),"observed":float(y[bins==b].mean())} for b in sorted(set(bins))]
    return {"log_score":float(np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
            "brier":float(np.mean((y-p)**2)),"observed_rate":float(y.mean()),
            "predicted_rate":float(p.mean()),"roc_auc":float(roc_auc_score(y,p)) if len(set(y))>1 else None,
            "pr_auc":float(average_precision_score(y,p)) if len(set(y))>1 else None,
            "calibration_intercept":float(calibration.intercept_[0]) if calibration else None,
            "calibration_slope":float(calibration.coef_[0,0]) if calibration else None,
            "mean_probability_positive":float(p[y==1].mean()) if y.sum() else None,
            "mean_probability_negative":float(p[y==0].mean()) if (y==0).sum() else None,
            "reliability_curve":json.dumps(reliability,separators=(",",":"))}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    panel=pd.read_csv(STUDY/"data/processed/district_week_panel.csv")
    panel["y"]=(panel.government_maoist_state_based_events>0).astype(int)
    panel["week_start"]=pd.to_datetime(panel.week_start)
    panel["week_index"]=((panel.week_start-pd.Timestamp(START)).dt.days//7).astype(int)
    train=panel[panel.split=="training"]; global_p=(train.y.sum()+1)/(len(train)+2)
    by=train.groupby("district_id").y.agg(["sum","count"]); k=8
    district_p=((by["sum"]+k*global_p)/(by["count"]+k)).to_dict()
    neighbors=json.loads((STUDY/"data/processed/district_adjacency.json").read_text())["neighbors"]
    def simulator_cells(variant):
        cells=[]
        for seed in SEEDS:
            raw=json.loads((STUDY/f"runs/opportunity_nested/{variant}"/f"seed_{seed}_agents_750.json").read_text())
            cells.append({(e["district_id"],int(e["day"]//7)) for e in raw["contacts"] if e["realized"] and e["recorded"]})
        return cells
    pineland=simulator_cells("E_combined"); reduced=simulator_cells("C_decomposition")
    rows=[]
    for split in ("training","temporal_validation","geographic_validation","strict_joint_holdout"):
        f=panel[panel.split==split].sort_values(["week_index","district_id"]).copy(); y=f.y.to_numpy()
        predictions={"global_logit":np.repeat(global_p,len(f)),
                     "district_empirical_bayes":f.district_id.map(district_p).fillna(global_p).to_numpy()}
        spatial=[]; self_exciting=[]; history=Counter()
        for r in f.itertuples():
            base=district_p.get(r.district_id,global_p)
            neighbor=np.mean([district_p.get(n,global_p) for n in neighbors.get(r.district_id,[])])
            spatial.append(np.clip(.5*base+.5*neighbor,1e-6,1-1e-6))
            excitation=sum(math.exp(-.25*(r.week_index-w)) for (d,w),v in history.items()
                           if d==r.district_id and w<r.week_index for _ in range(v))
            self_exciting.append(1-math.exp(-(-math.log(1-base)+.30*excitation)))
            if r.y: history[(r.district_id,r.week_index)]+=1
        predictions["spatial_incidence"]=spatial; predictions["self_exciting_hazard"]=self_exciting
        predictions["full_pineland"]=np.array([sum((d,w) in s for s in pineland)/len(pineland)
                                                  for d,w in zip(f.district_id,f.week_index)])
        predictions["reduced_pineland"]=np.array([sum((d,w) in s for s in reduced)/len(reduced)
                                                     for d,w in zip(f.district_id,f.week_index)])
        for model,p in predictions.items(): rows.append({"split":split,"model":model,**scores(y,p),
                                                          "fit_scope":"training only" if model!="full_pineland" else "untuned simulator"})
    pd.DataFrame(rows).to_csv(OUT/"binary_competitor_scores.csv",index=False)
    from pineland_sim.reproducibility import build_run_manifest, file_sha256
    run_inputs = [
        STUDY/f"runs/opportunity_nested/{variant}"/f"seed_{seed}_agents_750.json"
        for variant in ("E_combined", "C_decomposition") for seed in SEEDS
    ]
    analysis_config = {
        "target": "district-week >=1 state-based government-CPN-M event",
        "training_only": True,
        "holdout_refit": False,
        "pineland_parameter_fit": False,
        "models": [
            "global_logit", "district_empirical_bayes", "spatial_incidence",
            "self_exciting_hazard", "full_pineland", "reduced_pineland",
        ],
        "district_empirical_bayes_prior_weeks": 8,
        "self_excitation_alpha": .30,
        "self_excitation_decay_per_week": .25,
    }
    manifest = build_run_manifest(
        analysis_config,
        seeds=SEEDS,
        execution_mode={
            "mode": "deterministic_binary_competitor_scoring_from_fixed_simulator_seeds",
            "workers": 1,
            "process_isolated": False,
        },
        output_schema={
            "name": "nepal_binary_competitor_scores",
            "version": "2.0.0",
            "scores_format": "csv",
            "manifest_format": "json",
        },
        case_files=[
            STUDY/"data/processed/district_week_panel.csv",
            STUDY/"data/processed/district_adjacency.json",
            STUDY/"data/manifests/sources.json",
            *run_inputs,
        ],
        split_file=STUDY/"config/split_manifest.json",
        repo_root=ROOT,
        extra={"runner_sha256": file_sha256(Path(__file__))},
    )
    manifest.update(analysis_config)
    manifest["scores_file_sha256"] = file_sha256(OUT/"binary_competitor_scores.csv")
    (OUT/"binary_competitor_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(pd.DataFrame(rows).to_string(index=False))
if __name__=="__main__": main()
