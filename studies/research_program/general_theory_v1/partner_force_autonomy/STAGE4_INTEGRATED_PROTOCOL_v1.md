# Stage 4 Integrated Partner-Force Paper Protocol v1

## Scientific objective

Stage 4 is one integrated paper program, not three independent papers.  It tests
the proposition that effective external assistance can become autonomy-eroding
when successful bottleneck relief expands operational demand faster than
indigenous capacity adapts, and that successful relief changes which indigenous
constraint binds next.

The causal structure is:

```text
external assistance
  -> relief of current binding constraint
  -> immediate supported capability/service gain
  -> change in operational demand
  -> indigenous production response or substitution
  -> autonomy gain/loss
  -> migration of the binding constraint
```

The program contains three coordinated modules with common outcome definitions,
matched/randomized seed logic, and a shared frozen analysis pipeline.

## Foundation gate

Stage 4 is conditional on the accepted Stage-3 v5 foundation recorded in
`contracts/stage4_foundation_reference_v1.json`.  Stage-3 production outcomes
are not pooled with Stage-4 outcomes.  They are used only for theory/design
calibration that occurred before the Stage-4 production freeze.

## Engineering calibration firewall

The developmental-assistance implementation is calibrated only on the
`2026290000` engineering seed namespace.  Calibration may establish treatment
relevance and reject runtime defects; it may not choose parameters to maximize
the Stage-4 hypotheses.  Production seeds begin at the contract-specific bases
`2026200000`, `2026210000`, and `2026220000` and remain unseen until the final
freeze is committed.

The initial developmental scale is retained unless the engineering calibration
shows treatment degeneracy or a correctness defect:

```text
development_rate_per_30d = 0.08 * factor_intensity
```

with factor intensities `0.5` and `1.0` in the mechanism experiment.  Under the
fixed seven-day treatment cadence this is deliberately moderate rather than an
instantaneous capacity jump.

## Module A — Autonomy-Trap Phase Map

Contract: `contracts/stage4_autonomy_phase_map_v1.json`

- 140 cells
- 12 production seeds per cell
- 1,680 worlds
- four starting structural families:
  - force-generation constrained;
  - logistics constrained;
  - command constrained;
  - balanced low capacity;
- five indigenous-capacity levels per family;
- seven balanced service-support intensities: `0, .25, .5, .75, 1, 1.5, 2`.

Primary question: where does the paired continued-support effect on terminal
indigenous autonomy change sign, and how does that boundary relate to indigenous
service response versus support-enabled demand?

Primary classification always reports:

```text
Delta capability
Delta indigenous service (I)
Delta service demand (D)
Delta q_indigenous
```

so a higher `I/D` caused only by demand collapse cannot be mislabeled as
capacity development.

## Module B — Bottleneck Migration

Contract: `contracts/stage4_bottleneck_migration_v1.json`

- 52 cells
- 12 production seeds per cell
- 624 worlds
- four starting structural families;
- one no-support comparator per structural family;
- force-generation-, logistics-, command-, and balanced-targeted support;
- three treatment intensities for each treated target.

The observed pre-withdrawal formal bottleneck determines whether assistance was
actually matched.  Contract labels are hypotheses, not ground truth.

Persistent migration is preregistered as the first post-split checkpoint at
which the observed formal bottleneck differs from the pre-withdrawal bottleneck
for two consecutive checkpoints.

The minimum-ratio bottleneck result must be accompanied by smooth arithmetic,
geometric, and harmonic channel-feasibility aggregators reconstructed from raw
trajectory services and demands.  A result that exists only because the formal
coordinate uses a hard minimum is insufficient for the paper's dynamic claim.

## Module C — Substitution vs Development

Contract: `contracts/stage4_substitution_development_v1.json`

- 42 cells
- 12 production seeds per cell
- 504 worlds
- force-generation, logistics, and command target systems;
- severe and moderate indigenous weaknesses;
- no-aid, substitution, developmental, and hybrid treatments;
- low/high treatment intensities for treated modes.

Direct substitution uses the existing external service overlays. Developmental
assistance instead changes partner-owned productive capacity on a fixed weekly
cadence:

- force generation: persistent endogenous recruitment/training-rate growth;
- logistics: persistent indigenous sustainment-production growth;
- command: persistent improvement in indigenous command reliability/latency.

Accrued developmental capacity survives withdrawal. Future developmental growth
and developmental donor cost stop in the withdrawal branch.

Developmental daily budget anchors are calibrated from Stage-3 mean donor costs
for the corresponding heavy support profiles:

| Channel | Nominal daily anchor |
|---|---:|
| Force generation | 1,650 |
| Logistics | 12,284 |
| Command | 2,550 |

The primary comparison is therefore not forced equality of early behavioral
capability. It is the capability/autonomy/indigenous-production trajectory at
approximately comparable channel-specific donor budgets.

## Common randomization and horizons

Every module uses 12 seeds and the common confirmatory horizons:

```text
7, 30, 90, 180, 360 days after the day-120 split
```

Within a cell and seed, SUPPORT_ON and SUPPORT_OFF remain exact cloned branches
at withdrawal. Across treatment cells, repeated seed indices provide common
random-number structure but are not treated as exact paired states once their
pre-withdrawal treatments differ.

## Frozen analysis

`analysis/analyze_stage4_integrated.py` is the common preregistered analysis.

Primary terminal autonomy classification uses:

```text
Delta min(q_indigenous, 1.0) at 360 days
```

while raw uncapped `q_indigenous` is retained as a resilience-margin outcome.
An assistance cell is "initially effective" when paired
`Delta composite_capability_30 > 1e-6`.

The four substantive 360-day quadrants are:

- productive autonomy: capability up, autonomy up;
- dependency gain: capability up, autonomy down;
- contraction autonomy: capability down, autonomy up;
- double harm: capability down, autonomy down.

Neutral/mixed outcomes remain a fifth residual class and are not forced into a
directional category.

Means alone are insufficient.  Report medians, quantiles, class frequencies,
and tails because Stage 3 demonstrated material heavy-tail behavior.

## ARC production plan

The scheduler throttle is operational, not scientific.  The initial concurrent
launch is:

| Module | Worlds | Initial concurrency |
|---|---:|---:|
| A Phase Map | 1,680 | 96 |
| B Migration | 624 | 52 |
| C Mechanism | 504 | 48 |
| **Total** | **2,808** | **196** |

Each world remains a one-core Slurm task.  The aggregate 196-core throttle is
well below the ARC/QOS CPU limit observed before launch and can be reduced by
the scheduler/fair-share environment without changing the scientific design.
Because Owl's `MaxArraySize` is 1001, Module A is packaged as two 840-task
Slurm arrays whose local indices are both `0-839`, at 48 concurrent tasks each.
The second array has the frozen offset `PF_TASK_OFFSET=840`, mapping its Slurm
indices to logical experiment task IDs `840-1679`.  The sidecar records both
IDs plus the offset, and merge validation requires `slurm_id + offset =
logical_id`.  This preserves Module A's planned 96-task concurrency and exact
scientific task mapping while obeying Owl's scheduler limit.

## Production integrity

Production must satisfy all of the following:

1. clean Git worktree;
2. one final Stage-4 production commit;
3. all contracts and selected runtime artifacts verified against the Stage-4
   cryptographic freeze;
4. distinct output directory per module;
5. one primary shard, one trajectory shard, and one metadata sidecar per world;
6. 100% task-id coverage;
7. cryptographic shard/trajectory verification;
8. a single production Git commit within each module and the same production
   commit across all three modules;
9. no manual deletion/exclusion of failed worlds; correctness failures block
   analysis until repaired and rerun;
10. postprocessing writes an independent READY artifact for each module.

## Interpretation boundary

Stage 4 tests causal mechanisms inside the synthetic Pineland model.  It does
not by itself establish that a historical partner force exhibited the same
parameter values or mechanisms, and it does not independently justify a
specific real-world security-assistance policy.  Historical transport requires
separate measurement and validation work.
