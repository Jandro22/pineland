#!/usr/bin/env python3
"""Validate manuscript mechanics and headline evidence against tracked Stage-4 outputs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper" / "partner_force_autonomy"
EVIDENCE = (
    ROOT
    / "studies"
    / "research_program"
    / "general_theory_v1"
    / "partner_force_autonomy"
    / "evidence"
    / "stage4"
)
STAGE5 = EVIDENCE.parent / "stage5"
STRUCTURAL = EVIDENCE.parent / "structural_falsification"
REVIEW = EVIDENCE.parent / "review_revision"
ABLATION = EVIDENCE.parent / "mechanism_ablation"


def main() -> None:
    manuscript = (PAPER / "manuscript.md").read_text(encoding="utf-8")
    paper_text = "\n".join(
        path.read_text(encoding="utf-8", errors="strict")
        for path in PAPER.iterdir()
        if path.is_file() and path.suffix in {".md", ".bib", ".py"}
    )

    assert "\u2014" not in paper_text, "em dash found in paper source"
    assert "\ufffd" not in paper_text, "Unicode replacement character found"

    bib = (PAPER / "references.bib").read_text(encoding="utf-8")
    bib_keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    cited_keys: set[str] = set()
    for block in re.findall(r"\[(@[^\]]+)\]", manuscript):
        cited_keys.update(re.findall(r"@([A-Za-z0-9_:-]+)", block))
    missing = cited_keys - bib_keys
    assert not missing, f"missing bibliography keys: {sorted(missing)}"
    unused = bib_keys - cited_keys
    assert not unused, f"unused bibliography keys: {sorted(unused)}"

    ready = json.loads(
        (EVIDENCE / "READY_STAGE4_INTEGRATED.json").read_text(encoding="utf-8")
    )
    assert ready["status"] == "STAGE4_INTEGRATED_PROGRAM_COMPLETE"
    assert ready["production_worlds"] == 2808

    phase = pd.read_csv(EVIDENCE / "phase_cell_summary_v1.csv")
    treated = phase[phase["factor_support_intensity"] > 0]
    effective = treated[treated["phase_regime"] != "not_initially_effective"]
    assert len(treated) == 120
    assert len(effective) == 106
    assert (effective["phase_regime"] == "effective_autonomy_trap").sum() == 96
    assert (effective["phase_regime"] == "effective_autonomy_building").sum() == 10
    assert (
        treated["robust_phase_regime"] == "robust_effective_autonomy_trap"
    ).sum() == 53
    assert (
        treated["robust_phase_regime"] == "robust_effective_autonomy_building"
    ).sum() == 0

    migration = pd.read_csv(EVIDENCE / "migration_target_match_summary_v1.csv")
    matched = migration[
        migration["observed_target_match"].eq(True)
        & migration["factor_support_target"].isin(["command", "forcegen", "logistics"])
    ]
    expected_migration = {
        "command": (38, 38),
        "forcegen": (46, 46),
        "logistics": (85, 0),
    }
    for target, (expected_n, expected_events) in expected_migration.items():
        group = matched[matched["factor_support_target"] == target]
        assert int(group["n"].sum()) == expected_n
        assert int(group["persistent_migration_count"].sum()) == expected_events

    expected_relief_yield = {
        "command": (0.00353620531578948, 0.0555494112894737),
        "forcegen": (2.07804347823507e-7, 0.0),
        "logistics": (0.0169926201764706, -0.221527308552941),
    }
    for target, (expected_cap30, expected_q360) in expected_relief_yield.items():
        group = matched[matched["factor_support_target"] == target]
        n = float(group["n"].sum())
        cap30 = float((group["mean_delta_capability_h30"] * group["n"]).sum() / n)
        q360 = float((group["mean_delta_q_feasible_h360"] * group["n"]).sum() / n)
        assert abs(cap30 - expected_cap30) < 1e-12
        assert abs(q360 - expected_q360) < 1e-12

    mechanism = pd.read_csv(EVIDENCE / "mechanism_mode_contrasts_v1.csv")
    logistics = mechanism[
        mechanism["factor_target"].eq("logistics")
        & mechanism["contrast"].eq("development_minus_substitution")
    ]
    assert len(logistics) == 4
    assert (logistics["delta_q_feasible_h360_boot95_lo"] > 0).all()
    assert (logistics["delta_q_feasible_h360_boot95_hi"] > 0).all()

    stage5_ready = json.loads((STAGE5 / "READY.json").read_text(encoding="utf-8"))
    assert stage5_ready["status"] == "STAGE5_ANALYSIS_COMPLETE"
    assert stage5_ready["expected_worlds"] == 1472
    assert stage5_ready["production_git_commit"] == "8d342c982e385699e76c766ec06ae991bc451876"
    assert stage5_ready["analysis_git_commit"] == stage5_ready["production_git_commit"]

    breadth = pd.read_csv(STAGE5 / "stage5_fixed_effort_breadth_premiums_v1.csv")
    assert len(breadth) == 32
    assert int((breadth["boot95_lo"] > 0).sum()) == 0
    assert int((breadth["boot95_hi"] < 0).sum()) == 21
    breadth_means = breadth.groupby("factor_starting_structure")["mean_breadth_premium_q"].mean()
    expected_breadth_means = {
        "command_constrained": -0.045882,
        "forcegen_constrained": -0.125743,
        "logistics_constrained": -0.043190,
        "near_tie_low": -0.076039,
    }
    for key, expected in expected_breadth_means.items():
        assert abs(float(breadth_means[key]) - expected) < 5e-7

    interactions = pd.read_csv(STAGE5 / "stage5_factorial_interactions_v1.csv")
    assert len(interactions) == 32
    sig_pos = interactions[interactions["boot95_lo"] > 0]
    sig_neg = interactions[interactions["boot95_hi"] < 0]
    assert len(sig_pos) == 2
    assert len(sig_neg) == 1
    nt_hi = interactions[
        interactions["factor_starting_structure"].eq("near_tie_low")
        & interactions["factor_intensity"].eq(1.0)
    ].set_index("interaction")
    assert abs(float(nt_hi.loc["forcegen+logistics", "mean_interaction_q"]) - 0.02473019) < 1e-8
    assert abs(float(nt_hi.loc["logistics+command", "mean_interaction_q"]) - 0.1717280) < 1e-7
    assert abs(float(nt_hi.loc["forcegen+logistics+command", "mean_interaction_q"]) + 0.05612863) < 1e-8

    paths = pd.read_csv(STAGE5 / "stage5_bottleneck_paths_v1.csv")
    split_counts = pd.crosstab(paths["factor_starting_structure"], paths["initial_postsplit_bottleneck"])
    assert int(split_counts.loc["forcegen_constrained", "logistics"]) == 368
    assert int(split_counts.loc["logistics_constrained", "logistics"]) == 368
    assert int(split_counts.loc["near_tie_low", "logistics"]) == 365
    assert int(split_counts.loc["near_tie_low", "command"]) == 3
    assert int(split_counts.loc["command_constrained", "command"]) == 100
    assert int(split_counts.loc["command_constrained", "logistics"]) == 268

    structural = json.loads((STRUCTURAL / "structural_result_v1.json").read_text(encoding="utf-8"))
    assert structural["worlds"] == 32
    assert structural["target_matched_worlds"] == 24
    assert structural["matched_command_terminal_worlds"] == 8
    assert structural["matched_forcegen_terminal_worlds"] == 8
    assert structural["matched_logistics_terminal_worlds"] == 8
    assert structural["unique_logistics_hard_code_rejected"] is True

    headroom = json.loads((EVIDENCE / "stage4_headroom_global_v1.json").read_text(encoding="utf-8"))
    assert headroom["observed_matched_treated_worlds"] == 169
    assert headroom["headroom_defined_worlds"] == 126
    assert abs(headroom["pearson_headroom_vs_delta_capability_h30"] + 0.08267959790872006) < 1e-8
    assert abs(headroom["spearman_headroom_vs_delta_capability_h30"] - 0.18738249198817408) < 1e-8

    control = pd.read_csv(REVIEW / "stage4_control_matched_capability_v1.csv")
    c30 = (
        control[np.isclose(control["horizon_days"].astype(float), 30.0)]
        .groupby("cell_id")
        .agg(
            supported=("supported_vs_control", "mean"),
            retained=("retained_vs_control", "mean"),
        )
    )
    eps = 1.0e-6
    assert int(((c30["supported"] > eps) & (c30["retained"] < -eps)).sum()) == 26
    assert int(((c30["supported"] > eps) & (c30["retained"] > eps)).sum()) == 30
    assert int(((c30["supported"] < -eps) & (c30["retained"] < -eps)).sum()) == 51
    assert int(((c30["supported"] < -eps) & (c30["retained"] > eps)).sum()) == 1

    decomposition = json.loads(
        (REVIEW / "stage4_supply_demand_decomposition_v1.json").read_text(encoding="utf-8")
    )
    assert decomposition["negative_coverage_same_terminal_bottleneck_worlds"] == 1174
    assert abs(decomposition["higher_demand_fraction"] - 0.959114139693356) < 1e-12
    assert abs(decomposition["lower_indigenous_service_fraction"] - 0.19846678023850084) < 1e-12

    standard = pd.read_csv(REVIEW / "stage4_demand_standardization_summary_v1.csv")
    effective_penalty = standard[standard["subset"] == "h30_effective_penalty"].iloc[0]
    assert int(effective_penalty["n"]) == 823
    assert abs(float(effective_penalty["mean_observed_effect"]) + 0.0822570081429633) < 1e-12
    assert abs(float(effective_penalty["mean_production_only_effect"]) + 0.0300896831135591) < 1e-12
    assert abs(float(effective_penalty["mean_demand_only_effect"]) + 0.0533801777512384) < 1e-12

    migration_penalty = pd.read_csv(REVIEW / "stage4_migration_penalty_summary_v1.csv").set_index("group")
    assert abs(float(migration_penalty.loc["effective_migrated", "mean_delta_q_h360"]) + 0.0224) < 5e-4
    assert abs(float(migration_penalty.loc["effective_not_migrated", "mean_delta_q_h360"]) + 0.0492) < 5e-4

    ablation_result = ABLATION / "mechanism_ablation_result_v1.json"
    if ablation_result.exists():
        ablation = json.loads(ablation_result.read_text(encoding="utf-8"))
        assert ablation["status"] == "ANALYSIS_COMPLETE"
        assert ablation["worlds"] == 96
        assert ablation["paired_worlds"] == 48
        assert ablation["manipulation_check_pass"] is True
        assert abs(ablation["clamp_fraction_within_5pct"] - 1.0) < 1e-12
        assert abs(ablation["clamp_error_median"] - 0.004609667710807261) < 1e-12
        assert abs(ablation["pooled_mean_delta_q_h360_normal"]) < 1e-12
        assert abs(ablation["pooled_mean_delta_q_h360_clamp"]) < 1e-12
        assert abs(ablation["pooled_mean_attenuation_q_h360"]) < 1e-12
        paired = pd.read_csv(ABLATION / "mechanism_ablation_paired_v1.csv")
        for horizon in (7, 30, 90, 180, 360):
            assert np.allclose(paired[f"delta_q_h{horizon}_normal"], 0.0)
            assert np.allclose(paired[f"delta_q_h{horizon}_clamp"], 0.0)
        pooled = pd.read_csv(ABLATION / "mechanism_ablation_summary_v1.csv")
        pooled = pooled[pooled["group"].eq("pooled")].iloc[0]
        assert abs(float(pooled["mean_change_capability_effect_h30"]) + 0.09252377220833335) < 1e-12
        assert abs(float(pooled["mean_change_capability_effect_h360"]) + 0.14650369160416668) < 1e-12

    print(
        "PASS manuscript validation: mechanics clean; citations closed; "
        "Stage-4/5, review diagnostics, headroom, structural-falsification, "
        "and mechanism-ablation claims match tracked evidence"
    )


if __name__ == "__main__":
    main()
