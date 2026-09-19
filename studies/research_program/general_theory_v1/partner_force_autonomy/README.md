# Partner-Force Autonomy — Stage 3

> **Research question:** When does security-force assistance create autonomous
> military capability, and when does it create only externally supported
> performance?

This directory is a preregistered synthetic discovery program inside Pineland
General Theory v1. It is designed to separate **supported performance** from
**partner-owned regenerative capacity** using paired counterfactual branches,
common random numbers, removable assistance overlays, and held-out tests.

**Current status:** Stage 3 mechanistic discovery is active. Stage 4
policy-comparison configurations remain blocked until the Stage-3 coordinates,
holdouts, and resolution checks are frozen and passed.

## Directory map

| Path | Purpose |
|---|---|
| **configs/** | Stage-3 design cells and blocked future policy configs |
| **contracts/** | Preregistration freeze, raw schema, holdouts, and resolution audit |
| **analysis/** | Metric derivation, regenerative coordinates, holdouts, and transport |
| **fixtures/** | Small deterministic validation fixtures |
| **outputs/** | Generated outputs; ignored except the directory sentinel |
| **validate_partner_force_autonomy_environment.py** | Preflight consistency checks |

## Core distinction

The program keeps four concepts separate:

1. **Supported performance (C_ON)** — capability while external support is
   available.
2. **Organic capacity (Ω)** — partner-owned stocks and endogenous regeneration
   flows.
3. **Autonomy after withdrawal (R_h)** — retained capability in a paired
   support-OFF branch relative to the support-ON branch.
4. **Long-horizon resilience** — persistence and renewal after losses and
   operational friction.

At withdrawal time **T = 120d**, the simulation world is cloned. One branch
retains external assistance; the paired branch removes only the designated
assistance overlays. Indigenous formations, people, organizations, supply
stocks, governance state, topology, and RNG streams remain identical at the
split.

## Assistance channels

| Channel | Mechanism | Accounting rule |
|---|---|---|
| Air support | External firepower increment during eligible contacts | Metered separately from organic firepower |
| Logistics | External supply push with capacity/loss accounting | Offered = delivered + rejected + lost |
| Command advisory | Reliability boost and latency reduction | Does not mutate underlying command topology |
| Force generation | Removable training-throughput increment | Organic and external graduates remain separable |

## Capability assay

Outcome capability is measured with the frozen behavioral assay
**pineland.partner_force_capability_assay.v1**:

    C(t) = (c_gov · c_personnel · c_formation · c_coverage)^(1/4)

The predictor firewall excludes regenerative stocks, flows, command-edge
parameters, and training throughput from the capability outcome itself. This
prevents the proposed explanatory coordinates from being mechanically embedded
in the dependent variable.

## Stage-3 design

The discovery manifest **configs/stage3_discovery_cells_v1.csv** defines
capacity profiles crossed with removable support compositions. The design
includes explicit negative-control cells in which no support is present; those
cells require paired ON/OFF capability to remain identical.

### Prospective holdouts

Four independently specified holdout families live under **contracts/**:

- **complexity** — changes environmental or operational complexity;
- **force-generation regime** — changes indigenous regeneration conditions;
- **support composition** — changes the mixture of removable assistance;
- **threat pressure** — changes adversary pressure.

Holdout evaluation is separate from discovery fitting. Contracts specify their
own evaluation horizons, and required short- and long-horizon gates must both
be satisfied rather than allowing a favorable early horizon to mask later
failure.

The separate **partner_force_scale_resolution_audit_v1.json** checks whether
substantive conclusions remain stable when simulation resolution changes.

## Verification

### Preflight

    python studies/research_program/general_theory_v1/partner_force_autonomy/validate_partner_force_autonomy_environment.py

### Rust tests

    cargo test --workspace --manifest-path rust/Cargo.toml

### Zero-compute design check

    cargo run --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3

Without an explicit execution flag, the runner prints the design summary and
exits without instantiating a scientific run.

### Tiny plumbing smoke

    cargo run --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3 -- --smoke --execute

### Analysis dry-runs

    python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/evaluate_partner_force_autonomy.py --dry-run
    python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/partner_force_autonomy_holdouts.py --dry-run

## Execution

Production Stage-3 discovery should run on **VT ARC Owl** (`normal_q`,
`owl_normal_base`) because matched 1,000-agent Stage-3 benchmarks were faster
than the development laptop on Owl, while TinkerCliffs was slower per task.
Each Slurm task owns exactly one `(cell, seed)` world and writes two atomic
products:

1. the frozen 8-row confirmatory branch shard; and
2. a 66-row diagnostic trajectory sidecar.

The trajectory sidecar samples the supported pre-withdrawal world every seven
days from day 60 through T=120, then samples both ON and OFF branches weekly
through day 180 while also including the exact 7/30/90/180 confirmatory
horizons. It records state, mechanism-flow, donor-support, and cryptographic
provenance fields. The sidecar is **diagnostic/exploratory only** and cannot be
used to redefine H1/H2/H3 or the preregistered predictor after outcomes are
seen. The non-interference audit demonstrates that adding these observations
left a matched supported production-scale primary output byte-identical.

Build on Owl with the pinned Rust toolchain and submit the frozen 720-task
array with bounded concurrency:

    cargo build --release --locked --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3
    sbatch --array=0-719%8 --account=will_taggart_mcll --partition=normal_q --qos=owl_normal_base --constraint=avx512 studies/research_program/general_theory_v1/partner_force_autonomy/arc/partner_force_array.sbatch

After all 720 tasks succeed, merge and validate **both** products:

    python studies/research_program/general_theory_v1/partner_force_autonomy/arc/merge_partner_force_shards.py \
      --input-dir studies/research_program/general_theory_v1/partner_force_autonomy/outputs/arc_stage3_shards \
      --expected-tasks 720 \
      --output-csv studies/research_program/general_theory_v1/partner_force_autonomy/outputs/partner_force_autonomy_stage3_raw_v2.csv \
      --trajectory-output-csv studies/research_program/general_theory_v1/partner_force_autonomy/outputs/partner_force_autonomy_stage3_trajectory_v1.csv

The expected production totals are **5,760 confirmatory branch rows** and
**47,520 diagnostic trajectory rows**. Analysis must not begin unless the
merger validates complete task coverage and both output classes.

Confirmatory analysis remains unchanged. Diagnostic trajectory analysis is a
separate downstream step:

    python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/analyze_partner_force_trajectories.py \
      --trajectory-csv studies/research_program/general_theory_v1/partner_force_autonomy/outputs/partner_force_autonomy_stage3_trajectory_v1.csv \
      --output-dir studies/research_program/general_theory_v1/partner_force_autonomy/outputs/trajectory_diagnostics

A local Stage-3 run remains available as a reproducibility fallback:

    cargo run --release --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3 -- --execute

Generated scientific outputs belong under **outputs/** and are intentionally
ignored by Git.

## Interpretation boundary

Stage 3 can establish relationships **inside the synthetic model** between
assistance composition, indigenous regeneration, supported capability, and
post-withdrawal retention. It does not by itself establish that a historical
partner force failed for the same reason, nor does it license a recommendation
for a real assistance policy.

Historical application requires a separately frozen measurement/transport
design and evidence that the relevant model quantities can be connected to
observed data.
