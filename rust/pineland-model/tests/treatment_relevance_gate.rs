use pineland_model::treatment_gate::{run_preflight_treatment_gate, GateOptions};

#[test]
fn treatment_relevance_gate_12_worlds() {
    let options = GateOptions {
        locality_count: 72,
        agent_count: 1000,
        withdrawal_time_days: 120.0,
        observation_start_days: 60.0,
        horizon_days: 7.0,
        verbose: true,
    };

    let summary = run_preflight_treatment_gate(&options)
        .expect("preflight treatment-relevance gate execution succeeded");

    assert!(
        summary.combat_liveness_pass,
        "Combat Liveness check failed: zero contacts or military losses recorded across active worlds"
    );
    assert!(
        summary.air_liveness_pass,
        "Air Support Liveness check failed: zero air assisted contacts or air donor cost in air-supported worlds"
    );
    assert!(
        summary.logistics_liveness_pass,
        "Logistics Liveness check failed: zero external logistics delivered or donor cost in logistics-strained worlds"
    );
    assert!(
        summary.forcegen_liveness_pass,
        "Force Generation Liveness check failed: zero external graduates or donor cost in forcegen-constrained worlds"
    );
    assert!(
        summary.command_liveness_pass,
        "Command Liveness check failed: zero command events or donor cost in command-critical worlds"
    );
    assert!(
        summary.counterfactual_exactness_pass,
        "Counterfactual Exactness check failed: negative control 'none' profile drifted between ON and OFF branches"
    );
    assert!(
        summary.branch_divergence_pass,
        "Supported Branch Divergence check failed: active treated cells exhibited degenerate identical ON and OFF branches"
    );
    assert!(
        summary.encounter_realism_pass,
        "Encounter realism failed: too much combat depended on forced same-locality microzone fallback"
    );
    assert!(
        summary.overall_pass,
        "Preflight Treatment-Relevance Gate failed overall verification"
    );
}
