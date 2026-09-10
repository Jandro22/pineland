from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

ID={'seed','time','locality','focal'}
DIAGNOSTIC_HISTORY={'e_cum_arrivals','e_cum_recruits','e_cum_actions','e_viable_activations','total_contacts','total_organized_actions','total_recruitment','total_civilian_harm'}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def derive(df):
    d=df.copy()
    d['M']=d.m_member_depth
    d['F']=np.log1p(d.f_effective_strength.clip(lower=0))
    d['L']=d.l_supply_fraction
    d['K_local']=d[['k_belief_conf','k_presence_conf','k_formation_info']].mean(axis=1)
    d['E']=d.e_foothold_strength
    d['C']=d.c_margin
    d['X']=d.x_expected_ins-d.x_expected_gov
    d['S_state']=d[['c_gov_effective','s_admin_capacity','s_institution_capacity','s_government_governance']].mean(axis=1)
    d['U_ext']=d.u_external_support+d.u_external_sanctuary+np.log1p(d.u_foreign_capacity.clip(lower=0))
    return d

def add_future(df,h):
    keys=['seed','locality']
    future=df.copy(); future['time']=future['time']-h
    cols=keys+['time','e_foothold_strength','e_cum_actions','e_cum_recruits','c_margin','f_personnel','c_gov_effective','e_viable_activations']
    future=future[cols].rename(columns={c:'future_'+c for c in cols if c not in keys+['time']})
    z=df.merge(future,on=keys+['time'],how='inner')
    z[f'viable_{int(h)}']=(z.future_e_foothold_strength>=0.20).astype(int)
    z[f'actions_delta_{int(h)}']=z.future_e_cum_actions-z.e_cum_actions
    z[f'recruits_delta_{int(h)}']=z.future_e_cum_recruits-z.e_cum_recruits
    z[f'control_delta_{int(h)}']=z.future_c_margin-z.c_margin
    z[f'fielded_{int(h)}']=z.future_f_personnel
    z[f'state_control_{int(h)}']=z.future_c_gov_effective
    z[f'viable_activation_delta_{int(h)}']=z.future_e_viable_activations-z.e_viable_activations
    return z

def oof_predict(X,y,groups,binary):
    uniq=np.unique(groups); pred=np.zeros(len(y),float)
    if len(uniq)<2:
        if binary: pred[:]=np.clip(np.mean(y),1e-6,1-1e-6)
        else: pred[:]=np.mean(y)
        return pred,'insufficient_seed_groups'
    n=min(4,len(uniq)); splitter=GroupKFold(n_splits=n)
    for tr,te in splitter.split(X,y,groups):
        if binary:
            if len(np.unique(y[tr]))<2: pred[te]=np.mean(y[tr]); continue
            m=HistGradientBoostingClassifier(max_iter=160,max_depth=5,learning_rate=.06,l2_regularization=.5,random_state=20260910)
            m.fit(X[tr],y[tr]); pred[te]=m.predict_proba(X[te])[:,1]
        else:
            m=HistGradientBoostingRegressor(max_iter=180,max_depth=5,learning_rate=.06,l2_regularization=.5,random_state=20260910)
            m.fit(X[tr],y[tr]); pred[te]=m.predict(X[te])
    return pred,'grouped_seed_cv'

def score(df,features,target,binary):
    X=df[features].replace([np.inf,-np.inf],0).fillna(0).to_numpy(float); y=df[target].to_numpy(); groups=df.seed.to_numpy()
    pred,mode=oof_predict(X,y,groups,binary)
    if binary:
        pred=np.clip(pred,1e-6,1-1e-6); base=np.full(len(y),np.mean(y)); base=np.clip(base,1e-6,1-1e-6)
        auc=float(roc_auc_score(y,pred)) if len(np.unique(y))>1 else None
        return {'cv_mode':mode,'n':len(y),'prevalence':float(np.mean(y)),'logloss':float(log_loss(y,pred,labels=[0,1])),'brier':float(brier_score_loss(y,pred)),'auc':auc,'baseline_logloss':float(log_loss(y,base,labels=[0,1])),'baseline_brier':float(brier_score_loss(y,base))}
    rmse=float(mean_squared_error(y,pred)**.5); sd=float(np.std(y)); base=np.full(len(y),np.mean(y))
    return {'cv_mode':mode,'n':len(y),'mean':float(np.mean(y)),'sd':sd,'rmse':rmse,'nrmse':rmse/(sd if sd>1e-12 else 1.0),'r2':float(r2_score(y,pred)) if sd>1e-12 else None,'baseline_rmse':float(mean_squared_error(y,base)**.5)}

def adversarial(df,macro,expanded):
    if df.seed.nunique()<2 or len(df)<20: return {'status':'insufficient_seed_groups_or_rows'}
    pairs=[]
    for t,g in df.groupby('time'):
        if g.seed.nunique()<2 or len(g)<10: continue
        xm=StandardScaler().fit_transform(g[macro].fillna(0)); xe=StandardScaler().fit_transform(g[expanded].fillna(0))
        nn=NearestNeighbors(n_neighbors=min(12,len(g))).fit(xm); dist,idx=nn.kneighbors(xm)
        seeds=g.seed.to_numpy(); rows=g.index.to_numpy()
        for a in range(len(g)):
            b=None; md=None
            for dd,j in zip(dist[a,1:],idx[a,1:]):
                if seeds[j]!=seeds[a]: b=j; md=float(dd); break
            if b is None: continue
            ed=float(np.linalg.norm(xe[a]-xe[b])); ra,rb=rows[a],rows[b]
            pairs.append({'macro_distance':md,'expanded_distance':ed,'viability_diff':int(df.loc[ra,'viable_90']!=df.loc[rb,'viable_90']),'control_delta_absdiff':abs(float(df.loc[ra,'control_delta_90']-df.loc[rb,'control_delta_90'])),'row_a':int(ra),'row_b':int(rb)})
    if not pairs:return {'status':'no_cross_seed_pairs'}
    mdq=float(np.quantile([x['macro_distance'] for x in pairs],.20)); edq=float(np.quantile([x['expanded_distance'] for x in pairs],.75))
    sel=[x for x in pairs if x['macro_distance']<=mdq and x['expanded_distance']>=edq]
    csd=float(np.std(df.control_delta_90)); thresh=(0.5*csd if csd>1e-12 else 1e-9)
    details=[]
    candidate_omitted=[c for c in expanded if c not in macro]
    for x in sel:
        arow=df.loc[x['row_a']]; brow=df.loc[x['row_b']]
        diffs=[]
        for c in candidate_omitted:
            av=float(arow[c]) if pd.notna(arow[c]) else 0.0; bv=float(brow[c]) if pd.notna(brow[c]) else 0.0
            sd=float(df[c].std(ddof=0)); z=abs(av-bv)/(sd if sd>1e-12 else 1.0)
            diffs.append((z,c,av,bv))
        diffs.sort(reverse=True)
        details.append({**x,'large_outcome_difference':bool(x['viability_diff']>0 or x['control_delta_absdiff']>thresh),
          'a':{'seed':int(arow.seed),'time':float(arow.time),'locality':int(arow.locality),'viable_90':int(arow.viable_90),'control_delta_90':float(arow.control_delta_90)},
          'b':{'seed':int(brow.seed),'time':float(brow.time),'locality':int(brow.locality),'viable_90':int(brow.viable_90),'control_delta_90':float(brow.control_delta_90)},
          'top_omitted_differences':[{'feature':c,'standardized_absdiff':float(z),'a':av,'b':bv} for z,c,av,bv in diffs[:12]]})
    return {'status':'ok','candidate_pairs':len(pairs),'selected_adversarial_pairs':len(sel),'macro_distance_p20':mdq,'expanded_distance_p75':edq,'large_outcome_difference_rate':float(np.mean([x['large_outcome_difference'] for x in details])) if details else None,'pairs':details}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--out',required=True); ns=ap.parse_args()
    raw=pd.read_csv(ns.csv); raw=derive(raw)
    feature_sets={
      'minimal_4':['M','F','E','C'],
      'operational_7':['M','F','L','K_local','E','C','X'],
      'competitive_9':['M','F','L','K_local','E','C','X','S_state','U_ext']
    }
    expanded=[c for c in raw.columns if c not in ID|DIAGNOSTIC_HISTORY and c not in {'M','F','L','K_local','E','C','X','S_state','U_ext'} and pd.api.types.is_numeric_dtype(raw[c])]
    # Add reduced variables too: expanded is a superset rather than a competitor deprived of them.
    expanded=feature_sets['competitive_9']+expanded
    expanded=list(dict.fromkeys(expanded)); feature_sets['expanded_state']=expanded
    results={}; allpasses=[]
    merged90=None
    for h in [30.0,90.0]:
        d=add_future(raw,h); results[str(int(h))]={}
        if h==90: merged90=d
        targets=[(f'viable_{int(h)}',True),(f'actions_delta_{int(h)}',False),(f'recruits_delta_{int(h)}',False),(f'control_delta_{int(h)}',False),(f'fielded_{int(h)}',False),(f'state_control_{int(h)}',False),(f'viable_activation_delta_{int(h)}',False)]
        for target,binary in targets:
            scores={name:score(d,fs,target,binary) for name,fs in feature_sets.items()}
            exp=scores['expanded_state']; comp=scores['competitive_9']
            if binary:
                regret=comp['logloss']-exp['logloss']; passed=(regret<=0.05 and regret<=max(0.05,0.10*max(exp['logloss'],1e-9)))
                comparison={'metric':'logloss','competitive_minus_expanded':regret,'passed_provisional_gate':bool(passed)}
            else:
                regret=comp['nrmse']-exp['nrmse']; passed=regret<=0.10
                comparison={'metric':'nrmse','competitive_minus_expanded':regret,'passed_provisional_gate':bool(passed)}
            allpasses.append(bool(passed)); results[str(int(h))][target]={'scores':scores,'competitive_vs_expanded':comparison}
    adv=adversarial(merged90,feature_sets['competitive_9'],expanded) if merged90 is not None else {'status':'no_90d_rows'}
    if adv.get('large_outcome_difference_rate') is not None: allpasses.append(adv['large_outcome_difference_rate']<=0.10)
    out={'schema_version':'pineland.macrostate_closure_analysis.v1','status':'synthetic_reduction_test_not_historical_result','historical_outcomes_used':False,'input':str(Path(ns.csv)),'input_sha256':sha(ns.csv),'seed_count':int(raw.seed.nunique()),'row_count':len(raw),'feature_sets':feature_sets,'results':results,'adversarial_pairs':adv,'provisional_gate_passed':bool(all(allpasses)) if allpasses else False,'warning':'Expanded-state predictor is a practical high-dimensional snapshot reference, not the literal full ParticleState. Passing is evidence for approximate closure only.'}
    Path(ns.out).write_text(json.dumps(out,indent=2)+"\n",encoding='utf-8'); print(ns.out); print('provisional_gate_passed',out['provisional_gate_passed'])
if __name__=='__main__': main()
