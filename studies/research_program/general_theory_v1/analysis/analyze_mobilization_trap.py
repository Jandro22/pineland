from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.model_selection import LeaveOneGroupOut

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def grouped_oof_auc(X,y,groups):
    if len(np.unique(groups)) < 2:
        return None,None,None
    pred=np.zeros(len(y),float)
    logo=LeaveOneGroupOut()
    for tr,te in logo.split(X,y,groups):
        if len(np.unique(y[tr]))<2:
            pred[te]=float(np.mean(y[tr]))
        else:
            m=LogisticRegression(max_iter=2000).fit(X[tr],y[tr])
            pred[te]=m.predict_proba(X[te])[:,1]
    auc=float(roc_auc_score(y,pred)) if len(np.unique(y))>1 else None
    return auc,float(brier_score_loss(y,pred)),pred

def main():
    ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--out',required=True);a=ap.parse_args()
    d=pd.read_csv(a.csv).sort_values(['seed','recruitment_mult','fielding_mult','capital_mult','time'])
    keys=['seed','recruitment_mult','fielding_mult','capital_mult']
    rows=[]
    for key,g in d.groupby(keys,sort=False):
        g=g.sort_values('time').reset_index(drop=True)
        first=g.iloc[0]; last=g.iloc[-1]
        inactive=g[g.org_active<=.5]
        if len(inactive):
            idx=int(inactive.index[0]); collapse=float(g.loc[idx,'time']); first_inactive_cap=float(g.loc[idx,'capital'])
            prev=g.loc[max(idx-1,0)]; last_active_cap=float(prev.capital); last_active_cohesion=float(prev.cohesion)
        else:
            collapse=None;first_inactive_cap=None;last_active_cap=float(last.capital);last_active_cohesion=float(last.cohesion)
        rows.append(dict(zip(keys,key))|{
            'strain_proxy':float(first.strain_proxy),
            'base_capital':float(first.base_capital),
            'initial_capital':float(first.capital),
            'survives_180':int(last.org_active>.5),
            'collapse_time_upper_days':collapse,
            'last_active_capital':last_active_cap,
            'first_inactive_capital':first_inactive_cap,
            'last_active_cohesion':last_active_cohesion,
            'hard_capital_depletion':int(first_inactive_cap is not None and first_inactive_cap<=1e-9),
            'final_capital':float(last.capital),'final_armed':float(last.armed_membership),'final_fielded':float(last.fielded_personnel),
            'final_footholds':float(last.active_footholds),'final_fiscal':float(last.mean_insurgent_fiscal_control),
            'recruitment':float(last.cumulative_recruitment-first.cumulative_recruitment)
        })
    r=pd.DataFrame(rows)
    y=r.survives_180.to_numpy(int); groups=r.seed.to_numpy()
    strain=np.log(r.strain_proxy.clip(lower=1e-12)).to_numpy()[:,None]
    full=np.column_stack([np.log(r.recruitment_mult),np.log(r.fielding_mult),np.log(r.capital_mult)])
    auc_s,brier_s,pred_s=grouped_oof_auc(strain,y,groups)
    auc_f,brier_f,pred_f=grouped_oof_auc(full,y,groups)
    # Matched deterministic monotonicity at the trajectory level.
    checks={}
    for factor,direction in [('capital_mult','up'),('recruitment_mult','down'),('fielding_mult','down')]:
        other=[x for x in ['seed','recruitment_mult','fielding_mult','capital_mult'] if x!=factor]
        vals=[]
        for _,g in r.groupby(other):
            g=g.sort_values(factor); z=g.survives_180.to_numpy(float); diff=np.diff(z)
            vals.append(bool(np.all(diff>=0)) if direction=='up' else bool(np.all(diff<=0)))
        checks[factor]={'expected_direction':direction,'matched_strata':len(vals),'monotone_fraction':float(np.mean(vals))}
    cell=r.groupby(['recruitment_mult','fielding_mult','capital_mult'],as_index=False).agg(
        p_survival=('survives_180','mean'),mean_collapse=('collapse_time_upper_days','mean'),hard_depletion_fraction=('hard_capital_depletion','mean'),
        mean_final_capital=('final_capital','mean'),mean_final_armed=('final_armed','mean'),mean_final_fielded=('final_fielded','mean'),mean_final_footholds=('final_footholds','mean'),mean_recruitment=('recruitment','mean'))
    cell['strain_proxy']=cell.recruitment_mult*cell.fielding_mult/cell.capital_mult
    transition=cell[(cell.p_survival>0)&(cell.p_survival<1)].sort_values('strain_proxy')
    collapsed=r[r.survives_180==0]
    hard=float(collapsed.hard_capital_depletion.mean()) if len(collapsed) else None
    # Bin by strain to see whether disparate parameter combinations collapse onto one curve.
    unique=sorted(r.strain_proxy.unique())
    strain_curve=[]
    same_strain_decomposition=[]
    for v,g in r.groupby('strain_proxy'):
        decomposition=(g.groupby(['recruitment_mult','fielding_mult','capital_mult'])
                         .survives_180.mean().reset_index(name='p_survival'))
        dispersion=float(decomposition.p_survival.max()-decomposition.p_survival.min()) if len(decomposition) else 0.0
        strain_curve.append({'strain_proxy':float(v),'n':len(g),'p_survival':float(g.survives_180.mean()),'mean_collapse_time':float(g.collapse_time_upper_days.mean()) if g.collapse_time_upper_days.notna().any() else None,'decomposition_count':int(len(decomposition)),'within_strain_survival_range':dispersion})
        same_strain_decomposition.append({'strain_proxy':float(v),'decomposition_count':int(len(decomposition)),'survival_range':dispersion,'decompositions':decomposition.to_dict('records')})
    out={
      'schema_version':'pineland.mobilization_trap_analysis.v1','status':'synthetic_mechanism_test_not_historical_result','historical_outcomes_used':False,
      'input':str(Path(a.csv)),'input_sha256':sha(a.csv),'integrity':{'rows':len(d),'trajectory_count':len(r),'seed_count':int(r.seed.nunique()),'cell_count':int(cell.shape[0])},
      'overall':{'p_survival_180':float(r.survives_180.mean()),'collapsed_trajectories':int((1-r.survives_180).sum()),'hard_capital_depletion_fraction_among_collapses':hard},
      'predictive':{'strain_log_oof_auc':auc_s,'strain_oof_brier':brier_s,'full_log_r_f_c_oof_auc':auc_f,'full_oof_brier':brier_f},
      'matched_monotonicity':checks,'transition_cell_count':len(transition),'transition_cells':transition.to_dict('records'),
      'strain_curve':sorted(strain_curve,key=lambda x:x['strain_proxy']),'same_strain_decomposition':same_strain_decomposition,'cell_summaries':cell.sort_values(['strain_proxy','recruitment_mult','fielding_mult','capital_mult']).to_dict('records'),
      'interpretation_guard':'Association with r*f/c is evidence about the implemented synthetic mechanism only. A useful general-theory strain variable requires robustness to resource-flow definitions, actor phenotype, geography, and independent empirical confrontation.'
    }
    Path(a.out).write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(a.out);print('overall',out['overall']);print('predictive',out['predictive']);print('monotonicity',checks);print('transition cells',len(transition))
    print(transition[['recruitment_mult','fielding_mult','capital_mult','strain_proxy','p_survival','hard_depletion_fraction']].to_string(index=False) if len(transition) else 'no transitions')
if __name__=='__main__':main()
