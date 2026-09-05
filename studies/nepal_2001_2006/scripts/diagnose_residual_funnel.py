"""Observed trajectory funnel and recording distortion diagnostics."""
from __future__ import annotations
from collections import Counter, defaultdict
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]; STUDY=ROOT/"studies/nepal_2001_2006"
OUT=STUDY/"results/residual_diagnosis"; SEEDS=(20011126,20021133,20031140,20041147,20051154,20061161,20071168,20081175)

def main():
    OUT.mkdir(parents=True,exist_ok=True); runs=[]; gates=Counter(); reasons=Counter(); contacts=[]
    for seed in SEEDS:
        row=json.loads((STUDY/"runs/opportunity_nested/E_combined"/f"seed_{seed}_agents_750.json").read_text()); runs.append(row)
        for trace in row["contact_funnel"]:
            gates.update({k:int(v) for k,v in trace["gate_counts"].items() if isinstance(v,(int,float))})
            reasons[trace["failure_reason"]]+=1
        contacts.extend([{**e,"seed":seed} for e in row["contacts"] if e["realized"]])
    attempts=sum(len(r["contact_funnel"]) for r in runs); latent=sum(e["realized"] for e in contacts)
    recorded=sum(e["recorded"] for e in contacts)
    geo=pd.read_csv(STUDY/"data/processed/district_geography.csv").set_index("district_id")
    case=json.loads((STUDY/"config/case_environment.json").read_text())
    local={x["locality_id"]:x for x in case["localities"]}
    strata=defaultdict(lambda:[0,0])
    for e in contacts:
        loc=local[e["district_id"]]; access=float(loc.get("observability",.5)); terrain=float(loc.get("terrain_friction",1))
        sev=float(e["reported_severity"]); when=int(e["day"]//365)
        labels={"accessibility:"+("high" if access>=.5 else "low"),
                "terrain:"+("high" if terrain>=1 else "low"),
                "severity:"+("high" if sev>=.01 else "low"),f"year:{when+1}",
                "actor:"+str(e.get("reported_actor") or "unknown")}
        for label in labels: strata[label][0]+=int(e["recorded"]); strata[label][1]+=1
    payload={"attempts":attempts,"candidate_pairs":gates["opposing_formation_candidate_pairs"],
             "microzone_eligible_pairs":gates["microzone_eligible_candidate_pairs"],
             "detected_opponent_sides":gates["detected_opponent_sides"],
             "initiation_hazard_draws":gates["engagement_hazard_draws"],
             "hazard_passes":gates["engagement_hazard_passes"],"latent_engagements":latent,
             "recorded_engagements":recorded,"p_recorded_given_latent":recorded/latent,
             "loss_fraction_by_stage":{"opportunity_to_latent":1-latent/max(1,attempts),
                                       "latent_to_recorded":1-recorded/max(1,latent)},
             "failure_reasons":dict(reasons),
             "recording_strata":{k:{"recorded":v[0],"latent":v[1],"probability":v[0]/v[1]} for k,v in sorted(strata.items())},
             "interpretation":"Counts are realized trajectory transitions, not deductions from parameter values."}
    (OUT/"residual_funnel.json").write_text(json.dumps(payload,indent=2)+"\n")
    print(json.dumps(payload,indent=2))
if __name__=="__main__":main()
