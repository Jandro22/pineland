from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd

TYPES=['E','M','F','G','MF','MG','FG','MFG']
CHILD_TYPES=['M','F','G','MF','MG','FG','MFG']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rho(A,iterations=100,tol=1e-12):
    n=A.shape[0]
    if n==0:return 0.0
    x=np.full(n,1.0/n)
    last=0.0
    for _ in range(iterations):
        y=A@x
        norm=float(np.linalg.norm(y,ord=1))
        if norm<=1e-15:return 0.0
        x=y/norm
        # Collatz-ish Rayleigh proxy; final eig computation below for stable small matrices.
        last=norm
    vals=np.linalg.eigvals(A)
    return float(np.max(np.abs(vals))) if len(vals) else 0.0

def build_matrix(d,seeds,parent_types=TYPES):
    locs=sorted(set(d.origin.unique())|set(d.destination.unique()))
    L=len(locs); li={x:i for i,x in enumerate(locs)}; ti={x:i for i,x in enumerate(TYPES)}
    n=L*len(TYPES); K=np.zeros((n,n),float); P0=np.zeros((L,L,len(TYPES)),float)
    sub=d[d.seed.isin(seeds)].copy()
    # Placebo probability by origin,destination,child signature; E children are structural zeros.
    pl=sub[(sub.parent_type=='none') & (sub.child==1)]
    den=max(len(set(seeds)),1)
    for (o,j,c),g in pl.groupby(['origin','destination','child_type']):
        if c in ti:P0[li[o],li[j],ti[c]]=g.seed.nunique()/den
    for pt in parent_types:
        if pt not in ti:continue
        x=sub[sub.parent_type==pt]
        for (o,j,c),g in x[x.child==1].groupby(['origin','destination','child_type']):
            if c not in ti:continue
            raw=g.seed.nunique()/den
            excess=max(0.0,raw-P0[li[o],li[j],ti[c]])
            K[li[o]*len(TYPES)+ti[pt], li[j]*len(TYPES)+ti[c]]=excess
    return K,locs

def case_table(d):
    # one row per seed/origin/parent; count each destination only once by construction
    return d.groupby(['seed','origin','parent_type'],as_index=False).agg(
        offspring=('child','sum'), adjacent_offspring=('adjacent_origin',lambda x:0))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('csv');ap.add_argument('--out',required=True);ap.add_argument('--bootstrap',type=int,default=1000);a=ap.parse_args()
    d=pd.read_csv(a.csv)
    seeds=sorted(d.seed.unique()); origins=sorted(d.origin.unique()); destinations=sorted(d.destination.unique())
    expected=len(seeds)*len(origins)*9*(len(origins)-1)
    integrity={'rows':len(d),'expected_rows':expected,'complete':len(d)==expected,'seed_count':len(seeds),'origin_count':len(origins),'parent_types':sorted(d.parent_type.unique())}
    cases=d.groupby(['seed','origin','parent_type'],as_index=False).child.sum().rename(columns={'child':'offspring'})
    summary={}
    for pt,g in cases.groupby('parent_type'):
        arr=g.offspring.to_numpy(float)
        summary[pt]={'n_parent_experiments':len(arr),'mean_offspring':float(arr.mean()),'sd_offspring':float(arr.std(ddof=1)) if len(arr)>1 else 0.0,'p_any_offspring':float(np.mean(arr>0)),'max_offspring':int(arr.max()),'total_offspring':int(arr.sum())}
    placebo=summary.get('none',{})
    # signatures/triggers/space
    hits=d[d.child==1].copy()
    sig={pt:{str(k):int(v) for k,v in g.child_type.value_counts().items()} for pt,g in hits.groupby('parent_type')}
    trig={pt:{str(k):int(v) for k,v in g.trigger_event.value_counts().items()} for pt,g in hits.groupby('parent_type')}
    spatial={}
    for pt,g in hits.groupby('parent_type'):
        spatial[pt]={'n':len(g),'adjacent_fraction':float(g.adjacent_origin.mean()),'median_distance_km':float(g.distance_km.median()),'mean_distance_km':float(g.distance_km.mean()),'median_first_time_days':float(g.first_time.median()),'p90_first_time_days':float(g.first_time.quantile(.9))}
    K,locs=build_matrix(d,seeds)
    rho_hat=rho(K)
    # Row sums by parent type, averaging origins: expected first-generation children over window.
    row_summary={}
    for pt in TYPES:
        idx=[i*len(TYPES)+TYPES.index(pt) for i in range(len(locs))]
        rs=K[idx,:].sum(axis=1)
        row_summary[pt]={'mean_excess_offspring':float(rs.mean()),'median_excess_offspring':float(np.median(rs)),'max_excess_offspring':float(rs.max())}
    # Destination child-type composition of K.
    child_mass={ct:float(K[:,[j*len(TYPES)+TYPES.index(ct) for j in range(len(locs))]].sum()) for ct in TYPES}
    # Bootstrap seeds, preserving all origin/type matched panels.
    rng=np.random.default_rng(20260910); boots=[]
    if len(seeds)>1 and a.bootstrap>0:
        for _ in range(a.bootstrap):
            sample=list(rng.choice(seeds,size=len(seeds),replace=True))
            # duplicated seeds need weights, so materialize bootstrap copies with synthetic bootstrap IDs.
            parts=[]
            for bi,s in enumerate(sample):
                z=d[d.seed==s].copy();z['seed']=bi;parts.append(z)
            bd=pd.concat(parts,ignore_index=True)
            B,_=build_matrix(bd,list(range(len(sample))))
            boots.append(rho(B))
    ci=[float(np.quantile(boots,.025)),float(np.quantile(boots,.975))] if boots else None
    out={
      'schema_version':'pineland.reproduction_impulse_analysis.v2',
      'status':'synthetic_finite_horizon_first_generation_kernel',
      'historical_outcomes_used':False,
      'input':str(Path(a.csv)),'input_sha256':sha(a.csv),'integrity':integrity,
      'parent_summary':summary,'placebo_passed':bool(placebo and placebo.get('total_offspring',1)==0),
      'child_signature_counts':sig,'trigger_counts':trig,'spatial':spatial,
      'kernel':{'type_order':TYPES,'locality_order':[int(x) for x in locs],'shape':list(K.shape),'rho_K90':rho_hat,'rho_seed_bootstrap_ci95':ci,'bootstrap_replicates':len(boots),'row_summary':row_summary,'child_mass':child_mass},
      'interpretation_guard':'K_90 is a finite-horizon, experimentally isolated first-generation kernel. Pure relocation/E-only viability is excluded and no-parent spontaneous ignition is subtracted. rho(K_90) is not yet promoted as a lifetime R_I; horizon convergence and replication under structural contexts are required.'
    }
    Path(a.out).write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    # Save matrix as compressed npz beside JSON for reproducibility.
    np.savez_compressed(str(Path(a.out).with_suffix('.npz')),K=K,types=np.array(TYPES),localities=np.array(locs))
    print(a.out);print('integrity',integrity);print('placebo',placebo);print('rho_K90',rho_hat,'ci',ci)
    print('row summaries')
    for k,v in row_summary.items():print(k,v)
    print('signatures',sig);print('triggers',trig)
if __name__=='__main__':main()
