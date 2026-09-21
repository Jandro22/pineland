# Subsystem evidence index

This is a mechanical index of test and documentation evidence, not a maturity score.
Counts show where executable verification effort exists; they do not establish
historical validity, realism, or correctness by themselves.

Current repository baseline: **734 Python test functions across 110 test files** and
**96 Rust test cases across 27 Rust source files**.

| Subsystem | Role | Selected Python tests | Selected Rust tests | Primary evidence |
|---|---|---:|---:|---|
| Runtime, determinism, and reproducibility | Research-load-bearing infrastructure | 45 | 28 | [rust/README.md](../rust/README.md); [docs/repository-layout.md](repository-layout.md) |
| Physical presence and territorial control | Research-load-bearing mechanism | 33 | 0 | [docs/physical-model.md](physical-model.md); [docs/odd-model.md](odd-model.md) |
| Logistics, readiness, and command | Research-load-bearing mechanism | 44 | 2 | [docs/logistics-model.md](logistics-model.md); [docs/resource-semantics.md](resource-semantics.md) |
| Organization ecology and reproduction | Research-load-bearing in General Theory v1 | 97 | 8 | [docs/organization-ecology.md](organization-ecology.md); [studies/research_program/general_theory_v1/README.md](../studies/research_program/general_theory_v1/README.md) |
| Information, observations, and actor beliefs | Research-load-bearing mechanism | 52 | 1 | [docs/information-model.md](information-model.md); [docs/social-network-semantics.md](social-network-semantics.md); [docs/research-readiness.md](research-readiness.md) |
| State estimation and inference | Research-load-bearing inference layer | 50 | 9 | [docs/state-estimation.md](state-estimation.md); [docs/research-v1.md](research-v1.md) |
| Organized action and combat | Implemented and used by active studies | 52 | 18 | [docs/action-model.md](action-model.md); [docs/combat-model.md](combat-model.md) |
| Political order and governance | Implemented; secondary to the first-paper inference program | 11 | 0 | [docs/political-order.md](political-order.md) |
| Foreign affairs and partner-force support | Implemented; integrated Partner-Force Stage 4 completed | 35 | 28 | [docs/foreign-affairs.md](foreign-affairs.md); [studies/research_program/general_theory_v1/partner_force_autonomy/README.md](../studies/research_program/general_theory_v1/partner_force_autonomy/README.md); [studies/research_program/general_theory_v1/partner_force_autonomy/STAGE4_RESULTS_INTERPRETATION_2026-09-20.md](../studies/research_program/general_theory_v1/partner_force_autonomy/STAGE4_RESULTS_INTERPRETATION_2026-09-20.md) |
| Peace process | Implemented; currently peripheral | 16 | 0 | [docs/peace-process.md](peace-process.md) |
| Historical measurement and case transport | Active external-validation layer | 51 | 0 | [docs/empirical-benchmarking.md](empirical-benchmarking.md); [docs/research-validation.md](research-validation.md) |
| HPC and distributed execution | Research-load-bearing execution infrastructure | 34 | 6 | [rust/hpc/ARC.md](../rust/hpc/ARC.md); [rust/README.md](../rust/README.md) |

## Selected executable evidence

The table intentionally uses selected test files rather than assigning every
cross-cutting test to exactly one subsystem. A test may appear in multiple rows
when the same invariant crosses subsystem boundaries.

### Runtime, determinism, and reproducibility

Python:
- [tests/test_reproducibility.py](../tests/test_reproducibility.py) - 12 test functions
- [tests/test_scheduler.py](../tests/test_scheduler.py) - 1 test functions
- [tests/test_timebase.py](../tests/test_timebase.py) - 3 test functions
- [tests/test_simulation.py](../tests/test_simulation.py) - 12 test functions
- [tests/test_io.py](../tests/test_io.py) - 1 test functions
- [tests/test_archive_stream.py](../tests/test_archive_stream.py) - 2 test functions
- [tests/test_native_ensemble.py](../tests/test_native_ensemble.py) - 13 test functions
- [tests/test_native_kernels.py](../tests/test_native_kernels.py) - 1 test functions

Rust:
- [rust/pineland-core/src/checkpoint.rs](../rust/pineland-core/src/checkpoint.rs) - 5 test cases
- [rust/pineland-core/src/config.rs](../rust/pineland-core/src/config.rs) - 9 test cases
- [rust/pineland-core/src/json.rs](../rust/pineland-core/src/json.rs) - 2 test cases
- [rust/pineland-core/src/rng.rs](../rust/pineland-core/src/rng.rs) - 8 test cases
- [rust/pineland-core/src/scheduler.rs](../rust/pineland-core/src/scheduler.rs) - 2 test cases
- [rust/pineland-core/src/sha256.rs](../rust/pineland-core/src/sha256.rs) - 1 test cases
- [rust/pineland-core/src/state.rs](../rust/pineland-core/src/state.rs) - 1 test cases

### Physical presence and territorial control

Python:
- [tests/test_physical.py](../tests/test_physical.py) - 10 test functions
- [tests/test_role_capacity_resolution.py](../tests/test_role_capacity_resolution.py) - 5 test functions
- [tests/test_scaling.py](../tests/test_scaling.py) - 2 test functions
- [tests/test_weighted_representative_semantics.py](../tests/test_weighted_representative_semantics.py) - 11 test functions
- [tests/test_resource_semantics.py](../tests/test_resource_semantics.py) - 5 test functions

### Logistics, readiness, and command

Python:
- [tests/test_logistics.py](../tests/test_logistics.py) - 15 test functions
- [tests/test_causal_integrity.py](../tests/test_causal_integrity.py) - 6 test functions
- [tests/test_armed_formation_operational_semantics.py](../tests/test_armed_formation_operational_semantics.py) - 18 test functions
- [tests/test_resource_semantics.py](../tests/test_resource_semantics.py) - 5 test functions

Rust:
- [rust/pineland-model/src/logistics.rs](../rust/pineland-model/src/logistics.rs) - 1 test cases
- [rust/pineland-model/src/movement.rs](../rust/pineland-model/src/movement.rs) - 1 test cases

### Organization ecology and reproduction

Python:
- [tests/test_organization_ecology.py](../tests/test_organization_ecology.py) - 33 test functions
- [tests/test_insurgent_reproduction.py](../tests/test_insurgent_reproduction.py) - 19 test functions
- [tests/test_insurgent_reproduction_identification.py](../tests/test_insurgent_reproduction_identification.py) - 6 test functions
- [tests/test_competitive_local_renewal.py](../tests/test_competitive_local_renewal.py) - 9 test functions
- [tests/test_local_foothold_state.py](../tests/test_local_foothold_state.py) - 3 test functions
- [tests/test_local_force_critical_mass.py](../tests/test_local_force_critical_mass.py) - 6 test functions
- [tests/test_locality_activation_genealogy.py](../tests/test_locality_activation_genealogy.py) - 10 test functions
- [tests/test_locality_reproduction_ensemble.py](../tests/test_locality_reproduction_ensemble.py) - 1 test functions
- [tests/test_franchise_ecology.py](../tests/test_franchise_ecology.py) - 10 test functions

Rust:
- [rust/pineland-model/src/state_regeneration.rs](../rust/pineland-model/src/state_regeneration.rs) - 8 test cases

### Information, observations, and actor beliefs

Python:
- [tests/test_information.py](../tests/test_information.py) - 12 test functions
- [tests/test_compact_information_state.py](../tests/test_compact_information_state.py) - 9 test functions
- [tests/test_measurement.py](../tests/test_measurement.py) - 6 test functions
- [tests/test_truth_firewall.py](../tests/test_truth_firewall.py) - 10 test functions
- [tests/test_social_exposure_provenance.py](../tests/test_social_exposure_provenance.py) - 7 test functions
- [tests/test_networks.py](../tests/test_networks.py) - 8 test functions

Rust:
- [rust/pineland-model/src/information.rs](../rust/pineland-model/src/information.rs) - 1 test cases

### State estimation and inference

Python:
- [tests/test_state_estimation.py](../tests/test_state_estimation.py) - 14 test functions
- [tests/test_recovery.py](../tests/test_recovery.py) - 18 test functions
- [tests/test_reproduction_identification_recovery.py](../tests/test_reproduction_identification_recovery.py) - 1 test functions
- [tests/test_identifiability_triage.py](../tests/test_identifiability_triage.py) - 4 test functions
- [tests/test_afghanistan_filtered_state_estimation.py](../tests/test_afghanistan_filtered_state_estimation.py) - 13 test functions

Rust:
- [rust/pineland-inference/src/filter.rs](../rust/pineland-inference/src/filter.rs) - 4 test cases
- [rust/pineland-inference/src/forecast.rs](../rust/pineland-inference/src/forecast.rs) - 1 test cases
- [rust/pineland-inference/src/parallel.rs](../rust/pineland-inference/src/parallel.rs) - 1 test cases
- [rust/pineland-inference/src/resampling.rs](../rust/pineland-inference/src/resampling.rs) - 3 test cases

### Organized action and combat

Python:
- [tests/test_action_model.py](../tests/test_action_model.py) - 24 test functions
- [tests/test_combat.py](../tests/test_combat.py) - 11 test functions
- [tests/test_contact_pipeline.py](../tests/test_contact_pipeline.py) - 9 test functions
- [tests/test_event_support_architecture.py](../tests/test_event_support_architecture.py) - 2 test functions
- [tests/test_experimental_action_support.py](../tests/test_experimental_action_support.py) - 3 test functions
- [tests/test_insurgent_portfolio_synthetic_validation.py](../tests/test_insurgent_portfolio_synthetic_validation.py) - 3 test functions

Rust:
- [rust/pineland-model/src/lib.rs](../rust/pineland-model/src/lib.rs) - 18 test cases

### Political order and governance

Python:
- [tests/test_political_order.py](../tests/test_political_order.py) - 11 test functions

### Foreign affairs and partner-force support

Python:
- [tests/test_foreign_affairs.py](../tests/test_foreign_affairs.py) - 16 test functions
- [tests/test_arc_hpc_campaign.py](../tests/test_arc_hpc_campaign.py) - 17 test functions
- [tests/test_stage4_compact_evidence.py](../tests/test_stage4_compact_evidence.py) - 2 test functions

Rust:
- [rust/pineland-model/src/lib.rs](../rust/pineland-model/src/lib.rs) - 18 test cases
- [rust/pineland-model/src/logistics.rs](../rust/pineland-model/src/logistics.rs) - 1 test cases
- [rust/pineland-model/src/movement.rs](../rust/pineland-model/src/movement.rs) - 1 test cases
- [rust/pineland-model/src/state_regeneration.rs](../rust/pineland-model/src/state_regeneration.rs) - 8 test cases

### Peace process

Python:
- [tests/test_peace_process.py](../tests/test_peace_process.py) - 16 test functions

### Historical measurement and case transport

Python:
- [tests/test_empirical.py](../tests/test_empirical.py) - 8 test functions
- [tests/test_empirical_geography.py](../tests/test_empirical_geography.py) - 11 test functions
- [tests/test_historical.py](../tests/test_historical.py) - 5 test functions
- [tests/test_historical_database_v2.py](../tests/test_historical_database_v2.py) - 6 test functions
- [tests/test_case_readiness.py](../tests/test_case_readiness.py) - 1 test functions
- [tests/test_comparative_case_contract.py](../tests/test_comparative_case_contract.py) - 2 test functions
- [tests/test_comparative_control_presence_panels.py](../tests/test_comparative_control_presence_panels.py) - 3 test functions
- [tests/test_afghanistan_historical_inputs.py](../tests/test_afghanistan_historical_inputs.py) - 9 test functions
- [tests/test_afghanistan_transfer_gate.py](../tests/test_afghanistan_transfer_gate.py) - 4 test functions
- [tests/test_nigeria_2014_external_holdout_design.py](../tests/test_nigeria_2014_external_holdout_design.py) - 2 test functions

### HPC and distributed execution

Python:
- [tests/test_arc_hpc_campaign.py](../tests/test_arc_hpc_campaign.py) - 17 test functions
- [tests/test_execution_scaling.py](../tests/test_execution_scaling.py) - 17 test functions

Rust:
- [rust/pineland-hpc/src/distributed.rs](../rust/pineland-hpc/src/distributed.rs) - 1 test cases
- [rust/pineland-hpc/src/distribution.rs](../rust/pineland-hpc/src/distribution.rs) - 2 test cases
- [rust/pineland-hpc/src/migration.rs](../rust/pineland-hpc/src/migration.rs) - 2 test cases
- [rust/pineland-hpc/src/mpi.rs](../rust/pineland-hpc/src/mpi.rs) - 1 test cases

## Interpretation

Three distinct questions remain separate:

1. **Implementation evidence:** does executable code and regression coverage exist?
2. **Synthetic scientific evidence:** does the mechanism or inference method survive
   known-truth, sensitivity, falsification, or holdout tests?
3. **Historical validity:** can the corresponding construct be measured and defended
   against real-world evidence?

The existence of many tests is evidence for engineering attention, not a substitute
for the latter two questions.

Regenerate this page with:

    python scripts/build_subsystem_evidence_index.py
