from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import log_loss,brier_score_loss,roc_auc_score,mean_squared_error,r2_score
from sklearn.model_selection import GroupKFold

ID={'seed','time','locality','focal'}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def derive(d):
    d=d.copy()
    d['M']=d.m_member_depth
    d['F']=np.log1p(d.f_effective_strength.clip(lower=0))
    d['L']=d.l_supply_fraction
    d['K_local']=d[['k_belief_conf','k_presence_conf','k_formation_info']].mean(axis=1)
    d['E']=d.e_foothold_strength
    d['C']=d.c_margin
    d['X']=d.x_expected_ins-d.x_expected_gov
    d['S_state']=d[['c_gov_effective','s_admin_capacity','s_institution_capacity','s_government_governance']].mean(axis=1)
    d['U_ext']=d.u_external_support+d.u_external_sanctuary+np.log1p(d.u_foreign_capacity.clip(lower=0))
    d['z_log_population']=np.log1p(d.population.clip(lower=0))
    d['z_log_econ_pc']=np.log1p((d.economic_output/d.population.clip(lower=1))*1000.0)
    d['s_security_per_1000']=d.s_security_personnel/d.population.clip(lower=1)*1000.0
    return d

def add_future(df,h):
    keys=['seed','locality']; fut=df.copy(); fut['time']=fut['time']-h
    cols=keys+['time','e_foothold_strength','e_cum_actions','e_cum_recruits','c_margin','f_personnel','c_gov_effective','e_viable_activations']
    fut=fut[cols].rename(columns={c:'future_'+c for c in cols if c not in keys+['time']})
    z=df.merge(fut,on=keys+['time'],how='inner')
    z[f'viable_{int(h)}']=(z.future_e_foothold_strength>=.20).astype(int)
    z[f'actions_delta_{int(h)}']=z.future_e_cum_actions-z.e_cum_actions
    z[f'recruits_delta_{int(h)}']=z.future_e_cum_recruits-z.e_cum_recruits
    z[f'control_delta_{int(h)}']=z.future_c_margin-z.c_margin
    z[f'fielded_{int(h)}']=z.future_f_personnel
    z[f'state_control_{int(h)}']=z.future_c_gov_effective
    z[f'activation_delta_{int(h)}']=z.future_e_viable_activations-z.e_viable_activations
    return z

def score(df,features,target,binary):
    X=df[features].replace([np.inf,-np.inf],0).fillna(0).to_numpy(float); y=df[target].to_numpy(); groups=df.seed.to_numpy()
    n=min(4,len(np.unique(groups))); splitter=GroupKFold(n_splits=n); pred=np.zeros(len(y))
    for tr,te in splitter.split(X,y,groups):
        if binary:
            if len(np.unique(y[tr]))<2: pred[te]=np.mean(y[tr]); continue
            m=HistGradientBoostingClassifier(max_iter=160,max_depth=5,learning_rate=.06,l2_regularization=.5,random_state=20260910)
            m.fit(X[tr],y[tr]); pred[te]=m.predict_proba(X[te])[:,1]
        else:
            m=HistGradientBoostingRegressor(max_iter=180,max_depth=5,learning_rate=.06,l2_regularization=.5,random_state=20260910)
            m.fit(X[tr],y[tr]); pred[te]=m.predict(X[te])
    if binary:
        pred=np.clip(pred,1e-6,1-1e-6); base=np.clip(np.full(len(y),np.mean(y)),1e-6,1-1e-6)
        return {'n':len(y),'prevalence':float(np.mean(y)),'logloss':float(log_loss(y,pred,labels=[0,1])),'brier':float(brier_score_loss(y,pred)),'auc':float(roc_auc_score(y,pred)) if len(np.unique(y))>1 else None,'baseline_logloss':float(log_loss(y,base,labels=[0,1]))}
    rmse=float(mean_squared_error(y,pred)**.5); sd=float(np.std(y)); base=float(mean_squared_error(y,np.full(len(y),np.mean(y)))**.5)
    return {'n':len(y),'sd':sd,'rmse':rmse,'nrmse':rmse/(sd if sd>1e-12 else 1.0),'r2':float(r2_score(y,pred)) if sd>1e-12 else None,'baseline_rmse':base}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--out',required=True); ns=ap.parse_args()
    d=derive(pd.read_csv(ns.csv))
    scalar9=['M','F','L','K_local','E','C','X','S_state','U_ext']
    local_vector=[
      'm_member_depth','m_rooted_local_share','m_rooted_district_share','m_social_exposure','m_armed_mass',
      'f_personnel','f_effective_strength','f_mean_readiness','f_mean_embeddedness','formation_quality','formation_command','formation_fatigue','formation_availability',
      'l_supply_stock','l_supply_fraction','k_belief_conf','k_presence_conf','k_formation_info','k_tradecraft','e_foothold_strength','e_renewal_count',
      'c_ins_effective','c_gov_effective',
      'c_ins_formal','c_ins_physical','c_ins_admin','c_ins_legal','c_ins_fiscal','c_ins_social','c_ins_expected',
      'c_gov_formal','c_gov_physical','c_gov_admin','c_gov_legal','c_gov_fiscal','c_gov_social','c_gov_expected',
      'x_expected_gov','x_expected_ins','x_grievance','x_fear','x_political_access','x_state_legitimacy','x_government_legitimacy','x_trust_insurgent','x_insurgent_behavior_share',
      's_admin_capacity','s_security_per_1000','s_institution_capacity','s_institution_reach','s_government_governance',
      'u_external_support','u_external_sanctuary','u_foreign_capacity']
    Z=['z_log_population','z_log_econ_pc','infrastructure','terrain_friction','observability','network_mean_degree','displaced_share']
    theta=['org_cohesion','org_discipline','org_persistence','org_mobility','org_institutional_quality','org_capital_social','org_capital_political','org_capital_organizational','org_capital_material','org_risk_tolerance','org_governance_investment']
    feature_sets={
      'scalar9':scalar9,
      'scalar9_plus_Z':scalar9+Z,
      'structured_X':local_vector,
      'structured_X_plus_Z':local_vector+Z,
      'structured_X_plus_Z_Theta':local_vector+Z+theta,
    }
    # Expanded reference: every numeric contemporaneous state feature except IDs and cumulative outcome-history diagnostics.
    exclude=ID|{'e_cum_arrivals','e_cum_recruits','e_cum_actions','e_viable_activations','total_contacts','total_organized_actions','total_recruitment','total_civilian_harm'}
    derived=set(['M','F','L','K_local','E','C','X','S_state','U_ext','z_log_population','z_log_econ_pc','s_security_per_1000'])
    expanded=[c for c in d.columns if c not in exclude and c not in derived and pd.api.types.is_numeric_dtype(d[c])]
    expanded=list(dict.fromkeys(local_vector+Z+theta+expanded)); feature_sets['expanded_snapshot']=expanded
    results={}; gates=[]
    for h in (30.0,90.0):
        z=add_future(d,h); hr={}
        targets=[(f'viable_{int(h)}',True),(f'actions_delta_{int(h)}',False),(f'recruits_delta_{int(h)}',False),(f'control_delta_{int(h)}',False),(f'fielded_{int(h)}',False),(f'state_control_{int(h)}',False),(f'activation_delta_{int(h)}',False)]
        for target,binary in targets:
            sc={name:score(z,fs,target,binary) for name,fs in feature_sets.items()}
            ref=sc['expanded_snapshot']; candidate=sc['structured_X_plus_Z_Theta']
            if binary:
                regret=candidate['logloss']-ref['logloss']; passed=regret<=.05
                comp={'metric':'logloss','regret':regret,'passed':bool(passed)}
            else:
                regret=candidate['nrmse']-ref['nrmse']; passed=regret<=.10
                comp={'metric':'nrmse','regret':regret,'passed':bool(passed)}
            gates.append(bool(passed)); hr[target]={'scores':sc,'structured_vs_expanded':comp}
        results[str(int(h))]=hr
    out={'schema_version':'pineland.structured_closure_analysis.v1','status':'synthetic_grouped_seed_predictive_compression','historical_outcomes_used':False,'input_sha256':sha(ns.csv),'seed_count':int(d.seed.nunique()),'rows':len(d),'feature_sets':feature_sets,'results':results,'all_predictive_regret_gates_passed':bool(all(gates)),'interpretation_guard':'Predictive compression is necessary but not sufficient for Markov closure. Distributional matched-state continuation remains required.'}
    Path(ns.out).write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8'); print(ns.out); print('all gates',out['all_predictive_regret_gates_passed'])
    for h,r in results.items():
      print('H',h)
      for t,v in r.items():
        a=v['scores']['scalar9']; b=v['scores']['structured_X_plus_Z_Theta']; e=v['scores']['expanded_snapshot']
        m='logloss' if 'logloss' in e else 'nrmse'
        print(t,m,round(a[m],4),round(b[m],4),round(e[m],4),'regret',round(v['structured_vs_expanded']['regret'],4))
if __name__=='__main__': main()
