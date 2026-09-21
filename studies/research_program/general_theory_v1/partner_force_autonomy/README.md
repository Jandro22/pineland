# Partner-Force Autonomy, integrated Stage 4 plus prospective Stage 5

> **Research question:** When does external security assistance create
> autonomous partner capability, and when does it create performance that
> depends on continued external support?

This directory contains the completed Stage-3/Stage-4 synthetic research
program for partner-force autonomy inside Pineland General Theory v1. The core
design separates **supported operational performance** from **indigenous service
production and regeneration**, then follows how the binding constraint changes
after assistance alters the system.

## Current status

**Stage 4 is complete.** The integrated campaign produced and verified
**2,808/2,808 production worlds**:

**Stage 5 is prospectively frozen before production.** The coordinated-
development follow-up contains 92 cells and 16 common-random-number seeds per
cell, for **1,472 planned worlds**. It tests every nonempty combination of
force-generation, logistics, and command development under two dosing regimes:
fixed total normalized effort and equal per-channel dose. This separates the
value of breadth from the trivial advantage of simply spending more.

Stage 5 was designed after Stage-4 outcomes were known and must always be
reported as a motivated follow-up rather than part of the original Stage-4
preregistration. See `STAGE5_RISING_TIDE_PROTOCOL_v1.md`.

| Module | Cells | Seeds | Worlds | Purpose |
|---|---:|---:|---:|---|
| Autonomy-Trap Phase Map | 140 | 12 | **1,680** | Map short-run capability gains against long-run indigenous autonomy |
| Bottleneck Migration | 52 | 12 | **624** | Test whether successful assistance changes which service constraint binds |
| Substitution vs Development | 42 | 12 | **504** | Compare direct external service substitution with indigenous-capacity development and hybrid treatments |
| **Total** | **234** | — | **2,808** | Integrated one-paper experiment family |

The final production dataset was independently re-hashed after completion. All
2,808 logical task IDs were present exactly once; primary and trajectory
SHA-256s, row counts, filenames, source commit, contract hashes, and freeze
provenance matched with **zero integrity errors**.

The final integrated READY artifact is tracked under
[`evidence/stage4/READY_STAGE4_INTEGRATED.json`](evidence/stage4/READY_STAGE4_INTEGRATED.json).

## Main synthetic findings

The results support a moving-binding-constraint account of security assistance.

### 1. Direct substitution usually produced an autonomy trap

Among the **106 treated Phase-Map cells** in which continued direct service
assistance improved composite capability at +30 days, **96 (90.6%)** had lower
capped indigenous autonomy at +360 days.

- **53** cells met the precommitted robust autonomy-trap rule.
- **0** cells met the robust autonomy-building rule.
- The mean terminal autonomy penalty became more negative as direct support
  intensity increased: approximately **−0.025 at 0.25×** versus **−0.132 at
  2.0×**.

### 2. Bottlenecks migrated asymmetrically

When targeted support matched the observed pre-withdrawal bottleneck:

- command: **38/38** worlds persistently migrated, median detection **7 days**;
- force generation: **46/46** migrated, median **7 days**;
- logistics: **0/85** migrated.

Command and force-generation relief overwhelmingly exposed **logistics** as the
next binding constraint. Logistics behaved as a terminal/sink constraint in the
tested architecture.

### 3. Developmental assistance can outperform substitution without guaranteeing autonomy

Developmental logistics assistance improved terminal autonomy relative to
direct substitution by approximately **+0.132 to +0.433 q** across the four
matched severity/intensity contrasts; every corresponding 95% bootstrap
interval excluded zero. It also produced large gains in indigenous logistics
output and indigenous coverage of cumulative demand.

However, local subsystem development did not automatically translate into
whole-system autonomy. Force-generation development could generate large
additional indigenous output while leaving whole-system `q` unchanged because
logistics became binding. Command development similarly improved indigenous
command service while frequently shifting the bottleneck to logistics.

The resulting theoretical synthesis is:

> **The autonomy effect of external assistance depends on whether indigenous
> production keeps pace with the operating requirement at the constraint that
> ultimately binds the adapted system. Successful development of one subsystem
> can fail at the system level when the binding constraint migrates elsewhere.**

These are synthetic-model findings, not empirical estimates for a historical
partner force. Historical transport and validation remain separate tasks.

## Evidence and provenance

The research layers are deliberately separated so later interpretation does not
rewrite preregistration history.

| Artifact | Role |
|---|---|
| [`RESEARCH_PROGRAM_MEMO_2026-09-20.md`](RESEARCH_PROGRAM_MEMO_2026-09-20.md) | Literature-adjusted program synthesis and experiment priorities |
| [`STAGE4_INTEGRATED_PROTOCOL_v1.md`](STAGE4_INTEGRATED_PROTOCOL_v1.md) | Frozen integrated experiment design and production integrity rules |
| [`contracts/partner_force_stage4_integrated_freeze_v1.json`](contracts/partner_force_stage4_integrated_freeze_v1.json) | Cryptographic production freeze |
| [`STAGE4_RUN_LEDGER_2026-09-20.md`](STAGE4_RUN_LEDGER_2026-09-20.md) | ARC jobs, commits, gates, repairs, and integrity record |
| [`POSTPROCESS_REPAIR_2026-09-20.md`](POSTPROCESS_REPAIR_2026-09-20.md) | Postprocessing-only defects and audited repairs |
| [`STAGE4_PAPER_SECONDARY_ANALYSIS_PLAN_2026-09-20.md`](STAGE4_PAPER_SECONDARY_ANALYSIS_PLAN_2026-09-20.md) | Paper-level estimands and uncertainty rules fixed before production completion |
| [`STAGE4_RESULTS_INTERPRETATION_2026-09-20.md`](STAGE4_RESULTS_INTERPRETATION_2026-09-20.md) | Post-completion interpretation and theory synthesis |
| [`evidence/stage4/`](evidence/stage4/) | Compact tracked READY manifests and paper-level summary tables |

The raw 2,808-world panels remain outside normal Git history under the
repository evidence policy. Compact summaries required to verify published
claims are tracked here.

### Provenance commits

- production simulator/contracts: `e369c107f4465ce8cd385a366cafca8c28c04b65`
- final postprocessing hardening: `7697e6eac83248c7bc03830e58d94a2d878c6635`
- precommitted paper-level analysis: `9b0e975c7e4073f2f5abd94e72cd125beb75f20d`
- post-completion interpretation: `472ca6cfc417eef7e424c2f5b53960aa274535bf`

## Formal autonomy coordinate

The formal layer represents force generation, logistics, and command as service
channels with demand `D`, indigenous service `I`, and external service `E`.
For each active channel:

```text
q_indigenous = I / D
q_supported  = (I + E) / D
```

System indigenous autonomy uses the minimum active service ratio; capped
feasible autonomy uses `min(q_indigenous, 1)`. The formal definitions and audit
are under [`formal/partner_force_theory/`](formal/partner_force_theory/).

The paper-level autonomy-trap estimand was fixed before production completion:

```text
early operational effect = Δ composite capability at +30d
terminal autonomy effect = Δ min(q_indigenous, 1) at +360d
```

An **effective autonomy trap** has positive early operational effect and
negative terminal autonomy effect.

## Stage-4 treatment architecture

Direct substitution retains the removable Stage-3 service overlays. Stage 4
adds persistent indigenous-development treatments:

- **force generation:** raises endogenous recruitment/training production;
- **logistics:** raises indigenous sustainment production;
- **command:** improves indigenous command reliability/latency;
- **hybrid:** combines direct substitution with developmental investment.

Development accumulated before withdrawal remains indigenous capacity;
continued donor-funded developmental growth stops in the withdrawal branch.

At day 120 each world is cloned into `SUPPORT_ON` and `SUPPORT_OFF`. The clone
preserves the full state and random streams; the OFF branch removes only the
specified external/developmental continuation. Primary horizons are +7, +30,
+90, +180, and +360 days.

## Directory map

| Path | Purpose |
|---|---|
| [`configs/`](configs/) | Stage-3 discovery cells and historical configuration inputs |
| [`contracts/`](contracts/) | Stage-3/Stage-4 preregistration, schemas, runtime amendments, holdouts, and freezes |
| [`analysis/`](analysis/) | Stage-3 diagnostics, integrated Stage-4 analysis, and precommitted paper-level secondary analysis |
| [`arc/`](arc/) | Owl/Slurm execution, merge, validation, postprocessing, and finalization wrappers |
| [`formal/`](formal/) | Lean formalization of the partner-force autonomy coordinate |
| [`fixtures/`](fixtures/) | Small deterministic validation fixtures |
| [`evidence/stage4/`](evidence/stage4/) | Compact completed Stage-4 evidence retained in Git |
| [`outputs/`](outputs/) | Generated large outputs; ignored except the directory sentinel |

## Reproduction and validation

### Environment/preflight

```bash
python studies/research_program/general_theory_v1/partner_force_autonomy/validate_partner_force_autonomy_environment.py
cargo test --workspace --manifest-path rust/Cargo.toml
cargo run --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3
```

The Stage-4 design/contracts can be regenerated and validated with:

```bash
python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/generate_stage4_integrated_designs.py
python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/generate_stage4_freeze.py
```

Virginia Tech Advanced Research Computing (ARC) production and postprocessing
are documented in
[`arc/launch_stage4_integrated.sh`](arc/launch_stage4_integrated.sh),
[`arc/stage4_array.sbatch`](arc/stage4_array.sbatch), and
[`arc/stage4_postprocess.sbatch`](arc/stage4_postprocess.sbatch).

The precommitted paper-level summary is generated by
[`analysis/analyze_stage4_paper_secondary.py`](analysis/analyze_stage4_paper_secondary.py).

## Interpretation boundary

Stage 4 establishes causal relationships **inside the synthetic Pineland
model**. Numerical transition regions, effect sizes, and the apparent terminal
role of logistics are model findings, not empirical cutoff values for real
security forces. Historical use requires independent measurement, process
tracing, or external validation of the relevant mechanisms.
