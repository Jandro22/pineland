# Pineland COIN-SIM v0.12.0 research-audit closure

Version 0.12.0 closes the executable software and measurement-integrity items
identified in the v0.11 pre-publication audit. It does not claim that synthetic
priors are empirical estimates; empirical validation remains a case-data task.

## Closed implementation gates

- The simulator has an explicit `burn_in_days` phase. Warm-up events run at
  negative model time, are excluded from event, observation, causal, ledger,
  and checkpoint outputs, and the stabilized state is re-baselined at time 0.
- Formation positions are explicit microzones. Government and insurgent reach
  are computed from the same presence/response process and then adjusted by a
  symmetric contestation term. Zone-level diagnostics expose both sides.
- Civilian mobility reads `ActorBeliefView`; environment and analyst code use
  `WorldTruthView`; recorded outputs use `EmpiricalRecordView`.
- Expected-control updates are a scheduled event. Recruitment has one owner
  and one recurring clock. Every processed event emits a sparse state delta and
  event-boundary stock transactions.
- Organization thresholds use represented population. Birth startup supply is
  converted from organization resources exactly once. Organization identity
  heterogeneity is weighted within-group variance.
- Observation fusion applies source-correlation attenuation and one explicit
  language-fusion exponent. Recording channels have source-specific rates,
  severity/access/remoteness, noise, and geocoding-distance distributions.
- Foreign interventions report gross transfer, host retention, crowding-out,
  peak capacity, and withdrawal quantities.
- Empirical targets can carry construct correspondence declarations covering the
  theoretical construct, latent state, simulation and empirical observables,
  transformation, observation model, mismatch, and calibration status.

## Executable validation batteries

`pineland_sim.research_audit` provides reproducible diagnostics:

`truth_firewall_check`, `scheduler_audit`, `causal_ledger_audit`,
`null_and_extreme_checks`, `recording_calibration`, `resolution_ladder`,
`initialization_ensemble`, `morris_sensitivity`, `variance_sensitivity`,
`parameter_recovery_ensemble`, `mechanism_ablation`,
`foreign_withdrawal_diagnostics`, `language_factorial`,
`fragmentation_bargaining_ablation`, and `long_horizon_diagnostics`.

Each reports raw counts/distributions and a machine-readable pass or warning
field where a binary criterion is scientifically meaningful. Resolution,
sensitivity, recovery, and recording diagnostics are distributional; they must
be rerun after changes to parameters, mechanisms, or case data.

## Evidence boundary

The parameter registry now tags each scalar as an empirical estimand, literature
prior, structural/scaling coefficient, engineering prior, numerical safeguard,
or experimental treatment. Missing external citations are explicit rather than
silently represented as empirical provenance. A substantive empirical claim is
publication-ready only after case-specific construct correspondence,
source-calibrated recording, temporal/geographic holdouts, repeated synthetic
recovery, global sensitivity, model-ladder comparison, multi-resolution
uncertainty, and mechanism ablation are supplied.
