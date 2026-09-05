# Research-readiness contract

Pineland is now instrumented as a research engine rather than only a feature
demonstrator. The implementation is deliberately diagnostic: synthetic runs
can establish software, conservation, and identification properties, but they
cannot establish historical validity.

## Truth firewall

Actor-facing bargaining, patrol routing, force reallocation, information
fusion, civilian behavior, recruitment, and organization onset use beliefs or
experience-side variables. `bargaining_values(..., perspective="truth")` and
the truth view are analyst-only counterfactuals. Organization onset records
`expected_repression` separately from `experienced_repression`; only the
expected value enters the founder hazard.

Run `pineland-sim truth-firewall` for the paired hidden-state metamorphic
battery. It holds beliefs and RNG streams fixed while perturbing latent
physical control and reports whether actor choices remain invariant.

## Output fidelity

`SimulationConfig.output_mode` has three values:

* `forensic`: full event, observation, state-delta, and synthetic-record data;
* `ensemble`: compact event summaries, checkpoints, and recorded evidence;
* `calibration`: compact counters and checkpoints only.

The process RNG calls are made in every mode. `output-benchmark` compares final
scientific summaries under matched seeds and reports runtime, peak memory, and
trajectory equivalence.

## Representative agents and households

Population-facing thresholds use represented weight. Sampled nodes are
representative agents, and a household is a **household archetype / kin-resource
cell**, not a literal household of the represented population. The
`representative-audit` command checks membership, recruitment, migration,
election, casualty, and organization-transition accounting in represented
units.

## Network and language experiments

`topology-ablation` compares the generated graph, degree-preserving rewiring,
and random-mixing attributes while preserving the degree sequence. It reports
control, diffusion/behavior, recruitment, onset, information, contacts,
casualties, and graph diagnostics.

`language-factorial` runs all eight combinations of topology, detection, and
fusion language channels over matched seeds and returns main and pairwise
interaction effects.

## Global accounting

Each stock-boundary change is classified as `internal_transfer`, `production`,
`consumption`, `destruction`, `external_inflow`, or `external_outflow`.
`WorldState.global_accounting_diagnostics()` reports per-stock residuals,
population residuals, gross/net flow summaries, and a closed total
reconciliation. Any non-zero residual is an invariant failure.

## Scaling, sensitivity, and recovery

`resolution-audit` supports the 25k/75k/250k resolution ladder with multiple
seeds and standardized mean differences. Morris and Saltelli-style routines
report stochastic repetitions, standard errors, interactions, and finite-sample
warnings. `parameter_recovery_ensemble` generates synthetic **recorded**
evidence and reports bias, RMSE, rank correlation, boundary hits, and failure
rates; interval coverage is explicitly unavailable for point estimates.

## First-paper boundary

`paper-spec` emits the locality-week experiment contract for physical control,
logistics, information, and social response, including construct
correspondence, measurement model, holdouts, competitors, ablations, and
falsification criteria. No empirical data are bundled. The readiness report
therefore does not claim empirical validation.

## Final report

`readiness-report` runs the bounded core battery and writes exact numerics,
runtime, closure status, open empirical requirements, and separate methods-
paper versus substantive-paper readiness scores. Pass `--full` to run the
powered resolution, sensitivity, and recovery batteries as well.
