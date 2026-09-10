from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score,brier_score_loss
from sklearn.model_selection import LeaveOneGroupOut

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def oof(X,y,g):
 pred=np.zeros(len(y));logo=LeaveOneGroupOut()
 for tr,te in logo.split(X,y,g):
  if len(np.unique(y[tr]))<2:pred[te]=y[tr].mean()
  else:
   m=LogisticRegression(max_iter=2000).fit(X[tr],y[tr]);pred[te]=m.predict_proba(X[te])[:,1]
 return (float(roc_auc_score(y,pred)) if len(np.unique(y))>1 else None,float(brier_score_loss(y,pred)))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--out',required=True);a=ap.parse_args()
 d=pd.read_csv(a.csv).sort_values('time')
 keys=['seed','recruitment_mult','memory_mult','fielding_mult']
 last=d.groupby(keys).tail(1).copy()
 last['org_survival']=(last.insurgent_org_active>.5).astype(int)
 last['rooted_reproduction_stock']=(last.total_armed_membership>1e-9).astype(int)
 last['foothold_memory']=(last.active_footholds>.5).astype(int)
 last['coercive_shell']=(last.total_fielded_personnel>75).astype(int)
 last['renewing_survival']=(last.org_survival & last.rooted_reproduction_stock).astype(int)
 last['memory_without_org']=((last.foothold_memory==1)&(last.org_survival==0)).astype(int)
 last['coercion_without_org']=((last.coercive_shell==1)&(last.org_survival==0)).astype(int)
 cell=last.groupby(['recruitment_mult','memory_mult','fielding_mult'],as_index=False).agg(
  p_renewing=('renewing_survival','mean'),p_org=('org_survival','mean'),p_rooted=('rooted_reproduction_stock','mean'),
  p_memory_without_org=('memory_without_org','mean'),p_coercion_without_org=('coercion_without_org','mean'),
  mean_active_footholds=('active_footholds','mean'),mean_armed=('total_armed_membership','mean'),mean_fielded=('total_fielded_personnel','mean'))
 transition=cell[(cell.p_renewing>0)&(cell.p_renewing<1)].copy()
 # Matched monotonicity on cell-level survival probability.
 mono={}
 for fac,direction in [('recruitment_mult','down'),('fielding_mult','down'),('memory_mult','up')]:
  other=[x for x in ['recruitment_mult','memory_mult','fielding_mult'] if x!=fac];checks=[]
  for _,g in cell.groupby(other):
   g=g.sort_values(fac); z=g.p_renewing.to_numpy(); diff=np.diff(z)
   checks.append(bool(np.all(diff<=1e-12)) if direction=='down' else bool(np.all(diff>=-1e-12)))
  mono[fac]={'expected_direction':direction,'matched_strata':len(checks),'monotone_fraction':float(np.mean(checks))}
 y=last.renewing_survival.to_numpy();groups=last.seed.to_numpy()
 Xrf=np.column_stack([np.log(last.recruitment_mult),np.log(last.fielding_mult)])
 Xall=np.column_stack([np.log(last.recruitment_mult),np.log(last.fielding_mult),np.log(last.memory_mult)])
 Xprod=np.log((last.recruitment_mult*last.fielding_mult).to_numpy())[:,None]
 auc_prod,brier_prod=oof(Xprod,y,groups);auc_rf,brier_rf=oof(Xrf,y,groups);auc_all,brier_all=oof(Xall,y,groups)
 marg={f:last.groupby(f).agg(p_renewing=('renewing_survival','mean'),p_memory_without_org=('memory_without_org','mean'),p_coercion_without_org=('coercion_without_org','mean'),armed=('total_armed_membership','mean'),fielded=('total_fielded_personnel','mean'),footholds=('active_footholds','mean')).reset_index().to_dict('records') for f in ['recruitment_mult','memory_mult','fielding_mult']}
 time=d.assign(org=(d.insurgent_org_active>.5).astype(int),rooted=(d.total_armed_membership>1e-9).astype(int),memory=(d.active_footholds>.5).astype(int),coercive=(d.total_fielded_personnel>75).astype(int)).groupby('time').agg(p_org=('org','mean'),p_rooted=('rooted','mean'),p_memory=('memory','mean'),p_coercive=('coercive','mean')).reset_index()
 out={'schema_version':'pineland.criticality_renewal_analysis.v2','status':'synthetic_proxy_reinterpreted_as_renewal_not_RI','historical_outcomes_used':False,'input':str(Path(a.csv)),'input_sha256':sha(a.csv),'trajectory_count':len(last),'seed_count':int(last.seed.nunique()),'cell_count':len(cell),
 'endpoint_separation':{'p_renewing_survival_180':float(last.renewing_survival.mean()),'p_memory_without_org_180':float(last.memory_without_org.mean()),'p_coercion_without_org_180':float(last.coercion_without_org.mean()),'org_and_rooted_identical_in_this_sweep':bool(np.array_equal(last.org_survival,last.rooted_reproduction_stock))},
 'transition_cell_count':len(transition),'transition_cells':transition.to_dict('records'),'matched_monotonicity':mono,
 'predictive':{'log_recruitment_x_fielding_oof_auc':auc_prod,'brier':brier_prod,'log_recruitment_and_fielding_oof_auc':auc_rf,'rf_brier':brier_rf,'plus_memory_oof_auc':auc_all,'plus_memory_brier':brier_all},
 'marginals':marg,'time_course':time.to_dict('records'),'cell_summaries':cell.to_dict('records'),
 'interpretation_guard':'A viable foothold after focal organization collapse is memory/persistence, not endogenous reproduction. Recoverable formations after collapse are residual coercive capacity under the model logistics semantics. Neither is R_I. Renewing survival requires a live organization with rooted membership; parent-attributed reproduction is estimated separately by the impulse kernel.'}
 Path(a.out).write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(a.out);print(out['endpoint_separation']);print('transition',len(transition));print('mono',mono);print('predictive',out['predictive'])
if __name__=='__main__':main()
