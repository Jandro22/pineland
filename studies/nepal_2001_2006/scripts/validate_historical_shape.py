"""Construct-aligned historical shape validation; no simulator parameters are fitted."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import hashlib, json, math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies/nepal_2001_2006"
OUT = STUDY / "results/residual_diagnosis"
RUNS = STUDY / "runs/opportunity_nested/E_combined"
SEEDS = (20011126,20021133,20031140,20041147,20051154,20061161,20071168,20081175)
START = date(2001,11,26)
SPLITS = ("training","temporal_validation","geographic_validation","strict_joint_holdout")

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def gini(x):
    x=np.sort(np.asarray(x,float)); s=x.sum(); n=len(x)
    return float(np.sum((2*np.arange(1,n+1)-n-1)*x)/(n*s)) if s else 0.0
def spells(binary, value):
    out=[]; run=0
    for x in binary:
        if bool(x)==value: run+=1
        elif run: out.append(run); run=0
    if run: out.append(run)
    return out
def ecdf_quantiles(x):
    return {f"q{q}":float(np.quantile(x,q/100)) for q in (10,25,50,75,90)} if len(x) else {}
def moran(counts, neighbors, districts):
    x=np.array([counts.get(d,0) for d in districts],float); z=x-x.mean(); den=np.dot(z,z)
    edges=[(a,b) for a in districts for b in neighbors.get(a,[]) if b in counts or b in districts]
    num=sum(z[districts.index(a)]*z[districts.index(b)] for a,b in edges)
    return float(len(districts)/len(edges)*num/den) if den and edges else 0.0
def burstiness(times):
    gaps=np.diff(sorted(times)); m=gaps.mean() if len(gaps) else 0; sd=gaps.std() if len(gaps) else 0
    return float((sd-m)/(sd+m)) if sd+m else 0.0

def fast_shape_from_sample(sampled, hist, neighbors, districts):
    """Vectorized shape-only path for repeated count standardization."""
    counts=np.bincount(np.asarray(sampled,dtype=int),minlength=len(hist)) if len(sampled) else np.zeros(len(hist),int)
    weeks=hist.week_index.to_numpy(); district_values=hist.district_id.to_numpy()
    unique_weeks=np.arange(hist.week_index.min(),hist.week_index.max()+1)
    weekly=np.array([counts[weeks==w].sum() for w in unique_weeks],float)
    dc={d:int(counts[district_values==d].sum()) for d in districts}; values=np.array(list(dc.values()),float)
    total=values.sum(); shares=values/total if total else values
    expanded=np.repeat(weeks,counts)
    return {"weekly_fano":float(weekly.var()/weekly.mean()) if weekly.mean() else 0.0,
            "district_gini":gini(values),
            "normalized_hhi":float((np.sum(shares**2)-1/len(districts))/(1-1/len(districts))) if total else 0.0,
            "morans_i":moran(dc,neighbors,districts),"burstiness":burstiness(expanded)}

def compute(frame, neighbors, coords, districts):
    frame=frame.copy(); frame["active"]=(frame.events>0).astype(int)
    n=len(frame); active=frame.active.sum(); events=frame.events.sum()
    weekly=frame.groupby("week_index").events.sum().sort_index()
    allweeks=np.arange(frame.week_index.min(),frame.week_index.max()+1) if n else []
    weekly=weekly.reindex(allweeks,fill_value=0)
    recurrence={}
    inactive_baseline={}
    propagation={}
    for lag in (1,2,4,8):
        prev={(r.district_id,r.week_index) for r in frame.itertuples() if r.active}
        denom=len(prev)
        recurrence[str(lag)]=sum((d,w+lag) in prev for d,w in prev)/denom if denom else 0
        propagation[str(lag)]=sum(any((nb,w+lag) in prev for nb in neighbors.get(d,[])) for d,w in prev)/denom if denom else 0
        inactive=[(r.district_id,r.week_index) for r in frame.itertuples() if not r.active]
        inactive_baseline[str(lag)]=sum((d,w+lag) in prev for d,w in inactive)/len(inactive) if inactive else 0
    district_counts=frame.groupby("district_id").events.sum().reindex(districts,fill_value=0)
    shares=(district_counts/district_counts.sum()).sort_values(ascending=False) if events else district_counts
    district_series=[]; inactive_series=[]
    for _,grp in frame.sort_values("week_index").groupby("district_id"):
        binary=grp.active.tolist(); district_series.extend(spells(binary,True)); inactive_series.extend(spells(binary,False))
    expanded=[]
    for r in frame.itertuples(): expanded.extend([r.week_index]*int(r.events))
    consecutive=[]
    ordered=frame.loc[frame.events>0].sort_values(["week_index","district_id"])
    expanded_locations=[]
    for r in ordered.itertuples(): expanded_locations.extend([r.district_id]*int(r.events))
    for a,b in zip(expanded_locations,expanded_locations[1:]):
        if a in coords and b in coords: consecutive.append(math.hypot(coords[a][0]-coords[b][0],coords[a][1]-coords[b][1]))
    previously=set(); new=ret=opportunities=0
    for week,grp in frame.sort_values("week_index").groupby("week_index"):
        current=set(grp.loc[grp.active==1,"district_id"]); opportunities+=len(districts)
        new+=len(current-previously); ret+=len(current&previously); previously|=current
    mean=weekly.mean() if len(weekly) else 0
    autocorrelation={str(lag):float(weekly.autocorr(lag)) if len(weekly)>lag+1 else 0.0
                     for lag in range(1,9)}
    first_activation=[grp.loc[grp.active==1,"week_index"].min()
                      for _,grp in frame.groupby("district_id") if grp.active.any()]
    return {"cells":n,"events":int(events),"active_cells":int(active),"active_cell_share":float(active/n),
            "mean_events_per_cell":float(events/n),"zero_event_share":float(1-active/n),
            "events_per_active_cell":float(events/active) if active else 0,
            "mean_active_districts_per_week":float(active/max(1,len(weekly))),
            "weekly_fano":float(weekly.var(ddof=0)/mean) if mean else 0,
            "weekly_autocorrelation_lag_1_to_8":autocorrelation,
            "recurrence_probability":recurrence,"inactive_baseline_activation_probability":inactive_baseline,
            "adjacent_propagation_probability":propagation,
            "active_spell_weeks":ecdf_quantiles(district_series),"inactive_spell_weeks":ecdf_quantiles(inactive_series),
            "inter_event_week_ecdf":ecdf_quantiles(np.diff(sorted(expanded))),"burstiness":burstiness(expanded),
            "district_gini":gini(district_counts),"normalized_hhi":float((np.sum(shares**2)-1/len(districts))/(1-1/len(districts))) if events else 0,
            "top_decile_district_share":float(shares.iloc[:math.ceil(.1*len(districts))].sum()) if events else 0,
            "morans_i":moran(district_counts.to_dict(),neighbors,districts),
            "districts_ever_active":int((district_counts>0).sum()),
            "first_activation_week":ecdf_quantiles(first_activation),
            "consecutive_event_distance":ecdf_quantiles(consecutive),
            "new_district_activation_rate":new/opportunities if opportunities else 0,
            "return_activation_rate":ret/opportunities if opportunities else 0}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    panel=pd.read_csv(STUDY/"data/processed/district_week_panel.csv")
    panel["events"]=panel.government_maoist_state_based_events.astype(int)
    panel["week_start"]=pd.to_datetime(panel.week_start)
    panel["week_index"]=((panel.week_start-pd.Timestamp(START)).dt.days//7).astype(int)
    neighbors=json.loads((STUDY/"data/processed/district_adjacency.json").read_text())["neighbors"]
    geo=pd.read_csv(STUDY/"data/processed/district_geography.csv")
    coords={r.district_id:(float(r.x_km),float(r.y_km)) for r in geo.itertuples()}
    districts=sorted(panel.district_id.unique())
    runs=[]
    for seed in SEEDS:
        raw=json.loads((RUNS/f"seed_{seed}_agents_750.json").read_text())
        records=[]
        for e in raw["contacts"]:
            records.append({"district_id":e["district_id"],"week_index":int(e["day"]//7),
                            "latent":int(e["realized"]),"recorded":int(e["realized"] and e["recorded"])})
        runs.append(pd.DataFrame(records))
    result={"schema_version":"1.0.0","parameter_fit":False,"primary_stream":"recorded_engagement",
            "arithmetic_invariant":"recorded_active_cells <= recorded_engagements <= latent_engagements",
            "splits":{},"count_standardized":{}}
    rng=np.random.default_rng(20260904)
    for split in SPLITS:
        hist=panel[panel.split==split].copy(); h=compute(hist,neighbors,coords,districts)
        rec=[]; lat=[]
        valid=set(zip(hist.district_id,hist.week_index))
        template=hist[["district_id","week_index"]]
        for events in runs:
            def model_frame(column):
                counts=Counter((r.district_id,r.week_index) for r in events.itertuples()
                               if getattr(r,column) and (r.district_id,r.week_index) in valid)
                f=template.copy(); f["events"]=[counts[(d,w)] for d,w in zip(f.district_id,f.week_index)]
                return f
            rf=model_frame("recorded"); lf=model_frame("latent")
            assert int((rf.events>0).sum()) <= int(rf.events.sum()) <= int(lf.events.sum())
            rec.append(compute(rf,neighbors,coords,districts)); lat.append(compute(lf,neighbors,coords,districts))
        keys=[k for k,v in rec[0].items() if isinstance(v,(int,float))]
        result["splits"][split]={"historical":h,
            "recorded_mean":{k:float(np.mean([x[k] for x in rec])) for k in keys},
            "recorded_runs":rec,"latent_runs":lat}
        # Deterministically thin the larger stream in each run to the smaller total.
        standardized=[]
        hist_events=np.repeat(np.arange(len(hist)),hist.events.to_numpy())
        shape_keys=("weekly_fano","district_gini","normalized_hhi","morans_i","burstiness")
        for rf_metrics in rec:
            target=min(len(hist_events),rf_metrics["events"])
            for _ in range(100):
                sampled=rng.choice(hist_events,target,replace=False) if target else []
                standardized.append(fast_shape_from_sample(sampled,hist,neighbors,districts))
        result["count_standardized"][split]={"method":"100 deterministic without-replacement historical thinnings per simulated seed",
            "resamples":len(standardized),"historical_thinned_summary":{
                k:{"mean":float(np.mean([x[k] for x in standardized])),
                   "q025":float(np.quantile([x[k] for x in standardized],.025)),
                   "q975":float(np.quantile([x[k] for x in standardized],.975))} for k in shape_keys},
            "model_recorded_mean":{k:float(np.mean([x[k] for x in rec])) for k in shape_keys}}
    result["frozen_hashes"]={"split_manifest":sha(STUDY/"config/split_manifest.json"),
                              "case_environment":sha(STUDY/"config/case_environment.json"),
                              "simulation":sha(ROOT/"src/pineland_sim/simulation.py"),
                              "processes":sha(ROOT/"src/pineland_sim/processes.py"),
                              "config":sha(ROOT/"src/pineland_sim/config.py"),
                              "world":sha(ROOT/"src/pineland_sim/world.py"),
                              "information":sha(ROOT/"src/pineland_sim/information.py"),
                              "combat":sha(ROOT/"src/pineland_sim/combat.py"),
                              "generator":sha(ROOT/"src/pineland_sim/generator.py"),
                              "logistics":sha(ROOT/"src/pineland_sim/logistics.py")}
    (OUT/"historical_shape_validation.json").write_text(json.dumps(result,indent=2)+"\n")
    (OUT/"residual_shape_metrics.json").write_text(json.dumps(result,indent=2)+"\n")
    (OUT/"frozen_formulation.json").write_text(json.dumps({"selected_before_validation":True,
        "mechanisms":["pair-specific opportunities","explicit time-unit hazard","directional initiation",
        "target exposure independent of readiness","outcome-independent formation decomposition",
        "conditioned actor persistence","organization-scaled logistics","recording downstream of latent engagement"],
        "hashes":result["frozen_hashes"]},indent=2)+"\n")
    print(OUT/"historical_shape_validation.json")
if __name__=="__main__": main()
