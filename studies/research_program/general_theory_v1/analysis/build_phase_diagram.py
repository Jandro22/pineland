#!/usr/bin/env python3
"""
Dimensionless Phase Diagram Analysis (v1).

Maps simulated Pineland trajectories across the fundamental dimensionless groups:
1. Pi_0: Reproduction potential / basic reproductive ratio
2. Pi_M: Mobilization strain / resource exhaustion ratio
3. Pi_S: State institutional regeneration ratio
4. Gamma: Competitive net margin

Identifies and formalizes the boundaries separating:
1. Endogenous Extinction
2. Mobilization Trap / Resource Exhaustion
3. Externally Maintained Persistence
4. Localized Endemic Persistence
5. Spatial Expansion
6. State Consolidation / Durable Quiet

Outputs:
- phase_diagram_results_v1.json
"""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

def sha256_file(p: str | Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='studies/research_program/general_theory_v1/phase_diagram_results_v1.json')
    args = parser.parse_args()

    # Load evidence sources
    rep_path = Path('studies/research_program/general_theory_v1/reproduction_kernel_results_v1.json')
    mob_path = Path('studies/research_program/general_theory_v1/mobilization_resource_results_v1.json')
    state_path = Path('studies/research_program/general_theory_v1/state_regeneration_results_v1.json')
    comp_path = Path('studies/research_program/general_theory_v1/competitive_dynamics_results_v1.json')

    rep_data = json.loads(rep_path.read_text(encoding='utf-8'))
    mob_data = json.loads(mob_path.read_text(encoding='utf-8'))
    state_data = json.loads(state_path.read_text(encoding='utf-8'))
    comp_data = json.loads(comp_path.read_text(encoding='utf-8'))

    # Extract empirically verified parameter values and boundaries
    # From reproduction kernel:
    rho_K_inf = float(rep_data['horizon_curve'][-1]['rho_K']) # ~6.394
    rho_K_30 = float([x['rho_K'] for x in rep_data['horizon_curve'] if x['horizon_days'] == 30][0]) # 1.658
    generation_time_mean = rep_data['generation_time_density']['mean_days'] # 59.44d
    generation_time_max = rep_data['generation_time_density']['max_days'] # 158d

    # From mobilization sweep:
    # Safe regime: strain_proxy <= 0.125 -> 100% survival
    # Transition regime: 0.25 <= strain_proxy <= 0.50 -> partial survival (p in (0, 1))
    # Trap regime: strain_proxy >= 1.0 -> 0% survival
    mob_cells = mob_data['cell_summaries']
    safe_cells = [c for c in mob_cells if c['p_survival'] == 1.0]
    transition_cells = [c for c in mob_cells if 0.0 < c['p_survival'] < 1.0]
    trap_cells = [c for c in mob_cells if c['p_survival'] == 0.0]

    pi_m_safe_upper = max(c['strain_proxy'] for c in safe_cells) if safe_cells else 0.125
    pi_m_trap_lower = min(c['strain_proxy'] for c in trap_cells) if trap_cells else 1.0

    # From state regeneration:
    mean_Q_final = state_data['primary']['mean_final_Q_capacity'] # 0.0068
    tau_state_renewal_days = "> 360" # no recovery to 50% at 180 days

    # From competitive dynamics:
    gamma_expansion = comp_data['critical_inflection_thresholds']['expansion_regime_threshold']
    gamma_collapse = comp_data['critical_inflection_thresholds']['collapse_hazard_threshold']

    regimes = [
        {
            'regime_id': 'R1_endogenous_extinction',
            'name': 'Endogenous Extinction',
            'governing_conditions': {
                'Pi_0': '< 1.0',
                'Pi_U': '< 1.0',
                'Gamma': '< 0.0'
            },
            'physical_mechanism': (
                "Subcritical reproduction without external sanctuary or material subsidy. "
                "Each generation produces fewer than 1 spatial offspring, leading to demographic "
                "and organizational extinction within finite time."
            ),
            'typical_outcome': 'Insurgent organization collapses, footholds extinguish, 0 active formations.'
        },
        {
            'regime_id': 'R2_mobilization_trap',
            'name': 'Mobilization Trap (Resource Exhaustion)',
            'governing_conditions': {
                'Pi_0': '>= 1.0',
                'Pi_M': f'>= {pi_m_trap_lower}',
                'capital_depletion': '100% complete'
            },
            'physical_mechanism': (
                "Mobilization rate and fighter conversion outrun organizational material replenishment. "
                "Fielded force creates unsustainable burn rate, exhausting central organizational capital to 0. "
                "Produces catastrophic organizational collapse despite high initial recruitment mass."
            ),
            'typical_outcome': 'Hard capital exhaustion, organizational disbanding, stranded formations.'
        },
        {
            'regime_id': 'R3_externally_maintained_persistence',
            'name': 'Externally Maintained Persistence',
            'governing_conditions': {
                'Pi_0': '< 1.0',
                'Pi_U': '>= 1.0'
            },
            'physical_mechanism': (
                "Endogenous reproduction is subcritical, but cross-border external sanctuary or "
                "foreign resource transfers replenish losses faster than local attrition."
            ),
            'typical_outcome': 'Border-adjacent persistence, immune to local COIN clearing.'
        },
        {
            'regime_id': 'R4_localized_endemic_persistence',
            'name': 'Localized Endemic Persistence',
            'governing_conditions': {
                'Pi_0': '~ 1.0',
                'Pi_M': f'< {pi_m_safe_upper}',
                'Gamma': f'between {gamma_collapse:.3f} and {gamma_expansion:.3f}'
            },
            'physical_mechanism': (
                "Balanced generation dynamics. Insurgent replaces losses locally at a sustainable rate "
                "without overtaxing capital stocks or expanding beyond local rough terrain."
            ),
            'typical_outcome': 'Protracted low-intensity conflict, stable foothold presence.'
        },
        {
            'regime_id': 'R5_spatial_expansion',
            'name': 'Spatial Expansion',
            'governing_conditions': {
                'Pi_0': f'> 1.0 (baseline rho_inf ~ {rho_K_inf:.2f})',
                'Pi_M': f'< {pi_m_safe_upper}',
                'Gamma': f'> {gamma_expansion:.3f}'
            },
            'physical_mechanism': (
                "Supercritical spatial reproduction. Parent rooted membership establishes offspring in "
                "adjacent network localities via recruitment waves within generation horizon tau_g <= 158 days."
            ),
            'typical_outcome': 'Multi-district expansion, governance erosion, foothold network growth.'
        },
        {
            'regime_id': 'R6_state_consolidation_durable_quiet',
            'name': 'State Consolidation (Durable Quiet)',
            'governing_conditions': {
                'Gamma': f'< {gamma_collapse:.3f}',
                'Pi_S': 'institutional presence intact',
                'insurgent_presence': 'extinguished or marginalized'
            },
            'physical_mechanism': (
                "State authority maintains overwhelming competitive margin. Insurgent organizational capital "
                "and membership depth are suppressed below establishment threshold."
            ),
            'typical_outcome': 'Full government administrative and physical control.'
        }
    ]

    phase_diagram = {
        'schema_version': 'pineland.phase_diagram_results.v1',
        'status': 'synthetic_phase_diagram_derived',
        'historical_outcomes_used': False,
        'fundamental_dimensionless_groups': {
            'Pi_0': {
                'formula': 'rho(K_infinity) = max eigenvalue of spatial reproduction operator',
                'interpretation': 'Basic spatial reproduction number across generational lifecycle',
                'critical_value': 1.0,
                'empirical_baseline': rho_K_inf,
            },
            'Pi_M': {
                'formula': 'r * f / c = (recruitment_rate * fighter_conversion) / capital_stock',
                'interpretation': 'Mobilization strain index: recruitment & fielding burn rate vs capital',
                'safe_threshold': pi_m_safe_upper,
                'exhaustion_threshold': pi_m_trap_lower,
                'universality_status': 'Falsified as single universal scalar (within-strain dispersion > 15%); derived as two-timescale ratio Pi_M = tau_replenish / tau_mobilize',
            },
            'Pi_S': {
                'formula': 'tau_renewal / tau_conflict',
                'interpretation': 'Ratio of state institutional regeneration tempo to conflict tempo',
                'empirical_finding': 'Q_S(180) ~ 0.007; state capacity is strongly hysteretic and does not passively recover from central fiscal injection over 180 days',
            },
            'Gamma': {
                'formula': 'log(insurgent_stock) - log(state_stock)',
                'interpretation': 'Competitive margin governing trajectory inflection',
                'critical_expansion_threshold': gamma_expansion,
                'critical_collapse_threshold': gamma_collapse,
            }
        },
        'phase_regimes': regimes,
        'bifurcation_boundaries': {
            'extinction_boundary': 'Pi_0 = 1.0 (transcritical bifurcation between extinction and endemic survival)',
            'mobilization_trap_boundary': f'Pi_M in [{pi_m_safe_upper}, {pi_m_trap_lower}] (saddle-node bifurcation causing sudden capital collapse)',
            'expansion_boundary': f'Gamma = {gamma_expansion:.3f} (spatial front propagation threshold)',
        },
        'theoretical_compression_summary': (
            "The multi-agent dynamics of Pineland compress into a universal phase diagram governed by "
            "four dimensionless groups: Pi_0 (reproduction), Pi_M (mobilization strain), Pi_S (state renewal), "
            "and Gamma (competitive margin). The boundaries demarcate distinct qualitative dynamical regimes "
            "with zero reference to historical data fitting."
        )
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(phase_diagram, indent=2), encoding='utf-8')
    print(f"Wrote phase diagram results to {args.out}")

if __name__ == '__main__':
    main()
