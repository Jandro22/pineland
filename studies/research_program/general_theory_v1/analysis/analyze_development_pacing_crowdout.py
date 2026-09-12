#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--out',required=True); a=ap.parse_args()
    d=pd.read_csv(a.csv)
    summaries={}
    for m,g in d.groupby('budget_multiplier'):
        g=g.sort_values(['seed','time'])
        per_seed=[]
        for seed,s in g.groupby('seed'):
            anchor=float(s.anchor_government_capital.iloc[0]); threshold=.1*anchor
            hit=s[s.government_capital<=threshold]
            final=s.iloc[-1]
            per_seed.append({
                'seed':int(seed),'first_below_10pct_day':float(hit.time.iloc[0]) if len(hit) else None,
                'total_outflow':float(s.interval_outflow.sum()),'political_outflow':float(s.interval_political_outflow.sum()),
                'regeneration_outflow':float(s.interval_state_regeneration_outflow.sum()),'governance_outflow':float(s.interval_governance_outflow.sum()),
                'final_legitimacy':float(final.mean_government_legitimacy),'final_capacity':float(final.mean_local_institution_capacity),
                'final_control':float(final.population_weighted_government_control),'final_capital':float(final.government_capital),
            })
        x=pd.DataFrame(per_seed)
        summaries[str(float(m))]={
            'mean_total_outflow':float(x.total_outflow.mean()),'mean_political_outflow':float(x.political_outflow.mean()),
            'mean_regeneration_outflow':float(x.regeneration_outflow.mean()),'mean_governance_outflow':float(x.governance_outflow.mean()),
            'median_first_below_10pct_day':float(x.first_below_10pct_day.dropna().median()) if x.first_below_10pct_day.notna().any() else None,
            'mean_final_legitimacy':float(x.final_legitimacy.mean()),'mean_final_capacity':float(x.final_capacity.mean()),
            'mean_final_control':float(x.final_control.mean()),'mean_final_capital':float(x.final_capital.mean()),
        }
    s5=summaries['5.0']; s20=summaries['20.0']
    total_diff=abs(s20['mean_total_outflow']-s5['mean_total_outflow'])/max(s5['mean_total_outflow'],1e-12)
    earlier=(s20['median_first_below_10pct_day'] is not None and s5['median_first_below_10pct_day'] is not None and s20['median_first_below_10pct_day']<s5['median_first_below_10pct_day'])
    worse=(s20['mean_final_legitimacy']<s5['mean_final_legitimacy'] and s20['mean_final_capacity']<s5['mean_final_capacity'])
    crowd=(s20['mean_regeneration_outflow']<s5['mean_regeneration_outflow'])
    gates={'5x_20x_total_outflow_within_1pct':total_diff<.01,'20x_exhausts_earlier':earlier,'20x_worse_legitimacy_and_capacity':worse,'20x_lower_regeneration_outflow':crowd}
    result={'schema_version':'pineland.development_pacing_crowdout_results.v1','status':'PACING_AND_CROWDOUT_SUPPORTED' if all(gates.values()) else 'PACING_CROWDOUT_GATES_NOT_ALL_MET','historical_outcomes_used':False,'input':a.csv,'input_sha256':sha256(a.csv),'seed_count':int(d.seed.nunique()),'summaries':summaries,'primary_gates':gates,'relative_total_outflow_difference_5x_vs_20x':total_diff,'guard':'Synthetic capital-pacing mechanism only; internal capital is not real dollars.'}
    Path(a.out).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8'); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
