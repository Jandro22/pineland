# Pineland COIN-SIM

Pineland COIN-SIM is a research-oriented, partially observed agent-based simulation of insurgency, counterinsurgency, governance, mobility, information, and multidimensional territorial control. This repository begins the v0.1 implementation described by the technical design specification.

The current engine is intentionally dependency-light and transparent. Every important control change is written to a causal ledger, actors act on noisy estimates rather than world truth, population agents carry weights, and all randomness is split into deterministic named streams.

## Implemented foundation

- Fixed 17-district Pineland registry and configurable generation of 60–90 heterogeneous localities.
- Weighted people, explicit households, individual multilingual proficiency, identities, preferences, grievance, fear, efficacy, trust, home, and residence.
- Explicit social communities and sparse multiplex household, community, and cross-community bridge edges.
- Language-aware communication weights, network exposure, civilian public-behavior choice, and community-to-locality aggregation.
- Locality-internal physical graphs, microzones, fixed posts, belief-routed patrol paths, presence memory, and response-time fields.
- Population-weighted upward aggregation from microzone physical control to locality physical control.
- Government, military, police, parties, an optional insurgent organization, and armed formations.
- Seven-dimensional control vectors for formal, physical, administrative, legal, fiscal, social, and expected control.
- Connected locality graph with terrain-friction travel costs.
- Asynchronous priority event scheduler with terrain-sensitive formation movement/patrol, belief, civilian mobility, recruitment, governance, economy, detection/contact/combat, and checkpoint processes.
- Actor-specific noisy beliefs and a separate biased synthetic historical record.
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

The effective-control scalar is for dashboards only. Analysis should retain the complete seven-dimensional vectors and their trajectories.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The suite covers bounded equations, scheduler ordering, district/locality generation, population conservation, seed reproducibility, the no-insurgency null model, independent forks, causal provenance, output persistence, household/community membership, network connectivity, language compatibility, bridge structure, and social influence.

## Architecture

`entities.py` holds scientific state, `generator.py` constructs the synthetic country, `networks.py` builds and measures social structure, `physical.py` builds locality-internal geography and physical-control fields, `events.py` owns temporal ordering, `processes.py` contains explicit mechanisms, `simulation.py` coordinates execution, `analytics.py` derives measures, `experiments.py` runs paired counterfactuals, and `scaling.py` measures resolution sensitivity. This keeps transition equations independently testable and leaves room for optimized kernels or a Julia core later without changing the analysis-facing data contract.

## Scope still ahead

The current slice establishes the runtime spine, Phase 1 social structure, and Phase 2 physical occupation model but does not claim full scientific calibration. The next implementation phase should deepen military movement and logistics across localities without adding tactical detail. Later work includes endogenous organization birth/splitting, patronage allocation, foreign actor decision clocks, negotiation/demobilization/recurrence, global sensitivity/identifiability pipelines, columnar event storage, and the semantic-zoom analyst interface.

Numeric values in code are transparent initial priors. They are not calibrated findings or policy recommendations.

The continuation audit, resolved mismatches, benchmark snapshot, and remaining limitations are recorded in [`docs/implementation-audit.md`](docs/implementation-audit.md). Phase 1 parameter meanings and calibration status are in [`docs/parameters.md`](docs/parameters.md).
