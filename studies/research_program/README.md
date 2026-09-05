# Pineland comparative research program

This directory converts the moonshot roadmap into enforceable research
decisions. It does not claim that the full comparative program has already
been executed.

The scientific core is frozen as `pineland-core-transfer-v3` by the live-tree
reproducibility certificate referenced in `core_freeze.json`.
The earlier settled-tree certificate is retained as an archive and is not the
authoritative provenance for new transfer runs.
Study code, case inputs, observation models, and reports remain outside that
core. A live model-hash mismatch is a hard stop for transfer claims: classify
the drift, restore the certified model or document a general defect under the
change rule, and then issue a superseding certificate and freeze record.

`case_ladder.json` fixes the order and promotion gates. Nepal is preserved as
a falsification result. Afghanistan is the first transfer case; its v2 target
failure is archived and requires v3 revalidation before current-core claims.
Colombia,
Iraq, and Vietnam are named future tests, not completed evidence.

`mechanism_registry.json` makes competitive local reproduction and `R_I`
explicitly provisional. It also requires reduced/statistical competitors and
the full multidimensional COIN outcome vector before policy claims.

`coin_interventions.json` is the preregistered COIN design. It fixes nine
intervention contrasts, their primary and harm outcomes, and falsifiers before
any intervention runs. `scripts/validate_coin_contract.py` checks that the
design still forbids holdout calibration and violence-only optimization.

`nepal_mechanism_evidence.json` is a generated, descriptive ablation matrix;
it is deliberately marked as pending cross-case replication and is not a
general mechanism claim. Rebuild it with
`scripts/build_mechanism_evidence.py` after any approved Nepal ablation update.

`identifiability_plan.json` and its generated `identifiability_triage.json`
replace any notion of 211-parameter global calibration with six questions that
activate only 5–7 parameters each. Every question is blocked on synthetic
estimand recovery. `spatial_reproduction_diagnostic_contract.json` fixes the
persistence, adjacency, movement, recruitment-locality, sanctuary, and
control-feedback tests before further case fitting.

Spatial reproduction now has an executable **statistical identification gate**
that is intentionally separate from case scoring. Run
`scripts/validate_reproduction_identification.py`; its generated
`reproduction_identification_recovery.json` exercises homogeneous,
spatial-frailty, degree-confounded, and serial-common-shock nulls; known
propagation and persistence; combined persistence/propagation; neighbor-dose
response; topology and temporal placebos; factorial mechanism/path ablation;
multi-parent attribution; competing/background activation; relocation versus
net reproduction; repeated episodes; censoring/IPW recovery; and clustered
uncertainty. The recovery artifact records `historical_outcomes_used=false`
and `empirical_parameter_fitting=false`.

Passing that statistical gate does **not** promote the mechanism-level
identifiability questions in `identifiability_triage.json`: Pineland-specific
matched-world tests must still distinguish, for example, presence memory from
contact recurrence and movement from social/recruitment propagation while
holding stocks and accounting fixed. The case-facing
`diagnose_spatial_reproduction.py` therefore labels same-area renewal and
neighbor risk differences as descriptive, exposes episode duration,
reactivation, dose response, and the future-neighbor temporal placebo, and
never licenses a causal contagion claim by itself.

`scripts/estimate_insurgent_reproduction.py` now makes a four-part decomposition
the primary estimand: local endogenous ignition, parent-attributed cross-local
colonization, foothold deepening into fielded force, and post-establishment
survival. Each component has its own explicit risk set and denominator. A
durable cross-local yield is reported only as a secondary product of the last
three components; scalar `R_I` is retained solely as a nested compatibility
output. The estimator still supports fractional multi-parent edges,
gross-versus-net reproduction, censoring/IPW, and dependence-aware uncertainty.
`insurgent_reproduction_decomposition.json` demonstrates the contract on an
observation-only genealogy with no historical outcomes or fitting.

`trace_locality_activation_genealogy.py` now assigns every non-root activation
to a frozen parentage ontology: local spontaneous ignition, social-network
seeding, migrating-member seeding, formation-recruitment seeding, formation
relocation, organizational split/offspring, sanctuary/external seeding, or
unresolved. Unknown provenance remains unresolved rather than being inferred
from adjacency or a contemporary social path.

`franchise_consequence_symmetry.json` is a matched-world negative-result audit.
Holding residence, membership mass, organization traits, language, geography,
and seed fixed while changing member home origins identifies a direct rootedness
effect on recruitment, but not on information, reporting, concealment,
extraction, survival, defection, backlash, or effective control. The congruence
measurement operator is actor-kind neutral across insurgent, government,
military, police, foreign, party, and civic organizations, but transition-level
institutional symmetry remains unestablished. No missing mechanism was added.

`spatial_factorial_experiment_contract.json` preregisters the next bounded
synthetic test: a matched-seed 2x2 factorial separating presence-memory from
geographic-neighbor restriction. It is intentionally not historical evidence
and cannot license a core change until synthetic estimands are recovered with
stable source hashes.

`scripts/run_spatial_factorial_pilot.py` implements that design in the study
layer. Its default 14-day, one-seed-per-cell run is a bounded execution and
provenance check; it fails closed if the model source changes during a cell.
The resulting `spatial_factorial_pilot.json` and companion manifest are
diagnostic only: the pilot is shorter than the 28-day estimand, does not run
synthetic truth recovery, and therefore leaves the scientific acceptance gate
false. The explicit `--full` ensemble also refuses to launch while the active
core certificate mismatches the live source; use it only after the pilot,
source-hash review, and any required superseding freeze are complete.

`spatial_factorial_pilot_assessment.json` records the current design failure:
the matched cells are reproducible, but zero contacts and zero adjacent
activations leave the mechanism estimands unexercised. A future challenge
initial condition must be preregistered separately; this null diagnostic is
not pooled with transfer evidence.

The same bounded pilot was rerun on the latest `c2afb8…` live snapshot as
`spatial_factorial_pilot_c2afb.json`; it reproduces the zero-contact and
zero-adjacent-activation limitation while showing that the memory treatment
changes memory stock without changing short-horizon renewal.

That separate preregistration is now
`spatial_factorial_contact_challenge_contract.json`. It fixes a small,
contact-enriched synthetic micro-world with a declared focal pair, forced
detection, no-gate contact supply, and no organization-ecology turnover. It is
an isolation test for the contact/presence pathway, not a replacement for the
comparative factorial or a historical result; its one-seed adequacy pilot is
recorded separately below.

The adequacy runs are recorded in
`spatial_factorial_contact_challenge_pilot.json` and
`spatial_factorial_contact_challenge_pilot_seed8812.json`, with the combined
assessment in `spatial_factorial_contact_challenge_pilot_assessment.json`.
Both seeds exercise latent focal contacts in every cell and recover the
presence-memory contrast, but they use different source snapshots, remain
below the eight-seed acceptance gate, and do not identify adjacent activation.
The same challenge was also rerun on the current `c2afb8…` snapshot as
`spatial_factorial_contact_challenge_pilot_c2afb.json`; it reproduces the
pathway result but is still a one-seed adequacy check.

The bounded eight-seed replication is now recorded in
`contact_challenge_eight_seed_replication.json`, with provenance in
`contact_challenge_eight_seed_replication_manifest.json`. It covers 32 cells
(eight seeds across the four preregistered conditions), exercises at least one
latent contact in every cell, and produces a positive insurgent
presence-memory contrast in every seed (mean difference 2.151 memory units).
Integrity and the synthetic acceptance gate pass. The artifact is explicitly
synthetic-only and its live source remains uncertified, so it supports the
conjunctive pathway constraint but cannot satisfy a historical case cell or
license a superseding core freeze.

Both pilot families are snapshot-bound artifacts, not current-core transfer
evidence. Their manifests record the source hashes used at execution; the live
source has changed since those runs and remains uncertified.

`spatial_reproduction_identification_recovery.json` records the data-free
identification battery, with its content-addressed companion manifest. All
eleven gates pass: known propagation and persistence are recovered, while
spatial-frailty, degree, common-shock, and topology-placebo nulls are not
falsely promoted to causal evidence.

`locality_activation_genealogy_pilot.json` is a short observation-only pilot
using the live simulator. It found 21 activation episodes, 18 of them initial
conditions, with only one relocation and one local recruitment episode; its
single parent edge is insufficient to identify historical `R_I`.

The freeze-evidence audit is content-addressed and fails closed. Legacy Nepal
artifacts are archival evidence: their missing original commit, model/config,
registry, case, split, environment, execution-mode, and output-schema fields
are never reconstructed from the current checkout.

`core_change_classification_ledger.json` records the evidence still required
before the broad live-core repair can receive a superseding certificate. A
stable hash alone is insufficient: each repair must have a data-free failure,
causal explanation, and impact assessment against completed cases.

`current_core_snapshot.json` records the latest bounded live-source check. It
is stable across the recorded samples but explicitly not a certificate.

Two construct-level current-core preflights now bind the settled live hash
(`12ce71b3…` model, `a8ee32d4…` tracked diff):
`studies/nepal_2001_2006/results/post_structural_repair/structural_repair_manifest.json`
passes Nepal geometry, population, force-structure, and supply invariants, and
`afghanistan_initialization_preflight.json` passes the Afghanistan stock,
geography, sanctuary, and supply initialization gate. Both use no historical
outcome fitting and are explicitly not transfer results; full historical
impact assessment remains required before a superseding certificate.

`afghanistan_current_core_smoke_preflight.json` adds a single 30-day
current-core impact diagnostic: 2,522 events were processed, but latent and
recorded contacts were both zero. This preserves the contact-opportunity
bottleneck as a current-source constraint without turning a smoke run into a
historical transfer claim.

An earlier content-addressed snapshot extended the same diagnostic to 365 days in
`afghanistan_current_core_year_preflight.json`: 30,386 events, 5 latent
contacts, 2 recorded contacts, and one active province-week. This distinguishes
a rare contact hazard from an impossible contact pathway while remaining a
single-strength smoke diagnostic, not a transfer result.

The earlier snapshot's `afghanistan_contact_hazard_sensitivity.json` preregisters and runs four
90-day contact-rate multipliers. Mean hazard increases monotonically; contacts
remain zero at 0.5×–2× and appear at 4×. This isolates a hazard-limited
snapshot-bound bottleneck without selecting a multiplier from historical fit;
the long-horizon artifact is retained for provenance and is not treated as
current after subsequent source edits.

`nepal_current_core_smoke_preflight.json` provides the matched Nepal check:
the latest settled source produced zero latent and recorded contacts in 30 days,
with population conservation and invariants passing. An earlier Nepal snapshot
produced one latent and one recorded contact, but that contrast is retained as
snapshot-bound; neither smoke run is a transfer estimate.

`contact_challenge_current_core_pilot.json` reruns the four-cell contact
challenge on the settled live source. Every cell has one latent contact, and
formation-memory stock exceeds patrol-only stock in the current-policy pair.
The pilot remains below the preregistered scientific gate by design and is
synthetic pathway evidence only.

`theory_extraction_protocol.json` fixes the candidate reproduction cycle and
the cross-case survival/falsification rules. All mechanism statuses remain
`unresolved` until those rules are met.

`theory_status_matrix.json` is the current evidence ledger: it separates
synthetic constraints, unresolved mechanisms, policy candidates, falsifiers,
and the exact evidence required before any claim can be promoted to a stable
general theory.

`comparative_theory_promotion_matrix.json` binds each candidate claim to every
case in the ladder. It marks legacy or data-construction cells as ineligible,
requires simpler competitors and frozen holdouts, and fails closed while no
case has both current-core provenance and identified historical observations.
The audit checks this matrix so synthetic pathway recovery cannot silently
become a cross-case theory claim.

`historical_reproduction_signature_benchmark.json` is the next low-cost,
observation-only comparison. Its builder harmonizes the currently available
Nepal and Afghanistan renewal/adjacency summaries, preserves denominators and
missingness, and emits explicit null cells for Colombia, Iraq, and Vietnam
until their processed panels are ready. Temporal, topology, and reporting-
persistence placebos are required before any signature can support a causal
reproduction claim; the benchmark never fits parameters or changes the core.

`event_only_spatial_signature_diagnostic.json` extends the descriptive screen
to the available Colombia and Iraq UCDP event panels. It builds complete
GADM-unit by observed-month grids, computes renewal and adjacency-proxy rates,
and reports a temporal-lead placebo plus a topology-label-shuffle null. The
result remains violence-only: missing actor identity, control/presence joins,
and case measurement models keep it outside transfer or theory-promotion
evidence.

`harmonized_historical_event_signatures.json` applies the same monthly event
definition to Nepal, Afghanistan, Colombia, and Iraq. It reports pooled and
case-unweighted summaries without silently mixing case frequencies or imputing
unobserved actors. The reverse-time placebo leaves no robust cross-case
directional margin, so the result is a negative constraint on adjacency-as-
propagation, not support for a general diffusion law.
The topology null relabels both endpoints of each edge, preserving graph
symmetry and degree sequence; it is an isomorphic label null rather than an
arbitrary neighbor-label remap. Interpretation remains limited by case-native
event definitions, incomplete location assignment, and the non-causal
conditioning of the reverse-time diagnostic.
The harmonized artifact also reports one-month sensitivity by case-native event
stratum for Nepal and Afghanistan. Renewal and adjacency vary substantially by
stratum, reinforcing that pooled violence presence is not a common insurgent
outcome.
`historical_assignment_sensitivity.json` separately reports raw location
coverage: 99.96% of Nepal rows meet the district rule versus 41.54% of
Afghanistan rows under the high-confidence district rule. The unassigned
Afghanistan rows remain missing rather than being interpreted as zero activity.

The prospective SIGAR ordinal observation operator has a separate synthetic
recovery artifact with 99.24% accuracy. It is a measurement-contract check only;
it does not validate latent control dynamics or historical transfer.

`historical_signature_competitor_benchmark.json` compares four simple,
training-only predictors on deterministic temporal holdouts: a global base
rate, local renewal, neighbor exposure, and their combination. Local renewal
improves the violence-proxy Brier score in all four cases, while the
neighbor-only lift is weak in Colombia and Iraq. This supports prioritizing
local renewal as a candidate predictor, but it is not causal evidence and does
not replace preregistered frozen holdouts or control/joint-outcome validation.
The same artifact now includes three blocked rolling-origin sensitivity windows
(50%, 60%, and 70% training prefixes); local renewal remains positive in every
window and case, while the combined local-plus-neighbor model is positive in all
windows but adds little beyond local renewal in several cases. These windows are
exploratory and do not license a general diffusion claim.
Nepal's weekly source rows are aggregated to months, so source split labels are
not treated as a frozen holdout; this is a chronology check, not a preregistered
evaluation.
The same competitor screen within event strata preserves negative results:
Afghanistan's Taliban state-based stratum retains positive local lift, while
faction, government one-sided, and external strata are slightly negative. This
is evidence that the pooled lift is outcome-definition-sensitive, not a general
local-reproduction law.

`actor_continuity_diagnostic.json` tests whether monthly renewal and adjacency
preserve the same recorded UCDP dyad in Nepal and Afghanistan. Dyad-consistent
renewal is substantial, but dyad-consistent adjacency does not show a robust
forward-time margin over its reverse-time placebo. Dyad labels are retained as
identity proxies only; no organization genealogy or parent-attributed
reproduction claim is licensed.

`historical_signature_artifact_manifest.json` content-addresses the four
historical diagnostics and their builder scripts, including raw location-
assignment coverage. The program audit verifies those hashes before accepting
the evidence ledger.

`timebase_repair_evidence.json` records the one currently classified general
defect in the moving core: fixed per-event probabilities were not invariant to
scheduler refinement. The data-free counterexample and composition contract
justify the repair, while completed-case impact and a settled release hash
remain required before any superseding freeze.

`insurgent_portfolio_synthetic_validation.json` adds a separate data-free
structural check: the frontier/foothold/stronghold/exploration portfolio has
the declared simplex, route-risk, sanctuary, and stage-separation properties.
It is not a historical movement or reproduction result.

`outcome_measurement_contract.json` keeps violence, control, harm, capacity,
regeneration, dependence, and recurrence as separate measured outcomes. It
forbids substituting violence for control and requires explicit missingness
rather than silent cross-outcome imputation.

`moonshot_checklist.json` is the completion ledger. It deliberately separates
software certification from scientific completion: Afghanistan has a preserved
legacy failed first transfer awaiting live-core revalidation, the comparative cases remain in data construction,
and COIN efficacy is not licensed.

The three future case directories (`colombia_1984_2016`, `iraq_2003_2011`,
and `vietnam_1955_1975`) contain preregistration-first contracts only. Their
empty data and results directories are intentional: no case is promoted by a
scaffold alone.

`scripts/validate_case_readiness.py studies/colombia_1984_2016` fails closed
until sources are acquired and hashed, construct measurements and frozen
holdouts exist, and uncertainty artifacts are supplied; the same guard applies
to each future case.

Run the audit from the repository root:

```powershell
$env:PYTHONPATH = "src"
python studies/research_program/scripts/audit_program.py
```

The audit intentionally reports both calibration and COIN inference as
unlicensed at the current stage.

The comparative observation builder freezes source- and output-hashed panels
for Colombia, Iraq, and Vietnam under `data/processed/comparative_control_presence/`.
Comparability is limited to schema and provenance: undated Colombian points
remain undated, Iraq remains a Rusafa-only anchor, and Vietnam HES ratings
remain raw ordinal categories. Harmonization alone grants no run license.

`predictive_competition_gate.json` prevents a premature “beats simpler models”
claim. Candidate and six named alternatives must predict identical held-out
rows. The gate currently fails because candidate predictions and complete
covariate/crosswalk mappings do not exist; COIN experiments remain unauthorized.
