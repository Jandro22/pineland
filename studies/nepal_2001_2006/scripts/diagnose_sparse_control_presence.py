"""Untuned application of the predeclared ordinal control projection."""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]; STUDY=ROOT/"studies/nepal_2001_2006"
OUT=STUDY/"results/residual_diagnosis"; START=date(2001,11,26)
SEEDS=(20011126,20021133,20031140,20041147,20051154,20061161,20071168,20081175)
DIMS=("administrative","legal","fiscal","physical","social")
def project(control):
    g=sum(control["government"][d] for d in DIMS)/len(DIMS); m=sum(control["insurgent"][d] for d in DIMS)/len(DIMS)
    return ("STATE_DOMINANT" if g-m>.2 else "MAOIST_DOMINANT" if m-g>.2 else "CONTESTED"),g,m
def main():
    evidence=pd.read_csv(STUDY/"data/processed/nepal_sparse_control_presence.csv")
    rows=[]
    for e in evidence.to_dict("records"):
        midpoint=pd.Timestamp(e["start_date"])+(pd.Timestamp(e["end_date"])-pd.Timestamp(e["start_date"]))/2
        day=(midpoint.date()-START).days
        if day<0: continue
        for seed in SEEDS:
            run=json.loads((STUDY/"runs/opportunity_nested/E_combined"/f"seed_{seed}_agents_750.json").read_text())
            checkpoint=min(run["checkpoints"],key=lambda x:abs(float(x["time"])-day))
            predicted,g,m=project(checkpoint["control"][e["district_id"]])
            rows.append({"district_id":e["district_id"],"district_name":e["district_name"],"observed_class":e["class"],
                         "seed":seed,"target_day":day,"checkpoint_day":checkpoint["time"],"predicted_class":predicted,
                         "government_score":g,"maoist_score":m,"correct":predicted==e["class"]})
    payload={"parameter_fit":False,"projection_frozen_before_accuracy":True,"observations_in_period":len(set((r["district_id"],r["target_day"]) for r in rows)),
             "seed_observation_predictions":len(rows),"accuracy":sum(r["correct"] for r in rows)/len(rows) if rows else None,
             "rows":rows,"interpretation":"Exploratory sparse diagnostic only; evidence is purposive and too sparse for validation claims."}
    (OUT/"sparse_control_presence_diagnostic.json").write_text(json.dumps(payload,indent=2)+"\n");print(json.dumps({k:v for k,v in payload.items() if k!="rows"},indent=2))
if __name__=="__main__":main()
