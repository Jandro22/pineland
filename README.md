# Pineland COIN-SIM

Version 0.13 adds a belief-based, budget-constrained organized-action layer
that separates persistent organizational capacity from action choice, execution,
latent events, and historical recording. Armed formation contact remains one
event channel rather than defining the full support of organized violence.
See `docs/action-model.md`.

Version 0.12 added an empirical-data boundary, provenance-preserving case
packages, measurement-error-aware targets, fragmentation forensics, synthetic
parameter recovery, and question-specific parameter registries. See
`docs/empirical-benchmarking.md`.

The `v0.5` baseline adds spatial stochastic armed engagements,
attrition, cohesion failure, disengagement, conserved combat expenditure,
civilian-harm observations, perceived momentum, and logistics-routed
reinforcement. See [the combat model](docs/combat-model.md).

The `v0.6` development line adds endogenous armed-organization ecology:
probabilistic onset, organizational capital, recruitment composition,
leadership, adaptation, fragmentation, merger, collapse, and reconstructable
genealogy. See [the organization ecology model](docs/organization-ecology.md).

The `v0.7` development line adds political institutions, local party branches,
elections, distinct state/government/party legitimacy, conserved patronage and
corruption flows, local policy distortion, elite brokerage, institutional
capacity, and peaceful political alternatives. See
[the political-order model](docs/political-order.md).

The `v0.8` development line adds neighboring states, first-class borders,
cross-border migration and diaspora, decomposed external support, sanctuary,
foreign formations, interpreters, imperfect foreign beliefs, host dependence,
capacity transfer/crowding-out, foreign domestic politics, rivalry, and routed
withdrawal. See [the foreign-affairs model](docs/foreign-affairs.md).

Pineland COIN-SIM is a research-oriented, partially observed agent-based simulation of insurgency, counterinsurgency, governance, mobility, information, and multidimensional territorial control. The current v0.13.0 development line implements the runtime spine, social and physical structure, logistics, persistent organization ecology, belief-based organized action, spatial combat, political order, foreign affairs, peace processes, and explicit detection/information fusion. It remains a research prototype; numeric priors are not calibrated findings.

The current engine is intentionally dependency-light and transparent. Every important control change is written to a causal ledger, actors act on noisy estimates rather than world truth, and population agents carry represented-population weights. Latent process transitions and synthetic historical recording use separate deterministic per-event-type RNG namespaces, so recording/output settings do not advance the scientific transition streams. Version 0.12 also records cross-stock transactions and sparse state deltas, executes an explicitly unrecorded burn-in when configured, uses spatially generated locality links, and exposes adversarial validation batteries for firewall, scheduler, conservation, recording, resolution, sensitivity, recovery, and foreign-withdrawal diagnostics.

The implementation-synchronized ODD description and state/observation taxonomy
are in [`docs/odd-model.md`](docs/odd-model.md). In particular, structural
assumptions, engineering priors, case inputs, calibrated parameters, latent
states, actor beliefs, and recorded observables are treated as different
scientific objects rather than interchangeable "parameters."

Research-readiness commands now provide a decision-level truth-firewall battery,
forensic/ensemble/calibration output benchmarking, a representative-agent and
household audit, degree-preserving topology ablations, an eight-cell language
factorial, globally reconciled stock accounting, multi-resolution and powered
sensitivity/recovery diagnostics, and a data-free first-paper contract. See
[the research-readiness contract](docs/research-readiness.md).

## Implemented foundation

- Default 17-district synthetic Pineland registry with configurable localities, plus empirical geography schemas 1.0.0–3.0.0 for case-supplied districts/containers, localities, hierarchy, population, coordinates, adjacency, and physical covariates.
- Weighted people, explicit households, individual multilingual proficiency, identities, preferences, grievance, fear, efficacy, trust, home, and residence.
- Explicit social communities and sparse multiplex household, community, and cross-community bridge edges.
- Language-aware communication weights, network exposure, civilian public-behavior choice, and community-to-locality aggregation.
- Locality-internal physical graphs, microzones, fixed posts, belief-routed patrol paths, presence memory, and response-time fields.
- Population-weighted upward aggregation from microzone physical control to locality physical control.
- Timed formation movement orders over locality paths, constrained by terrain, infrastructure, mobility, command latency, and supply.
- Conserved supply sources, shipments, losses, presence/activity consumption, readiness degradation/recovery, and availability.
- Command graphs with explicit reliability and communications latency.
- Assigned versus effective available strength and locality-level control-cost/sustainability metrics.
- First-class heterogeneous observations from patrols, fixed posts, civilians, social networks, administrative channels, organization members, political elites, interpreters, and contact events.
- Age-decaying confidence-weighted fusion with source trust, language comprehension, corroboration, contradiction, and local-versus-headquarters knowledge.
- Delayed and unreliable observation propagation through command graphs, with explicit information age, detection counts, and analyst-only belief-error diagnostics.
- Government, military, police, parties, an optional insurgent organization, and armed formations.
- Seven-dimensional control vectors for formal, physical, administrative, legal, fiscal, social, and expected control.
- Connected locality graph with terrain-friction travel costs.
- Asynchronous priority event scheduler with terrain-sensitive formation movement/patrol, information collection/fusion, civilian mobility, recruitment, governance, economy, belief-based organized action, combat, and checkpoint processes.
- Budget-constrained choice among waiting, armed confrontation, nonfielded human-target violence, asset violence, and nonviolent coercion; execution checks hidden target truth only after planning.
- Actor-specific evidence-based beliefs and a separate biased synthetic historical record.
- Conserved represented population, bounded state checks, stock checks, deterministic checkpoints, and causal provenance.
- Matched-seed scenario forks, ensemble summaries, locality causal decomposition, control velocity, and district aggregation.
- Subsystem-specific deterministic random streams, JSON scenario configuration, command-line entry point, and machine-readable output products.

## Quick start

### Pineland Native v1

The standalone Rust runtime is under [`rust/`](rust/README.md). It owns the
simulation and inference hot path and does not require Python:

```powershell
cargo test --workspace --manifest-path rust/Cargo.toml
cargo run --release --locked --manifest-path rust/Cargo.toml -p pineland-cli -- run scenarios/baseline.json --seed 20011126 --days 7 --output outputs/native-baseline
```

The native CLI also provides `validate-config`, `generate`, `resume`,
`filter`, `forecast`, `inspect-checkpoint`, `hash-state`, `benchmark`, and
`version`. See [`rust/BUILD.md`](rust/BUILD.md) and the checked-in SLURM
templates under [`rust/hpc/`](rust/hpc/) for portable and Owl execution.

Use Python 3.11 or newer. The package has no runtime dependencies.

```powershell
python -m pip install -e .
pineland-sim init scenarios/baseline.json
pineland-sim run --config scenarios/baseline.json --output outputs/baseline
```

For a fast smoke run:

```powershell
pineland-sim run --agents 1000 --days 30 --output outputs/smoke
```

Add an opt-in social graph snapshot when debugging selected agents or communities:

```powershell
pineland-sim run --agents 1000 --days 30 --output outputs/smoke `
  --network-snapshot outputs/network-debug.json `
  --debug-agent P00000000
```

Run a matched-seed governance intervention experiment:

```powershell
pineland-sim paired --config scenarios/baseline.json --repetitions 10 --multiplier 1.25
```

Compare macro behavior at fixed represented population across simulation resolutions:

```powershell
pineland-sim scale-check --config scenarios/baseline.json `
  --agents 25000 75000 150000 --days 30 `
  --output outputs/scale-comparison.json
```

The baseline configuration uses the specification target of 75,000 weighted agents. Start with smaller populations during development and benchmark 25,000, 75,000, and 150,000 agents before calibration runs.

### Repository hygiene

Generated empirical runs can be much larger than the source tree.  Use the
dry-run-first cleanup utility before manually deleting anything:

```powershell
python scripts/cleanup_generated_artifacts.py
python scripts/cleanup_generated_artifacts.py --apply --safety-age-hours 6
```

The utility only deletes explicitly disposable smoke/probe/cache trees and
refuses deletion if Git tracks anything inside a candidate.  On Windows/NTFS it
also LZX-compresses stale run, result, raw/processed-data, and generated-output
trees in place.  Compression is transparent: paths and file bytes are unchanged,
so retained negative results and provenance remain available for later analysis
or publication.  Trees modified inside the safety window are skipped to avoid
interfering with active runs.  Scratch/cache directories such as `tmp/`,
`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, and coverage output are ignored
by Git.

Run the publication-readiness smoke battery (add `--full` for the powered
resolution/sensitivity/recovery runs):

```powershell
pineland-sim readiness-report --agents 250 --days 2 `
  --output outputs/publication-readiness.json
```

The replicated language-factorial runs use up to eight CPU cores by default
(`--workers N` overrides this). Each worker owns a complete seeded simulation;
parallel scheduling therefore cannot change event ordering or random streams.

### Nepal historical benchmark

The first empirical benchmark is pinned under
`studies/nepal_2001_2006/`. It uses UCDP GED 26.1 as the district-week event
target, a separately documented INSEC cumulative spatial cross-check, a frozen
temporal/geographic split, eight fixed-seed 750-agent trajectories, four
process-isolated workers, leakage-controlled statistical competitors, and
matched mechanism ablations. Rebuild the derived products with:

```powershell
$env:PYTHONPATH = "src"
python studies/nepal_2001_2006/scripts/validate_contact_microworld.py
python studies/nepal_2001_2006/scripts/validate_logistics_independent.py
python studies/nepal_2001_2006/scripts/audit_supply_double_counting.py
python studies/nepal_2001_2006/scripts/validate_logistics_contact_branches.py
python studies/nepal_2001_2006/scripts/recover_contact_rate.py
python studies/nepal_2001_2006/scripts/analyze_supply_contact_chain.py
python studies/nepal_2001_2006/scripts/compute_contact_forensic.py
python studies/nepal_2001_2006/scripts/run_resolution_forensic.py
python studies/nepal_2001_2006/scripts/compute_model_benchmark.py
python studies/nepal_2001_2006/scripts/plot_benchmark.py
python studies/nepal_2001_2006/scripts/write_final_report.py
```

The current post-repair opportunity assessment is
`studies/nepal_2001_2006/results/opportunity_structure/armed_interaction_opportunity_report.md`,
with machine-readable metrics in
`results/opportunity_structure/post_repair_metrics.json`. The earlier
near-zero/zero-recorded-contact result is retained as a pre-repair
falsification artifact, not as the current model description. The repaired
opportunity structure produces a nondegenerate latent and recorded engagement
stream, but still underproduces the frozen district-week historical incidence.
The opportunity ceiling is therefore treated as structurally resolved while
historical fit and `contact_rate` calibration remain explicitly unlicensed.

## Output contract

Each run produces:

- `run_metadata.json`: schema, seed/stream namespace, output mode, resolution, and horizon.
- `summary.json`: headline counts and effective-control summaries.
- `checkpoints.json`: locality-by-actor control state at analysis intervals.
- `synthetic_records.jsonl`: imperfect researcher-visible event records.
- `causal_ledger.jsonl`: mechanism-level contributions to each control transition.
- `network_diagnostics.json`: community, degree, component, clustering, bridge, and language-compatibility measures.
- `physical_diagnostics.json`: per-locality and per-zone control, presence-memory, and response-time diagnostics.
- `logistics_diagnostics.json`: formation readiness, availability, stocks, orders, shipments, conservation, and control cost.
- `resource_flows.jsonl`: auditable production, shipment, delivery, movement, patrol, and sustained-presence resource flows.
- `information_diagnostics.json`: source mix, confidence, information age, command-relay state, detection counts, presence beliefs, and analyst-only belief error.
- `observations.jsonl`: first-class source observations with timestamps, estimated values, provenance, quality, and decay rates.
- `information_relays.jsonl`: command-network transmission attempts, route, latency, reliability, and delivery status.
- `recording_diagnostics.json`: generated-versus-recorded recall, event-type strata, geocoding-error rate, and distance distribution.
- `contact_funnel.jsonl`: scheduler-to-engagement gate traces with standardized rejection reasons and conditional counts.
- `action_funnel.json`: compact multichannel opportunity, choice, failure, latent-event, and state-based-event counts.
- `organization_eligibility.jsonl`: represented-size eligibility, split-hazard components, and realized conditional draws.
- `organization_onset.jsonl`: expected versus experienced repression and onset hazards.
- `causal_integrity_diagnostics.json`: cross-stock residuals, side-symmetric physical reach, belief-confidence health, recruitment-clock, patronage, and pathology warnings.
- `stock_transactions.jsonl`: event-boundary material/manpower deltas with stock class and boundary provenance.
- `state_deltas.jsonl`: sparse control, formation, belief, and organization changes keyed to event IDs.
- `stock_ledger_diagnostics.json`: initial/current aggregate stocks and conservation residuals.
- `global_accounting.json`: per-stock and population reconciliation with explicit flow-kind equations.

The effective-control scalar is for dashboards only. Analysis should retain the complete seven-dimensional vectors and their trajectories.

### Comparative research program

The moonshot roadmap is now encoded as an auditable program under
`studies/research_program/`: a frozen-core rule, case ladder, transport rules,
provisional competitive-local-reproduction theory, and a preregistered COIN
intervention contract. Run its structural audit with:

```powershell
$env:PYTHONPATH = "src"
python studies/research_program/scripts/audit_program.py
python studies/research_program/scripts/validate_coin_contract.py
```

The audit intentionally keeps calibration and general COIN efficacy unlicensed
until transfer evidence and simple-competitor tests earn them. The Colombia,
Iraq, and Vietnam packages are preregistration scaffolds, not completed case
claims.

### Current empirical status

Nepal and the first Afghanistan transfer are preserved negative results, not
validated substantive predictions. The completed 5,036-day Afghanistan
trajectories reached the October 2017 target but reproduced almost none of the
historically active province-weeks and produced zero or negative district
control correlations under the frozen v1 scalar measurement formulation.
Their supply-ledger failures have been reclassified as floating-point noise by
an absolute-plus-relative tolerance; no empirical score changed.

The prospective SIGAR operator is declared in
`studies/afghanistan_2004_2021/config/control_observation_model.json`. Future
runs retain all seven control dimensions for both actors. It is prohibited to
apply that operator retroactively to legacy scalar snapshots. Question-level
identifiability and spatial-reproduction diagnostics are under
`studies/research_program/`; global calibration and COIN inference remain
unlicensed.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The suite covers bounded equations, scheduler ordering, population and supply conservation, seed reproducibility, null models, independent forks, causal provenance, output persistence, social structure and influence, microzone topology and routing, presence decay, command latency/reliability, movement availability, deployment cost, resupply, readiness degradation/recovery, control-cost accounting, heterogeneous observations, confidence aging, contradictory evidence, language effects, social reporting, command relays, detection error, and analyst diagnostics.

## Architecture

`entities.py` holds scientific state, `generator.py` constructs the synthetic country, `networks.py` builds and measures social structure, `physical.py` builds locality-internal geography and physical-control fields, `logistics.py` owns pathfinding, supply, movement, command, and control-cost mechanics, `information.py` owns source collection, detection, fusion, confidence aging, and command relays, `events.py` owns temporal ordering, `processes.py` contains explicit transitions, `simulation.py` coordinates execution, `analytics.py` derives measures, `experiments.py` runs paired counterfactuals, and `scaling.py` measures resolution sensitivity. This keeps equations independently testable and leaves room for optimized kernels or a Julia core later without changing the analysis-facing data contract.

## Scope still ahead

The implemented conflict lifecycle is complete through combat, organizational ecology, political order, foreign affairs, and bargaining/DDR/recurrence. Research-readiness batteries now cover multi-seed resolution ladders, synthetic recorded-layer recovery, global sensitivity, measurement-model calibration, mechanism/topology/language ablations, global accounting, and long-horizon pathology monitoring. Empirical case data, construct calibration, holdout evaluation, and optional columnar/interactive analyst outputs remain external research work.

Numeric values in code are transparent initial priors. They are not calibrated findings or policy recommendations.

The continuation audit, resolved mismatches, benchmark snapshot, and remaining limitations are recorded in [`docs/implementation-audit.md`](docs/implementation-audit.md). Parameter meanings and calibration status are in [`docs/parameters.md`](docs/parameters.md).

The v0.11.1 causal-integrity repairs and adversarial validation protocol are recorded in [`docs/causal-integrity-v0.11.1.md`](docs/causal-integrity-v0.11.1.md). The v0.12.0 publication-audit closure and numeric validation batteries are documented in [`docs/research-audit-v0.12.0.md`](docs/research-audit-v0.12.0.md).

The verified Phase 1 + Phase 2 baseline is preserved at commit `124df96` and annotated tag `v0.2.0`. Phase 3 is preserved at commit `0b68d34` and annotated tag `v0.3.0`. Phase 4 observation/intelligence work is an explicit development diff on top of that checkpoint.
