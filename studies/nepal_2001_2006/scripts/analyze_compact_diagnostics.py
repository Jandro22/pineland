"""Shape, mechanism, persistence, and diffusion summaries for compact runs."""
from __future__ import annotations
from collections import Counter
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(HERE))
from validate_historical_shape import compute
STUDY=ROOT/"studies/nepal_2001_2006";DIR=STUDY/"results/residual_diagnosis/sensitivities"
SEEDS=(20011126,20051154); DESIGNS=json.loads((DIR/"summary.json").read_text())["designs"]

def summarize(values):return {"mean":float(np.mean(values)),"sd":float(np.std(values,ddof=1)),"min":float(min(values)),"max":float(max(values))}
def main():
    adjacency=json.loads((STUDY/"data/processed/district_adjacency.json").read_text())["neighbors"]
    geo=pd.read_csv(STUDY/"data/processed/district_geography.csv"); districts=sorted(geo.district_id)
    coords={r.district_id:(r.x_km,r.y_km) for r in geo.itertuples()}; output={"designs":{}}
    for name in DESIGNS:
        per=[]
        for seed in SEEDS:
            r=json.loads((DIR/f"{name}_seed_{seed}.json").read_text()); counts=Counter((e["district_id"],int(e["day"]//7)) for e in r["recorded_stream"])
            frame=pd.DataFrame([(d,w,counts[(d,w)]) for d in districts for w in range(53)],columns=["district_id","week_index","events"])
            m=compute(frame,adjacency,coords,districts); m.update({"opportunities":len(r["contact_funnel"]),
                "movement_orders":len(r["movement_history"]),"movement_arrivals":sum(x["status"]=="arrived" for x in r["movement_history"]),
                "final_mean_readiness":float(np.mean([x["readiness"] for x in r["final_formations"]])),
                "final_mean_supply":float(np.mean([x["supply_fraction"] for x in r["final_formations"]])),
                "final_active_formations":sum(x["operational_status"]=="effective" and not x["moving"] for x in r["final_formations"])})
            per.append(m)
        keys=("events","active_cells","weekly_fano","district_gini","morans_i","new_district_activation_rate","return_activation_rate","opportunities","movement_orders","movement_arrivals","final_mean_readiness","final_mean_supply","final_active_formations")
        output["designs"][name]={k:summarize([x[k] for x in per]) for k in keys}
    # Engagement-level post-event movement and renewal on the repaired baseline.
    lags=(1,2,4,8); persistence={k:{"renewed_same_district":0,"events":0,"involved_formation_departures":0,
                                   "reinforcement_orders":0} for k in lags}
    for seed in SEEDS:
        r=json.loads((DIR/f"baseline_seed_{seed}.json").read_text()); events=r["latent_stream"]
        for e in events:
            trace=e["latent_details"]["contact_funnel"]; involved={trace["selected_government_formation_id"],trace["selected_insurgent_formation_id"]}
            for lag in lags:
                future=[x for x in events if e["day"]<x["day"]<=e["day"]+7*lag]
                orders=[x for x in r["movement_history"] if x["formation_id"] in involved and e["day"]<x["issued_at"]<=e["day"]+7*lag]
                p=persistence[lag];p["events"]+=1;p["renewed_same_district"]+=int(any(x["district_id"]==e["district_id"] for x in future));p["involved_formation_departures"]+=int(bool(orders));p["reinforcement_orders"]+=int(bool(e["latent_details"].get("reinforcement_order_ids")))
    for lag,p in persistence.items():
        n=p["events"];p["renewal_probability"]=p["renewed_same_district"]/n;p["departure_probability"]=p["involved_formation_departures"]/n;p["reinforcement_probability"]=p["reinforcement_orders"]/n
    output["post_engagement_persistence"]=persistence
    (DIR.parent/"compact_mechanism_diagnostics.json").write_text(json.dumps(output,indent=2)+"\n");print(DIR.parent/"compact_mechanism_diagnostics.json")
if __name__=="__main__":main()
