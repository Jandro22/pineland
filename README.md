# Pineland COIN-SIM

The current `v0.5` development line adds spatial stochastic armed engagements,
attrition, cohesion failure, disengagement, conserved combat expenditure,
civilian-harm observations, perceived momentum, and logistics-routed
reinforcement. See [the combat model](docs/combat-model.md).

Pineland COIN-SIM is a research-oriented, partially observed agent-based simulation of insurgency, counterinsurgency, governance, mobility, information, and multidimensional territorial control. The current v0.4 development line implements the runtime spine, social and physical structure, logistics, and explicit detection/information fusion described by the technical design specification.

The current engine is intentionally dependency-light and transparent. Every important control change is written to a causal ledger, actors act on noisy estimates rather than world truth, population agents carry weights, and all randomness is split into deterministic named streams.

## Implemented foundation

- Fixed 17-district Pineland registry and configurable generation of 60–90 heterogeneous localities.
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
- Asynchronous priority event scheduler with terrain-sensitive formation movement/patrol, information collection/fusion, civilian mobility, recruitment, governance, economy, detection/contact/combat, and checkpoint processes.
- Actor-specific evidence-based beliefs and a separate biased synthetic historical record.
- Conserved represented population, bounded state checks, stock checks, deterministic checkpoints, and causal provenance.
- Matched-seed scenario forks, ensemble summaries, locality causal decomposition, control velocity, and district aggregation.
- Subsystem-specific deterministic random streams, JSON scenario configuration, command-line entry point, and machine-readable output products.

## Quick start

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

## Output contract

Each run produces:

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

The effective-control scalar is for dashboards only. Analysis should retain the complete seven-dimensional vectors and their trajectories.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The suite covers bounded equations, scheduler ordering, population and supply conservation, seed reproducibility, null models, independent forks, causal provenance, output persistence, social structure and influence, microzone topology and routing, presence decay, command latency/reliability, movement availability, deployment cost, resupply, readiness degradation/recovery, control-cost accounting, heterogeneous observations, confidence aging, contradictory evidence, language effects, social reporting, command relays, detection error, and analyst diagnostics.

## Architecture

`entities.py` holds scientific state, `generator.py` constructs the synthetic country, `networks.py` builds and measures social structure, `physical.py` builds locality-internal geography and physical-control fields, `logistics.py` owns pathfinding, supply, movement, command, and control-cost mechanics, `information.py` owns source collection, detection, fusion, confidence aging, and command relays, `events.py` owns temporal ordering, `processes.py` contains explicit transitions, `simulation.py` coordinates execution, `analytics.py` derives measures, `experiments.py` runs paired counterfactuals, and `scaling.py` measures resolution sensitivity. This keeps equations independently testable and leaves room for optimized kernels or a Julia core later without changing the analysis-facing data contract.

## Scope still ahead

The current development version establishes the runtime spine, Phase 1 social structure, Phase 2 physical occupation, Phase 3 logistics/force projection, and Phase 4 observation/intelligence with evidence-based partial information without claiming scientific calibration. Detailed combat resolution remains deliberately deferred; the inherited contact placeholder is retained only as a compatibility path. Later work includes endogenous organization birth/splitting, patronage allocation, foreign actor decision clocks, negotiation/demobilization/recurrence, global sensitivity/identifiability pipelines, columnar event storage, and the semantic-zoom analyst interface.

Numeric values in code are transparent initial priors. They are not calibrated findings or policy recommendations.

The continuation audit, resolved mismatches, benchmark snapshot, and remaining limitations are recorded in [`docs/implementation-audit.md`](docs/implementation-audit.md). Parameter meanings and calibration status are in [`docs/parameters.md`](docs/parameters.md).

The verified Phase 1 + Phase 2 baseline is preserved at commit `124df96` and annotated tag `v0.2.0`. Phase 3 is preserved at commit `0b68d34` and annotated tag `v0.3.0`. Phase 4 observation/intelligence work is an explicit development diff on top of that checkpoint.
