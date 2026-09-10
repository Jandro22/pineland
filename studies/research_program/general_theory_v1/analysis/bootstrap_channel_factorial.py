from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
FACTORS=['M','F','L','K','I']
OUTCOMES={'foothold_strength':'final_e_foothold_strength','viable':'viable','actions':'final_e_cum_actions','recruitment':'final_e_cum_recruits','fielded':'final_f_personnel','control':'final_c_ins_effective','control_margin':'control_margin','expectation':'final_x_expected_ins'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--out',required=True);ap.add_argument('--bootstrap',type=int,default=20000);a=ap.parse_args();d=pd.read_csv(a.csv);d['viable']=(d.final_e_foothold_strength>=.2).astype(float);d['control_margin']=d.final_c_ins_effective-d.final_c_gov_effective
 seeds=sorted(d.seed.unique());per={}
 for on,col in OUTCOMES.items():
  per[on]={}
  for f in FACTORS:
   vals=[]
   for seed,g in d.groupby('seed'):vals.append(float(g[g[f]==1][col].mean()-g[g[f]==0][col].mean()))
   per[on][f]=vals
  for ia,x in enumerate(FACTORS):
   for y in FACTORS[ia+1:]:
    vals=[]
    for seed,g in d.groupby('seed'):
     m=g.groupby([x,y])[col].mean();vals.append(float((m.loc[(1,1)]-m.loc[(0,1)])-(m.loc[(1,0)]-m.loc[(0,0)])))
    per[on][f'{x}x{y}']=vals
 rng=np.random.default_rng(20260910);res={}
 for on,effects in per.items():
  res[on]={}
  for name,vals in effects.items():
   v=np.array(vals,float);idx=rng.integers(0,len(v),size=(a.bootstrap,len(v)));b=v[idx].mean(axis=1);lo,hi=np.quantile(b,[.025,.975])
   res[on][name]={'mean':float(v.mean()),'seed_sd':float(v.std(ddof=1)),'ci95_seed_bootstrap':[float(lo),float(hi)],'positive_seed_fraction':float(np.mean(v>0)),'negative_seed_fraction':float(np.mean(v<0)),'per_seed':[float(x) for x in v]}
 out={'schema_version':'pineland.matched_seed_factorial_uncertainty.v1','status':'synthetic_matched_seed_effects','historical_outcomes_used':False,'input_sha256':sha(a.csv),'seed_count':len(seeds),'bootstrap_replicates':a.bootstrap,'effects':res}
 Path(a.out).write_text(json.dumps(out,indent=2)+'\n');print(a.out)
 for on in OUTCOMES:
  print('\n',on)
  for name,x in sorted(res[on].items(),key=lambda z:abs(z[1]['mean']),reverse=True)[:10]:print(name,round(x['mean'],4),[round(q,4) for q in x['ci95_seed_bootstrap']],round(x['positive_seed_fraction'],2))
if __name__=='__main__':main()
