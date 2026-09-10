from __future__ import annotations
import argparse,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier,HistGradientBoostingRegressor
from sklearn.metrics import log_loss,mean_squared_error
from sklearn.model_selection import GroupKFold

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def derive(d):
 d=d.copy();d['z_log_population']=np.log1p(d.population.clip(lower=0));d['z_log_econ_pc']=np.log1p((d.economic_output/d.population.clip(lower=1))*1000);d['s_security_per_1000']=d.s_security_personnel/d.population.clip(lower=1)*1000;return d
BLOCKS={
'M':['m_member_depth','m_rooted_local_share','m_rooted_district_share','m_social_exposure','m_armed_mass'],
'F':['f_personnel','f_effective_strength','f_mean_readiness','f_mean_embeddedness','formation_quality','formation_command','formation_fatigue','formation_availability'],
'L':['l_supply_stock','l_supply_fraction'],
'K':['k_belief_conf','k_presence_conf','k_formation_info','k_tradecraft'],
'E':['e_foothold_strength','e_renewal_count'],
'C':['c_ins_effective','c_gov_effective','c_ins_formal','c_ins_physical','c_ins_admin','c_ins_legal','c_ins_fiscal','c_ins_social','c_ins_expected','c_gov_formal','c_gov_physical','c_gov_admin','c_gov_legal','c_gov_fiscal','c_gov_social','c_gov_expected'],
'X':['x_expected_gov','x_expected_ins','x_grievance','x_fear','x_political_access','x_state_legitimacy','x_government_legitimacy','x_trust_insurgent','x_insurgent_behavior_share'],
'S':['s_admin_capacity','s_security_per_1000','s_institution_capacity','s_institution_reach','s_government_governance'],
'U':['u_external_support','u_external_sanctuary','u_foreign_capacity'],
'Z':['z_log_population','z_log_econ_pc','infrastructure','terrain_friction','observability','network_mean_degree','displaced_share'],
'THETA':['org_cohesion','org_discipline','org_persistence','org_mobility','org_institutional_quality','org_capital_social','org_capital_political','org_capital_organizational','org_capital_material','org_risk_tolerance','org_governance_investment']}
def future(d,h):
 f=d.copy();f['time']=f.time-h;cols=['seed','locality','time','e_foothold_strength','e_cum_actions','e_cum_recruits','c_margin','f_personnel','c_gov_effective'];f=f[cols].rename(columns={c:'future_'+c for c in cols if c not in ['seed','locality','time']});z=d.merge(f,on=['seed','locality','time']);z[f'viable_{h}']=(z.future_e_foothold_strength>=.2).astype(int);z[f'actions_{h}']=z.future_e_cum_actions-z.e_cum_actions;z[f'recruits_{h}']=z.future_e_cum_recruits-z.e_cum_recruits;z[f'control_{h}']=z.future_c_margin-z.c_margin;z[f'fielded_{h}']=z.future_f_personnel;z[f'state_{h}']=z.future_c_gov_effective;return z
def score(d,fs,t,binary):
 X=d[fs].replace([np.inf,-np.inf],0).fillna(0).to_numpy();y=d[t].to_numpy();g=d.seed.to_numpy();pred=np.zeros(len(y));cv=GroupKFold(n_splits=min(4,len(np.unique(g))))
 for tr,te in cv.split(X,y,g):
  if binary:
   if len(np.unique(y[tr]))<2:pred[te]=y[tr].mean();continue
   m=HistGradientBoostingClassifier(max_iter=120,max_depth=5,learning_rate=.07,l2_regularization=.5,random_state=20260910);m.fit(X[tr],y[tr]);pred[te]=m.predict_proba(X[te])[:,1]
  else:
   m=HistGradientBoostingRegressor(max_iter=140,max_depth=5,learning_rate=.07,l2_regularization=.5,random_state=20260910);m.fit(X[tr],y[tr]);pred[te]=m.predict(X[te])
 if binary:return float(log_loss(y,np.clip(pred,1e-6,1-1e-6),labels=[0,1]))
 sd=np.std(y);return float(np.sqrt(mean_squared_error(y,pred))/(sd if sd>1e-12 else 1))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--out',required=True);a=ap.parse_args();d=derive(pd.read_csv(a.csv));full=sum(BLOCKS.values(),[]);out={'schema_version':'pineland.structured_block_ablation.v1','input_sha256':sha(a.csv),'historical_outcomes_used':False,'blocks':BLOCKS,'results':{}}
 for h in [30,90]:
  z=future(d,h);targets=[(f'viable_{h}',True),(f'actions_{h}',False),(f'recruits_{h}',False),(f'control_{h}',False),(f'fielded_{h}',False),(f'state_{h}',False)];base={t:score(z,full,t,b) for t,b in targets};r={'full':base,'drop':{}}
  for block,cols in BLOCKS.items():
   fs=[x for x in full if x not in cols];r['drop'][block]={}
   for t,b in targets:
    v=score(z,fs,t,b);r['drop'][block][t]={'score':v,'degradation':v-base[t]}
  out['results'][str(h)]=r
 Path(a.out).write_text(json.dumps(out,indent=2)+'\n');print(a.out)
 for h,r in out['results'].items():
  print('H',h)
  ranking=[]
  for b,x in r['drop'].items(): ranking.append((max(v['degradation'] for v in x.values()),b,sum(max(0,v['degradation']) for v in x.values())))
  for mx,b,sm in sorted(ranking,reverse=True):print(b,'max_deg',round(mx,4),'sum_pos',round(sm,4))
if __name__=='__main__':main()
