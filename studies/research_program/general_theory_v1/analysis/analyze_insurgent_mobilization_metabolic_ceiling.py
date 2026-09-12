#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--out',required=True); a=ap.parse_args()
    d=pd.read_csv(a.csv)
    rows=[]
    for r,g in d.groupby('recruitment_multiplier'):
        c=g[g.collapsed.astype(str).str.lower().isin(['true','1'])]
        rows.append({
            'recruitment_multiplier':float(r), 'n':int(len(g)), 'collapse_fraction':float(len(c)/len(g)),
            'median_collapse_time':None if c.empty else float(c.collapse_time.median()),
            'median_recruitment_burn':float(g.recruitment_capital_burn.median()),
            'median_capital_inflow':float(g.capital_inflow.median()),
            'median_runway_ratio':float(g.runway_ratio.median()),
            'median_final_capital':float(g.final_capital.median()),
            'median_final_rooted':float(g.final_rooted.median()),
            'median_final_operational_force':float(g.final_operational_force.median()),
            'median_final_cumulative_recruitment':float(g.final_cumulative_recruitment.median()),
            'collapse_causes':{str(k):int(v) for k,v in c.collapse_cause.value_counts().items()},
        })
    s=pd.DataFrame(rows).sort_values('recruitment_multiplier')
    collapsed=d[d.collapsed.astype(str).str.lower().isin(['true','1'])]
    cause_counts={str(k):int(v) for k,v in collapsed.collapse_cause.value_counts().items()}
    capital_share=float((collapsed.collapse_cause=='capital').mean()) if len(collapsed) else 0.0
    rates=s.recruitment_multiplier.to_numpy(float)
    collapse_fraction=s.collapse_fraction.to_numpy(float)
    finite=s.median_collapse_time.notna()
    corr_collapse=float(pd.Series(rates).corr(pd.Series(collapse_fraction),method='spearman')) if len(np.unique(collapse_fraction))>1 else None
    corr_time=float(pd.Series(s.loc[finite,'recruitment_multiplier']).corr(pd.Series(s.loc[finite,'median_collapse_time']),method='spearman')) if finite.sum()>2 else None
    low=s[s.recruitment_multiplier<=.5]
    high=s[s.recruitment_multiplier>=1.5]
    low_c=float(low.collapse_fraction.mean()) if len(low) else None
    high_c=float(high.collapse_fraction.mean()) if len(high) else None
    supported=bool(len(collapsed)>0 and capital_share>=.5 and high_c is not None and low_c is not None and high_c>low_c)
    status='MOBILIZATION_METABOLIC_CEILING_SUPPORTED' if supported else 'METABOLIC_CEILING_NOT_YET_SUPPORTED'
    out={
        'schema_version':'pineland.insurgent_mobilization_metabolic_ceiling_results.v1','status':status,
        'historical_outcomes_used':False,'input':a.csv,'input_sha256':sha256(a.csv),'seed_count':int(d.seed.nunique()),
        'cell_summary':s.to_dict('records'),'aggregate_collapse_causes':cause_counts,'capital_trigger_share_among_collapses':capital_share,
        'spearman_recruitment_vs_collapse_fraction':corr_collapse,'spearman_recruitment_vs_median_collapse_time':corr_time,
        'low_recruitment_mean_collapse_fraction':low_c,'high_recruitment_mean_collapse_fraction':high_c,
        'support_rule':'Supported only if >50% of observed collapses are capital-triggered and high-recruitment cells collapse more often than low-recruitment cells.',
        'guard':'Synthetic mechanism result only. Recruitment multipliers and internal capital are not empirical estimates.'}
    Path(a.out).write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'capital_trigger_share':capital_share,'low_collapse_fraction':low_c,'high_collapse_fraction':high_c,'cause_counts':cause_counts},indent=2))

if __name__=='__main__': main()
