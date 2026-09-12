#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import pandas as pd

def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--out',required=True); a=ap.parse_args()
    d=pd.read_csv(a.csv)
    per=[]
    for (schedule,seed),s in d.sort_values(['schedule','seed','time']).groupby(['schedule','seed']):
        anchor=float(s.anchor_government_capital.iloc[0]); hit=s[s.government_capital<=.1*anchor]; final=s.iloc[-1]
        per.append({
          'schedule':schedule,'seed':int(seed),'total_outflow':float(s.interval_outflow.sum()),
          'political_outflow':float(s.interval_political_outflow.sum()),'governance_outflow':float(s.interval_governance_outflow.sum()),
          'regeneration_outflow':float(s.interval_state_regeneration_outflow.sum()),
          'first_below_10pct_day':float(hit.time.iloc[0]) if len(hit) else None,
          'final_legitimacy':float(final.mean_government_legitimacy),'final_capacity':float(final.mean_local_institution_capacity),
          'final_control':float(final.population_weighted_government_control),'final_capital':float(final.government_capital)})
    p=pd.DataFrame(per)
    summaries={}
    for schedule,g in p.groupby('schedule'):
        summaries[schedule]={
          'mean_total_outflow':float(g.total_outflow.mean()),'mean_political_outflow':float(g.political_outflow.mean()),
          'mean_governance_outflow':float(g.governance_outflow.mean()),'mean_regeneration_outflow':float(g.regeneration_outflow.mean()),
          'median_first_below_10pct_day':float(g.first_below_10pct_day.dropna().median()) if g.first_below_10pct_day.notna().any() else None,
          'mean_final_legitimacy':float(g.final_legitimacy.mean()),'mean_final_capacity':float(g.final_capacity.mean()),
          'mean_final_control':float(g.final_control.mean()),'mean_final_capital':float(g.final_capital.mean())}
    pairs=[]
    names=sorted(summaries)
    for i,left in enumerate(names):
        for right in names[i+1:]:
            a1=summaries[left]; b1=summaries[right]
            rel=abs(a1['mean_total_outflow']-b1['mean_total_outflow'])/max(min(a1['mean_total_outflow'],b1['mean_total_outflow']),1e-12)
            pairs.append({'left':left,'right':right,'within_1pct_total_outflow':rel<=.01,'relative_total_outflow_difference':rel,
                          'right_minus_left_governance_outflow':b1['mean_governance_outflow']-a1['mean_governance_outflow'],
                          'right_minus_left_legitimacy':b1['mean_final_legitimacy']-a1['mean_final_legitimacy'],
                          'right_minus_left_capacity':b1['mean_final_capacity']-a1['mean_final_capacity'],
                          'right_minus_left_control':b1['mean_final_control']-a1['mean_final_control']})
    immediate=summaries['immediate20']
    sequencing=[]
    for candidate in ['delayed20','ramp20']:
        x=summaries[candidate]
        rel=abs(x['mean_total_outflow']-immediate['mean_total_outflow'])/max(immediate['mean_total_outflow'],1e-12)
        sequencing.append({'schedule':candidate,'within_1pct_total_outflow':rel<=.01,
            'more_governance':x['mean_governance_outflow']>immediate['mean_governance_outflow'],
            'better_legitimacy':x['mean_final_legitimacy']>immediate['mean_final_legitimacy'],
            'better_capacity':x['mean_final_capacity']>immediate['mean_final_capacity'],
            'better_control':x['mean_final_control']>immediate['mean_final_control'],
            'relative_total_outflow_difference':rel})
    supported=any(all(v for k,v in row.items() if k not in ['schedule','relative_total_outflow_difference']) for row in sequencing)
    status='CAPACITY_FIRST_SEQUENCING_SUPPORTED' if supported else 'SEQUENCING_BENEFIT_NOT_FULLY_SUPPORTED'
    result={'schema_version':'pineland.development_sequence_frontier_results.v1','status':status,'historical_outcomes_used':False,
      'input':a.csv,'input_sha256':sha256(a.csv),'seed_count':int(d.seed.nunique()),'summaries':summaries,
      'same_spend_pairwise':pairs,'immediate20_sequence_tests':sequencing,
      'guard':'Synthetic temporal-allocation mechanism only; internal capital is not real dollars.'}
    Path(a.out).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':status,'tests':sequencing},indent=2))
if __name__=='__main__': main()
