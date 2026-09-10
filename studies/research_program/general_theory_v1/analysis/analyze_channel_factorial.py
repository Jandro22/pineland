from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import LeaveOneGroupOut

FACTORS=['M','F','L','K','I']
OUTCOMES={
 'foothold_strength':'final_e_foothold_strength',
 'foothold_viable':'_derived_viable',
 'actions':'final_e_cum_actions',
 'recruitment':'final_e_cum_recruits',
 'fielded_personnel':'final_f_personnel',
 'insurgent_control':'final_c_ins_effective',
 'control_margin':'_derived_control_margin',
 'expected_insurgent':'final_x_expected_ins'
}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mean_effect(df,factor,outcome): return float(df[df[factor]==1][outcome].mean()-df[df[factor]==0][outcome].mean())
def interaction(df,a,b,outcome):
    m=df.groupby([a,b])[outcome].mean()
    return float((m.loc[(1,1)]-m.loc[(0,1)])-(m.loc[(1,0)]-m.loc[(0,0)]))

def architecture_scores(df,outcome):
    z=df[FACTORS].astype(float).to_numpy()
    arch={
      'OR':1-np.prod(1-z,axis=1),
      'MAX':z.max(axis=1),
      'ADD':z.mean(axis=1),
      'PRODUCT':np.prod(z,axis=1),
      'MIN':z.min(axis=1),
      'THRESHOLD_3OF5':(z.sum(axis=1)>=3).astype(float)
    }
    y=df[outcome].to_numpy(float); groups=df['seed'].to_numpy()
    logo=LeaveOneGroupOut(); result={}
    for name,x in arch.items():
        pred=np.zeros_like(y,dtype=float); ok=np.zeros(len(y),bool)
        splits=list(logo.split(x,y,groups)) if len(np.unique(groups))>=2 else [(np.arange(len(y)),np.arange(len(y)))]
        for tr,te in splits:
            if len(np.unique(x[tr]))<2:
                pred[te]=np.mean(y[tr]); ok[te]=True; continue
            iso=IsotonicRegression(out_of_bounds='clip').fit(x[tr],y[tr])
            pred[te]=iso.predict(x[te]); ok[te]=True
        rmse=float(mean_squared_error(y[ok],pred[ok])**0.5)
        scale=float(np.std(y))
        result[name]={'rmse':rmse,'nrmse':rmse/(scale if scale>1e-12 else 1.0)}
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--out',required=True); ap.add_argument('--viability-threshold',type=float,default=0.20); ns=ap.parse_args()
    df=pd.read_csv(ns.csv)
    df['_derived_viable']=(df.final_e_foothold_strength>=ns.viability_threshold).astype(float)
    df['_derived_control_margin']=df.final_c_ins_effective-df.final_c_gov_effective
    cells=df.groupby('seed').cell.nunique()
    integrity={'seed_count':int(df.seed.nunique()),'rows':int(len(df)),'all_32_cells_per_seed':bool((cells==32).all()),'cells_per_seed':{str(k):int(v) for k,v in cells.items()},'no_missing_factor_cells':bool(len(df)==df.seed.nunique()*32)}
    results={}
    for oname,col in OUTCOMES.items():
        mainfx={f:mean_effect(df,f,col) for f in FACTORS}
        interactions={f'{a}x{b}':interaction(df,a,b,col) for ia,a in enumerate(FACTORS) for b in FACTORS[ia+1:]}
        zero=df[(df[FACTORS].sum(axis=1)==0)].groupby('seed')[col].mean()
        single={f:float(df[(df[f]==1)&(df[[x for x in FACTORS if x!=f]].sum(axis=1)==0)].groupby('seed')[col].mean().mean()-zero.mean()) for f in FACTORS}
        high=df[(df[FACTORS].sum(axis=1)==5)].groupby('seed')[col].mean()
        knockout={f:float(high.mean()-df[(df[f]==0)&(df[[x for x in FACTORS if x!=f]].sum(axis=1)==4)].groupby('seed')[col].mean().mean()) for f in FACTORS}
        results[oname]={'column':col,'main_effects':mainfx,'pairwise_interactions':interactions,'single_channel_rescue_over_all_low':single,'loss_when_knocked_out_from_all_high':knockout,'architecture_recovery':architecture_scores(df,col)}
    surv=results['foothold_viable']
    rescue=[f for f,v in surv['single_channel_rescue_over_all_low'].items() if v>=0.25]
    knockout=[f for f,v in surv['loss_when_knocked_out_from_all_high'].items() if v>=0.25]
    arch=surv['architecture_recovery']; ranked=sorted(arch,key=lambda k:arch[k]['nrmse'])
    interpretation={
      'substitution_signature':bool(rescue),'single_channels_with_large_survival_rescue':rescue,
      'strict_complementarity_signature':bool(knockout),'single_knockouts_with_large_survival_loss':knockout,
      'best_architecture_by_leave_one_seed_out_isotonic_nrmse':ranked,
      'warning':'This recovers structural behavior of the implemented synthetic model. It does not independently establish which architecture is historically true.'
    }
    out={'schema_version':'pineland.channel_factorial_analysis.v1','status':'synthetic_mechanism_discrimination_not_historical_result','historical_outcomes_used':False,'input':str(Path(ns.csv)),'input_sha256':sha(ns.csv),'integrity':integrity,'viability_threshold':ns.viability_threshold,'results':results,'interpretation':interpretation}
    Path(ns.out).write_text(json.dumps(out,indent=2)+"\n",encoding='utf-8'); print(ns.out); print(json.dumps(interpretation,indent=2))
if __name__=='__main__': main()

