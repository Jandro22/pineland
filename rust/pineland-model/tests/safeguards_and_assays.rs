use pineland_model::assays::{
    run_binding_constraint_assay, run_channel_isolation_assay, run_dose_sanity_assay,
    run_end_to_end_causal_trace, run_horizon_sufficiency_assay, run_outcome_sensitivity_assay,
    run_withdrawal_shock_assay,
};
use pineland_model::treatment_gate::GateOptions;

fn standard_options() -> GateOptions {
    GateOptions {
        locality_count: 72,
        agent_count: 1000,
        withdrawal_time_days: 120.0,
        observation_start_days: 60.0,
        horizon_days: 7.0,
        verbose: true,
        smoke_mode: false,
    }
}

#[test]
fn test_outcome_sensitivity_assay() {
    let opts = standard_options();
    let summary = run_outcome_sensitivity_assay(&opts)
        .expect("Outcome-sensitivity assay executed successfully");

    assert!(
        summary.pass,
        "Outcome sensitivity failed: C saturated or non-monotonic across engineering worlds: {}",
        summary.detail
    );
}

#[test]
fn test_channel_isolation_assay() {
    let opts = standard_options();
    let summary =
        run_channel_isolation_assay(&opts).expect("Channel-isolation assay executed successfully");

    for r in &summary.results {
        eprintln!(
            "ISOLATION {} pass={} input={:.6} mechanism={:.6} downstream={:.6} cost={:.2} C_on={:.6} C_off={:.6}",
            r.channel, r.pass, r.input_delivered, r.mechanism_state_diff,
            r.downstream_effect, r.donor_cost, r.composite_capability_on,
            r.composite_capability_off
        );
    }
    assert!(
        summary.pass,
        "Channel isolation failed: at least one channel failed causal isolation"
    );
    for r in &summary.results {
        assert!(
            r.pass,
            "Channel {} failed isolation test: delivered={:.2}, mechanism={:.4}, downstream={:.4}, cost={:.2}",
            r.channel, r.input_delivered, r.mechanism_state_diff, r.downstream_effect, r.donor_cost
        );
    }
}

#[test]
fn test_binding_constraint_assay() {
    let opts = standard_options();
    let summary = run_binding_constraint_assay(&opts)
        .expect("Binding-constraint assay executed successfully");

    for r in &summary.results {
        eprintln!(
            "BINDING {} pass={} {}",
            r.channel, r.binding_verified, r.description
        );
    }
    assert!(
        summary.pass,
        "Binding constraint failed: at least one channel failed to bind under stress"
    );
    for r in &summary.results {
        assert!(
            r.binding_verified,
            "Channel {} failed binding constraint: {}",
            r.channel, r.description
        );
    }
}

#[test]
fn test_support_dose_sanity_curves() {
    let opts = standard_options();
    let summary =
        run_dose_sanity_assay(&opts).expect("Support-dose sanity assay executed successfully");

    assert!(
        summary.pass,
        "Support dose sanity curves failed monotonicity check"
    );
    for r in &summary.results {
        assert!(
            r.monotonic,
            "Channel {} dose response was non-monotonic: doses={:?}, exposures={:?}",
            r.channel, r.doses, r.exposures
        );
    }
}

#[test]
fn test_withdrawal_shock_assay() {
    let opts = standard_options();
    let summary =
        run_withdrawal_shock_assay(&opts).expect("Withdrawal-shock assay executed successfully");

    assert!(
        summary.support_withdrawn_at_t,
        "Support withdrawal flag was not set at T on OFF branch"
    );
    assert!(
        summary.immediate_severing_verified,
        "Withdrawal shock failed immediate severing: post_t_off_cost={:.2}, post_t_on_cost={:.2}",
        summary.post_t_off_cost, summary.post_t_on_cost
    );
    assert_eq!(
        summary.post_t_off_cost, 0.0,
        "OFF branch accrued donor cost after withdrawal at T"
    );
}

#[test]
fn test_horizon_sufficiency_assay() {
    let opts = standard_options();
    let summary = run_horizon_sufficiency_assay(&opts)
        .expect("Horizon-sufficiency assay executed successfully");

    eprintln!(
        "HORIZON pass={} 180_sufficient={} recommended_terminal={:.0}d div_180={:.4} div_360={:.4} relative_change={:.3}",
        summary.horizon_design_pass,
        summary.horizon_180d_sufficient,
        summary.recommended_terminal_horizon_days,
        summary.divergence_180d,
        summary.divergence_360d,
        summary.relative_change_after_180
    );
    assert!(
        summary.horizon_design_pass,
        "horizon diagnostic found neither a stabilized 180-day effect nor a non-degenerate 360-day extension: div_180={:.4}, div_360={:.4}, relative_change={:.3}",
        summary.divergence_180d, summary.divergence_360d, summary.relative_change_after_180
    );
}

#[test]
fn test_end_to_end_causal_trace() {
    let opts = standard_options();
    let summary =
        run_end_to_end_causal_trace(&opts).expect("End-to-end causal trace executed successfully");

    assert!(
        summary.chain_verified,
        "End-to-end causal trace chain failed: contacts={}, losses={:.1}, air={}, supply={:.1}, cmd={}, fg={:.1}, C={:.4}",
        summary.contacts, summary.military_losses, summary.air_sorties, summary.supply_delivered,
        summary.command_orders_assisted, summary.graduates_deployed, summary.final_composite_capability
    );
}
