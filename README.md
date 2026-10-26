# Pineland COIN-SIM

<p align="center">
  <img src="docs/assets/pineland-logo.webp" alt="Pineland project logo" width="144">
</p>

<p align="center">
  <strong>A partially observed agent-based laboratory for insurgency, counterinsurgency, state capacity, and competitive political order.</strong>
</p>

<p align="center">
  <a href="https://github.com/Jandro22/pineland/actions/workflows/pineland-ci.yml"><img src="https://github.com/Jandro22/pineland/actions/workflows/pineland-ci.yml/badge.svg?branch=main" alt="Pineland CI"></a>
  &nbsp; Python 3.11+ &nbsp;&middot;&nbsp; Rust &nbsp;&middot;&nbsp; Apache-2.0
</p>

Pineland COIN-SIM is a research-oriented simulation platform for studying how
armed organizations, governments, civilians, institutions, logistics,
information, mobility, foreign assistance, and territorial control interact
over time. The model is explicitly **partially observed**: actors operate on
imperfect beliefs and researchers receive imperfect records rather than direct
access to simulated truth.

The repository contains both a transparent Python reference implementation and
a standalone Rust runtime for larger ensembles, inference, forecast branches,
checkpoint/restart, and HPC execution. The current package version is
**0.13.0**.

> **Research status:** Pineland is an experimental scientific platform, not a
> validated forecasting system or operational decision-support tool. Synthetic
> experiments can identify mechanisms inside the model; historical comparisons
> are external tests and do not turn latent simulated quantities into observed
> historical facts.
>
> **Repository status (2026-10-26):** the first major research/paper cycle is
> scientifically frozen at the git tag `paper-freeze-2026-09-21` (the exact code
> that produced the frozen Stage-4 and Stage-5 datasets). A second, post-freeze
> line of work (see [Post-freeze research](#post-freeze-research-the-dependency-valley))
> repaired model failures and ran a follow-up autonomy-trap campaign. The model
> on `main` therefore **differs** from the frozen one and does not reproduce the
> frozen datasets bit for bit; check out the tag to reproduce them. Changes to
> the frozen paper material are still limited to documented corrections,
> reproducibility or packaging repairs, and changes required by peer review.

## Frozen research program

The frozen research snapshot is organized around three connected layers.

### 1. General Theory v1

[General Theory v1](studies/research_program/general_theory_v1/) asks whether
the high-dimensional ABM can be reduced to a smaller conditional theory of
competitive local reproduction without losing the dynamics that matter. The
program uses prospective contracts, rival reduced-form architectures, closure
tests, holdouts, and falsification ledgers before historical transport.

### 2. Partner-Force Autonomy — integrated Stages 4 and 5 complete

[Partner-Force Autonomy](studies/research_program/general_theory_v1/partner_force_autonomy/)
is the completed integrated Stage-4 mechanistic program on a narrower question:

> When does external security assistance create autonomous partner capability,
> and when does it create performance that disappears with the assistance?

The design uses paired ON/OFF counterfactual branches, common random numbers,
removable assistance channels, formal indigenous-service accounting, and
explicit separation of supported performance from organic regenerative
capacity. Stage 4 completed **2,808/2,808 production worlds** across an
autonomy phase map, bottleneck-migration experiment, and
substitution-versus-development experiment. Stage 5 then completed
**1,472/1,472 worlds** in the coordinated-development follow-up. The paper
cycle also includes the prospectively frozen 96-world demand-clamp experiment
and a 32-world terminal-constraint sidecar. The tracked production datasets
and paper-facing evidence have passed their integrity and manuscript
validation checks.

The final paper interpretation is narrower than the initial autonomy-trap
framing. Successful assistance can produce **relief** without corresponding
indigenous **yield**, leaving supported capability above what the partner can
retain after withdrawal. Constraint displacement is directly demonstrated as
one mechanism for that pattern. Requirement expansion remains plausible but is
not claimed as causally identified by the post-review clamp experiment because
its fresh-seed normal arms did not reproduce the registered coverage penalty.

See the [post-completion interpretation](studies/research_program/general_theory_v1/partner_force_autonomy/STAGE4_RESULTS_INTERPRETATION_2026-09-20.md),
the [precommitted paper-analysis plan](studies/research_program/general_theory_v1/partner_force_autonomy/STAGE4_PAPER_SECONDARY_ANALYSIS_PLAN_2026-09-20.md),
the tracked [compact Stage-4 evidence](studies/research_program/general_theory_v1/partner_force_autonomy/evidence/stage4/),
and the [final paper package](paper/partner_force_autonomy/).

### 3. State estimation and historical confrontation

The earlier [research-v1](docs/research-v1.md) program remains the inference
and validation spine: hide a synthetic trajectory behind an observation
process, recover it with particle filtering and calibrated uncertainty, test
misspecification, and only then confront held-out historical cases. Historical
case packages for Afghanistan, Nepal, Colombia, Iraq, and Vietnam are retained
under [studies](studies/).

## Post-freeze research: the dependency valley

After the freeze, the Partner-Force question was revisited with a repaired model
and a much larger paired-counterfactual campaign. The question: **when does
continued external support leave a partner force weaker than withdrawing it?**

The design forks each simulated world at a withdrawal decision (day 120) into
two twins, support continued and support withdrawn, that share their random
draws event by event, and compares partner capability a year later (an index
from 0 to 1 combining army retention, formation survival, geographic coverage,
readiness and government control). The campaign is **66,576 paired production
worlds** (1,000 agents, 72 localities, 64 seeds per condition, four partner
types, 140 design cells, 24 variants), run on a university cluster in about
1,800 service units.

One mechanism is *assumed*: partner institutions **learn by doing**. A channel's
capacity (force generation, logistics, command) grows when the partner serves
itself and fades when outsiders serve for it. Under that assumption:

| Learning rate (per 30 days) | Balanced | Command | Force generation | Logistics |
|---|---|---|---|---|
| 0 (no learning) | +0.002 | +0.019* | +0.013* | -0.006 |
| 0.25 | -0.072* | -0.068* | -0.019* | -0.034* |
| 0.5 | -0.085* | -0.079* | -0.036* | -0.052* |

Capability effect of continued minus withdrawn support at day +360, pooled over
the design (2,240 worlds per cell); `*` marks p < 0.05. More:

- the harm **deepens with the learning rate** and levels off near 0.5, and it
  needs fast learning or a strict self-reliance standard to appear;
- **dose is non-monotone** (the *dependency valley*): with learning, 4 times the
  design dose is the worst case (about -0.2 for balanced and command partners)
  and 16 times recovers, because outsiders then replace the partner's output
  (its own supply production keeps falling);
- continued support **saves military lives** at every dose, so the harm to
  capability is the price of lives saved now;
- **building the binding capacity** rescues logistics-limited forces (+0.08
  under learning) but not command-limited ones, and staggering the exit does
  not help.

These are consequences of an assumed mechanism, not an empirical finding: the
learning rate is only bounded (about 0.1 to 0.5) by a plausibility check, and
the reference share and development dose are uncalibrated. Details, tables,
replications at two scales and limits are in
[experiments/etf_resurrection/findings/RESULTS.md](experiments/etf_resurrection/findings/RESULTS.md);
how to reproduce (local and cluster) is in
[experiments/etf_resurrection/README.md](experiments/etf_resurrection/README.md).

The post-freeze model repairs are summarized in the same README and in the
[CHANGELOG](CHANGELOG.md).

## What the model contains

Pineland's implemented scientific core includes:

- weighted civilians and households with identities, preferences, grievance,
  fear, efficacy, trust, language, home, and residence;
- sparse multiplex social networks and community structure;
- locality and microzone physical graphs, terrain friction, patrols, fixed
  posts, movement, and response-time fields;
- multidimensional territorial control: formal, physical, administrative,
  legal, fiscal, social, and expected control;
- conserved logistics, supply routing, readiness, formation availability, and
  command reliability/latency;
- persistent armed-organization ecology, recruitment, leadership, adaptation,
  fragmentation, merger, collapse, and genealogy;
- belief-based organized action, spatial combat, civilian harm, and imperfect
  historical recording;
- political parties, elections, patronage, corruption flows, governance
  capacity, and peaceful political alternatives;
- borders, neighboring states, foreign formations, sanctuary, interpreters,
  external support, capacity transfer, and withdrawal;
- first-class observations, information relays, actor beliefs, state
  estimation, particle filtering, branch forecasts, and Monte Carlo error
  diagnostics;
- deterministic random-stream namespaces, causal ledgers, stock transactions,
  sparse state deltas, checkpoints, and reproducibility metadata.

Added after the freeze:

- territorial contestation with institutional erosion under insurgent
  dominance, shadow governance, a Lanchester-style coercive balance, and police
  reinsertion gating;
- insurgent organization splits, defection cascades, and abandonment of
  government posts under insurgent pressure;
- the `multichannel_v6` organized-action architecture: operational-reach armed
  strikes with intelligence-gated targeting, speculative sweeps, and insurgent
  tempo;
- partner-force support with removable channels, per-channel withdrawal delays,
  developmental assistance, and (in the Stage-4 harness) use-it-or-lose-it
  institutional learning;
- event-keyed random streams (`combat.rng_event_resync`) that keep paired
  counterfactual twins synchronized after their histories diverge.

The implementation-synchronized model description is
[docs/odd-model.md](docs/odd-model.md). Subsystem documentation lives under
[docs](docs/).

## Quick start

### Native Rust runtime

The Rust runtime owns the high-performance simulation and inference path.

    cargo test --workspace --manifest-path rust/Cargo.toml
    cargo run --release --locked --manifest-path rust/Cargo.toml -p pineland-cli -- run scenarios/baseline.json --seed 20011126 --days 7 --output outputs/native-baseline

See [rust/README.md](rust/README.md), [rust/BUILD.md](rust/BUILD.md), and
[rust/hpc/ARC.md](rust/hpc/ARC.md).

### Python reference runtime

    python -m pip install -e ".[research,dev]"
    pineland-sim run --agents 1000 --days 30 --output outputs/smoke

The package has no mandatory runtime dependencies; the **research** extra adds
the analysis stack and **dev** adds pytest.

### Research-v1 reproduction smoke

    python pineland.py reproduce paper1 --profile smoke

This is a software/reproduction smoke, **not** a confirmatory paper run.

### Partner-force preflight

    python studies/research_program/general_theory_v1/partner_force_autonomy/validate_partner_force_autonomy_environment.py
    cargo run --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3
    python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/partner_force_autonomy_holdouts.py --dry-run

The Rust example exits without scientific compute unless an explicit execution
flag is supplied.

The complete Stage-4 production protocol, Virginia Tech Advanced Research
Computing (ARC) scheduler layout, and postprocessing chain are documented in
[STAGE4_INTEGRATED_PROTOCOL_v1.md](studies/research_program/general_theory_v1/partner_force_autonomy/STAGE4_INTEGRATED_PROTOCOL_v1.md)
and
[STAGE4_RUN_LEDGER_2026-09-20.md](studies/research_program/general_theory_v1/partner_force_autonomy/STAGE4_RUN_LEDGER_2026-09-20.md).

### Autonomy-trap campaign (post-freeze)

    python experiments/etf_resurrection/arc/build_campaign.py --design studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_autonomy_phase_map_v1.json --out experiments/etf_resurrection/results/local --local --seeds 16
    python experiments/etf_resurrection/arc/analyze_local.py --campaign experiments/etf_resurrection/results/local

The first command builds a small local campaign; see
[experiments/etf_resurrection/README.md](experiments/etf_resurrection/README.md)
for running it, for the production-scale cluster run, and for the figures.

## Repository map

| Path | Purpose |
|---|---|
| [rust/](rust/) | Standalone Rust runtime, inference engine, checkpointing, MPI/HPC support |
| [src/pineland_sim/](src/pineland_sim/) | Python reference model and analysis-facing API |
| [tests/](tests/) | Regression, invariant, exactness, and scientific-method tests |
| [scenarios/](scenarios/) | Hand-authored model configurations |
| [docs/](docs/) | Model, validation, audit, and research-method documentation |
| [studies/](studies/) | Historical case packages and frozen research-program artifacts |
| [experiments/etf_resurrection/](experiments/etf_resurrection/) | Post-freeze model repair, the autonomy-trap campaign, findings and figures |
| [scripts/](scripts/) | Repository, evidence, and research maintenance utilities |

The complete evidence/retention policy is in
[docs/repository-layout.md](docs/repository-layout.md).

Historical source redistribution status is summarized in
[docs/third-party-data-status.md](docs/third-party-data-status.md); a source is
not assumed publishable merely because its provenance is documented.

For a compact view of which subsystems are currently research-load-bearing,
implemented but secondary, or still under active validation, see
[docs/subsystem-status.md](docs/subsystem-status.md).

## Reproducibility and evidence policy

Pineland distinguishes **source code**, **prospective contracts**, **generated
panels**, and **compact scientific evidence**. Large raw panels, historical
data products, and ordinary run outputs stay outside normal Git history;
contracts, falsification ledgers, compact summaries, and audit records are
retained when they support a scientific claim.

Repository cleanup is dry-run first:

    python scripts/cleanup_generated_artifacts.py
    python scripts/cleanup_generated_artifacts.py --apply --safety-age-hours 6

The utility refuses to delete tracked files, skips recently modified work, and
on Windows transparently compresses stale scientific output rather than
deleting it.

The frozen paper cycle is pinned to the git tag `paper-freeze-2026-09-21`.
The model on `main` includes post-freeze repairs and its default behavior
differs from that tag, so frozen-paper numbers should be reproduced from the
tag, and post-freeze numbers from `main`.

Important reproducibility contracts include deterministic event ordering,
namespace-derived random streams, paired common-random-number branches,
versioned schemas, explicit provenance, state hashing, and restartable
checkpoints. Native details are documented in [rust/README.md](rust/README.md).

## Scientific boundaries

Pineland deliberately keeps several categories separate:

- **structural assumptions** — model architecture;
- **engineering priors** — values chosen to make a synthetic world executable;
- **case inputs** — observed or reconstructed historical inputs;
- **calibrated parameters** — quantities estimated under an explicit procedure;
- **latent states** — simulated but not directly observed quantities;
- **actor beliefs** — what agents inside the model think is true;
- **recorded observables** — what a synthetic or historical analyst can see.

Numerical priors in the repository are not empirical findings merely because
they appear in code. Synthetic results are evidence about the behavior of the
specified model. Historical claims require separately documented measurement,
validation, and transport procedures.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a change. Scientific
changes should preserve deterministic tests, provenance, and the distinction
between exploratory and confirmatory work.

## Citation and license

Citation metadata is provided in [CITATION.cff](CITATION.cff). Pineland is
released under the [Apache License 2.0](LICENSE). Project attribution notices
are recorded in [NOTICE](NOTICE).

Release conventions are documented in
[docs/release-policy.md](docs/release-policy.md). The public-release gate is in
[docs/public-release-checklist.md](docs/public-release-checklist.md).
