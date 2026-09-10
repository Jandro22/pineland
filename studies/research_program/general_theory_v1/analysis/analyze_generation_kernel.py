from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

TYPES = ['E', 'M', 'F', 'G', 'MF', 'MG', 'FG', 'MFG']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def prune_and_spectral_radius(A):
    B = np.asarray(A, float)
    while B.shape[0]:
        keep = (B.sum(axis=0) > 1e-15) & (B.sum(axis=1) > 1e-15)
        if bool(np.all(keep)):
            break
        B = B[np.ix_(keep, keep)]
    if B.shape[0] == 0:
        return 0.0
    vals = np.linalg.eigvals(B)
    return float(np.max(np.abs(vals))) if len(vals) else 0.0

def build_kernel_matrix(df, seeds, max_horizon=None):
    sub = df[df.seed.isin(seeds)].copy()
    if max_horizon is not None:
        sub['child_eff'] = np.where((sub.child == 1) & (sub.first_time <= max_horizon), 1, 0)
    else:
        sub['child_eff'] = sub.child
        
    locs = sorted(set(sub.origin.unique()) | set(sub.destination.unique()))
    L = len(locs)
    li = {x: i for i, x in enumerate(locs)}
    ti = {x: i for i, x in enumerate(TYPES)}
    n = L * len(TYPES)
    K = np.zeros((n, n), float)
    P0 = np.zeros((L, L, len(TYPES)), float)
    
    den = max(len(set(seeds)), 1)
    pl = sub[(sub.parent_type == 'none') & (sub.child_eff == 1)]
    for (o, j, c), g in pl.groupby(['origin', 'destination', 'child_type']):
        if c in ti:
            P0[li[o], li[j], ti[c]] = g.seed.nunique() / den
            
    for pt in TYPES:
        if pt not in ti: continue
        x = sub[sub.parent_type == pt]
        for (o, j, c), g in x[x.child_eff == 1].groupby(['origin', 'destination', 'child_type']):
            if c not in ti: continue
            raw = g.seed.nunique() / den
            excess = max(0.0, raw - P0[li[o], li[j], ti[c]])
            K[li[o] * len(TYPES) + ti[pt], li[j] * len(TYPES) + ti[c]] = excess
            
    return K, locs

def analyze_reproduction(csv_path: str, out_path: str, n_bootstrap: int = 500):
    df = pd.read_csv(csv_path)
    seeds = sorted(df.seed.unique())
    origins = sorted(df.origin.unique())
    
    hits = df[df.child == 1].copy()
    first_times = hits['first_time'].to_numpy(float)
    g_mean = float(np.mean(first_times))
    g_median = float(np.median(first_times))
    g_std = float(np.std(first_times, ddof=1))
    g_min = float(np.min(first_times))
    g_max = float(np.max(first_times))
    g_p25 = float(np.percentile(first_times, 25))
    g_p75 = float(np.percentile(first_times, 75))
    g_p90 = float(np.percentile(first_times, 90))
    
    weekly_bins = list(range(0, 189, 7))
    counts, _ = np.histogram(first_times, bins=weekly_bins)
    weekly_density = {f"day_{weekly_bins[i]}_{weekly_bins[i+1]}": int(c) for i, c in enumerate(counts)}
    
    horizons = [7, 14, 21, 30, 45, 60, 90, 120, 150, 180]
    horizon_results = []
    
    rng = np.random.default_rng(20260910)
    for h in horizons:
        Kh, locs = build_kernel_matrix(df, seeds, max_horizon=h)
        rho_h = prune_and_spectral_radius(Kh)
        
        boots = []
        if len(seeds) > 1 and n_bootstrap > 0:
            for _ in range(n_bootstrap):
                sample_seeds = list(rng.choice(seeds, size=len(seeds), replace=True))
                parts = []
                for bi, s in enumerate(sample_seeds):
                    z = df[df.seed == s].copy()
                    z['seed'] = bi
                    parts.append(z)
                bd = pd.concat(parts, ignore_index=True)
                Kb, _ = build_kernel_matrix(bd, list(range(len(sample_seeds))), max_horizon=h)
                boots.append(prune_and_spectral_radius(Kb))
            ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
        else:
            ci = None
            
        times_h = hits[hits.first_time <= h]['first_time'].to_numpy(float)
        mean_t_h = float(np.mean(times_h)) if len(times_h) > 0 else float(h)
        lambda_eff = float(np.log(max(rho_h, 1e-12)) / (mean_t_h / 30.0))
        
        horizon_results.append({
            'horizon_days': h,
            'rho_K': rho_h,
            'ci95': ci,
            'children_count': int((hits.first_time <= h).sum()),
            'mean_first_time': mean_t_h,
            'lambda_eff_per_30d': lambda_eff
        })
        
    hits_m = hits[hits.parent_type.isin(['M', 'MF', 'MG', 'MFG'])].copy()
    hits_m['dist_bin'] = pd.cut(hits_m['distance_km'], bins=[0, 25, 50, 75, 100, 150, 200])
    dist_curve = hits_m.groupby('dist_bin', observed=False).agg(
        n=('child', 'count'),
        mean_time=('first_time', 'mean'),
        adjacent_frac=('adjacent_origin', 'mean')
    ).reset_index()
    dist_curve['dist_bin'] = dist_curve['dist_bin'].astype(str)
    
    child_type_dist = hits['child_type'].value_counts().to_dict()
    trigger_dist = hits['trigger_event'].value_counts().to_dict()
    
    parent_cases = df.groupby(['seed', 'origin', 'parent_type'], as_index=False).child.sum()
    parent_stats = {}
    for pt, g in parent_cases.groupby('parent_type'):
        arr = g.child.to_numpy(float)
        parent_stats[pt] = {
            'mean_offspring': float(arr.mean()),
            'std_offspring': float(arr.std(ddof=1)),
            'p_any': float(np.mean(arr > 0)),
            'total_offspring': int(arr.sum())
        }
        
    out = {
        'schema_version': 'pineland.reproduction_kernel_results.v1',
        'status': 'synthetic_normalized_first_generation_complete',
        'historical_outcomes_used': False,
        'input': str(Path(csv_path)),
        'input_sha256': sha(csv_path),
        'generation_time_density': {
            'mean_days': g_mean,
            'median_days': g_median,
            'std_days': g_std,
            'iqr_days': [g_p25, g_p75],
            'p90_days': g_p90,
            'min_days': g_min,
            'max_days': g_max,
            'weekly_binned_counts': weekly_density,
            'plateau_verified': bool(g_max <= 158.0 and (hits.first_time > 158.0).sum() == 0)
        },
        'horizon_curve': horizon_results,
        'type_reduction': {
            'child_types_produced': child_type_dist,
            'mf_or_m_fraction': float((hits.child_type.isin(['M', 'MF'])).mean()),
            'g_produced_at_first_gen': bool((hits.child_type.str.contains('G')).sum() > 0),
            'dominant_trigger': trigger_dist,
            'recruitment_trigger_fraction': float((hits.trigger_event == 'recruitment').mean()),
            'falsification_parent_types': {
                'E_offspring': parent_stats.get('E', {}).get('total_offspring', 0),
                'F_offspring': parent_stats.get('F', {}).get('total_offspring', 0),
                'G_offspring': parent_stats.get('G', {}).get('total_offspring', 0),
                'FG_offspring': parent_stats.get('FG', {}).get('total_offspring', 0),
                'none_placebo_offspring': parent_stats.get('none', {}).get('total_offspring', 0)
            },
            'parent_type_stats': parent_stats
        },
        'spatial_kernel': {
            'distance_binned': dist_curve.to_dict('records'),
            'adjacent_fraction': float(hits.adjacent_origin.mean()),
            'median_distance_km': float(hits.distance_km.median())
        },
        'interpretation_guard': 'Reproduction kernel estimates are derived strictly from experimentally isolated single-parent synthetic trials without external support. Results characterize the native generative structure of Pineland, not real-world insurgent reproduction.'
    }
    
    Path(out_path).write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
    print(f"Wrote reproduction kernel results to {out_path}")
    print(f"Generation time: mean={g_mean:.1f}d, median={g_median:.1f}d, max={g_max:.1f}d")
    print(f"Horizon curve: rho(30)={horizon_results[3]['rho_K']:.3f}, rho(90)={horizon_results[6]['rho_K']:.3f}, rho(180)={horizon_results[9]['rho_K']:.3f}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('--out', required=True)
    ap.add_argument('--bootstrap', type=int, default=500)
    args = ap.parse_args()
    analyze_reproduction(args.csv, args.out, args.bootstrap)
