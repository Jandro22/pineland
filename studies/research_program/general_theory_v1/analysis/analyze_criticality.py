from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def slope(g):
    x=g.time.to_numpy(float); y=np.log(g.active_footholds.to_numpy(float)+0.5)
    if len(x)<2:return 0.0
    return float(np.polyfit(x,y,1)[0])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--out',required=True); ns=ap.parse_args()
    d=pd.read_csv(ns.csv)
    keys=['seed','recruitment_mult','memory_mult','fielding_mult']
    rows=[]
    for key,g in d.groupby(keys):
        g=g.sort_values('time'); after=g[g.time>=min(30.0,float(g.time.max()))]
        first=g.iloc[0]; last=g.iloc[-1]
        rows.append(dict(zip(keys,key))|{
          'growth_slope_log_active_per_day':slope(after),
          'initial_active':float(first.active_footholds),'final_active':float(last.active_footholds),
          'final_strength':float(last.mean_foothold_strength),'final_armed':float(last.total_armed_membership),
          'final_fielded':float(last.total_fielded_personnel),'final_control_margin':float(last.mean_insurgent_control-last.mean_government_control),
          'action_increment':float(last.total_actions-first.total_actions),'recruitment_increment':float(last.total_recruitment-first.total_recruitment),
          'org_survives':int(last.insurgent_org_active>0.5),'foothold_survives':int(last.active_footholds>0.5)
        })
    r=pd.DataFrame(rows)
    cells=[]
    for key,g in r.groupby(['recruitment_mult','memory_mult','fielding_mult']):
        cells.append({'recruitment_mult':key[0],'memory_mult':key[1],'fielding_mult':key[2],
          'mean_growth_slope':float(g.growth_slope_log_active_per_day.mean()),'sd_growth_slope':float(g.growth_slope_log_active_per_day.std(ddof=1)) if len(g)>1 else 0.0,
          'p_foothold_survival':float(g.foothold_survives.mean()),'p_org_survival':float(g.org_survives.mean()),'mean_final_active':float(g.final_active.mean()),
          'mean_final_control_margin':float(g.final_control_margin.mean()),'mean_action_increment':float(g.action_increment.mean()),'mean_recruitment_increment':float(g.recruitment_increment.mean())})
    cell=pd.DataFrame(cells)
    # Monotonicity checks are within matched values of the other two factors.
    mono={}
    for fac in ['recruitment_mult','memory_mult','fielding_mult']:
        other=[x for x in ['recruitment_mult','memory_mult','fielding_mult'] if x!=fac]
        checks=[]
        for _,g in cell.groupby(other):
            g=g.sort_values(fac); vals=g.mean_growth_slope.to_numpy(); checks.append(bool(np.all(np.diff(vals)>=-1e-8)))
        mono[fac]={'matched_strata':len(checks),'nondecreasing_growth_fraction':float(np.mean(checks)) if checks else None}
    # A deliberately low-dimensional relative criticality score. It is not called R_I.
    r['log_relative_reproductive_pressure']=np.log(r.recruitment_mult)+np.log(r.memory_mult)+np.log(r.fielding_mult)
    y=r.foothold_survives.to_numpy(); groups=r.seed.to_numpy(); x=r[['log_relative_reproductive_pressure']].to_numpy()
    auc=None
    if len(np.unique(y))>1 and len(np.unique(groups))>=2:
        pred=np.zeros(len(y)); logo=LeaveOneGroupOut()
        for tr,te in logo.split(x,y,groups):
            if len(np.unique(y[tr]))<2: pred[te]=y[tr].mean()
            else:
                m=LogisticRegression().fit(x[tr],y[tr]); pred[te]=m.predict_proba(x[te])[:,1]
        auc=float(roc_auc_score(y,pred))
    # Empirical synthetic transition zone: parameter cells neither always extinct nor always persistent.
    transition=cell[(cell.p_foothold_survival>0)&(cell.p_foothold_survival<1)].to_dict('records')
    out={'schema_version':'pineland.criticality_sweep_analysis.v1','status':'synthetic_criticality_proxy_not_reproduction_operator','historical_outcomes_used':False,'input':str(Path(ns.csv)),'input_sha256':sha(ns.csv),'seed_count':int(r.seed.nunique()),'trajectory_count':len(r),'cell_count':len(cell),'matched_monotonicity':mono,'relative_pressure_survival_auc':auc,'transition_cells':transition,'cell_summaries':cells,
      'interpretation_guard':'Growth of active footholds and survival are criticality proxies only. They do not identify parent-attributed K or rho(K). A multitype genealogy instrument is still required before calling any threshold R_I.'}
    Path(ns.out).write_text(json.dumps(out,indent=2)+"\n",encoding='utf-8'); print(ns.out); print('transition cells',len(transition),'auc',auc,'monotonicity',mono)
if __name__=='__main__': main()
