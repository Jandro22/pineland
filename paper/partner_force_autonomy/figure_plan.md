# Figure and table plan

## Figure 1. Conceptual mechanism

**Status:** Generated as `figures/figure1_conceptual.{png,pdf}`.

**Purpose:** Introduce the relief-yield-retention framework before showing
simulation results.

Flow:

```text
targeted assistance
        -> constraint relief
        -> system yield
        -> retained indigenous capability
```

The visual annotates the relief-to-yield transition with headroom and the
yield-to-retention transition with support-enabled demand and constraint
migration. It should make clear that migration is a mechanism, not itself the
measure of success.

## Figure 2. Autonomy-Trap Phase Map

**Status:** Generated as `figures/figure2_phase_map.{png,pdf}`.

**Source:** `phase_cell_summary_v1.csv`

Facets by starting structural family. Horizontal axis is support intensity.
Vertical axis is indigenous capacity level. Cell fill should represent mean
terminal autonomy effect at +360d. Overlay a symbol for initial effectiveness at
+30d and a separate outline for robust trap classification.

This figure should make three facts immediately visible:

1. effective direct support is overwhelmingly autonomy-eroding;
2. the penalty generally increases at high support intensity;
3. positive-mean command cells are narrow and statistically unstable.

## Figure 3. Capability-autonomy tradeoff by support intensity

**Status:** Generated as `figures/figure3_intensity_tradeoff.{png,pdf}`.

**Source:** `phase_cell_summary_v1.csv`

Two lines or point series by support intensity:

- mean +30d composite-capability effect;
- mean +360d capped indigenous-autonomy effect.

This is the cleanest visual representation of the autonomy trap.

## Figure 4. Bottleneck migration transition matrix

**Status:** Initial matched-target migration figure generated as
`figures/figure4_matched_migration.{png,pdf}`. A full transition matrix remains
planned if the archived world-level migration path table is promoted into the
paper evidence package.

**Source:** `migration_target_match_summary_v1.csv` plus Module-B world summaries.

Rows are observed pre-withdrawal bottlenecks. Columns are modal or terminal
post-treatment bottlenecks. Separate matched-target treatments from unmatched
treatments.

Headline annotations:

- command matched: 38/38 migrate, median 7d;
- force generation matched: 46/46 migrate, median 7d;
- logistics matched: 0/85 migrate.

## Figure 5. Substitution versus development

**Status:** Generated as `figures/figure5_mode_contrasts.{png,pdf}`.

**Source:** `mechanism_mode_contrasts_v1.csv`

Forest plot of development-minus-substitution and hybrid-minus-substitution
effects on +360d q by target, severity, and intensity. Include 95% bootstrap
intervals.

The logistics contrasts should be visually central because all four
development-minus-substitution intervals exclude zero.

## Figure 6. Local capacity versus system autonomy

**Status:** Generated as `figures/figure6_local_system_divergence.{png,pdf}`.

**Source:** `mechanism_mode_contrasts_v1.csv` and `mechanism_cell_summary_v1.csv`

Use force generation and command as paired examples. Plot indigenous subsystem
gain on the horizontal axis and whole-system q effect on the vertical axis.
Annotate the post-treatment binding constraint.

This figure demonstrates that local development is not equivalent to system
autonomy when the bottleneck migrates.

## Table 1. Integrated design

| Module | Cells | Seeds per cell | Worlds | Main estimand |
|---|---:|---:|---:|---|
| Phase Map | 140 | 12 | 1,680 | +30d capability and +360d indigenous autonomy |
| Bottleneck Migration | 52 | 12 | 624 | Persistent migration and migration time |
| Substitution vs Development | 42 | 12 | 504 | Matched treatment-mode contrasts |
| Total | 234 | 12 | 2,808 | Integrated mechanism program |

## Table 2. Relief, yield, migration, and retention

**Status:** Implemented in `manuscript.md`.

**Source:** Weighted post-completion aggregation of
`migration_target_match_summary_v1.csv`.

This table makes the conceptual distinction explicit: command and force
generation both migrate universally in observed-matched worlds, but their
short-run system yields differ; logistics produces the largest mean supported
yield of the three while remaining binding and eroding terminal autonomy.

## Table 3. Headline results

**Status:** Implemented in `manuscript.md`.

Compact table for the abstract/discussion numbers: 96/106 traps, 53 robust
traps, 0 robust builders, 38/38 command migration, 46/46 force-generation
migration, 0/85 logistics migration, and the range of logistics development
contrasts.

## Table 4. Robustness and evidentiary status

**Status:** Smooth-aggregator sign robustness implemented in `manuscript.md` for
the observed-matched Migration worlds. Evidentiary status remains explicit in
Table 3 and `claim_evidence_matrix.md`.

The tracked Migration package supports direct hard-minimum versus arithmetic,
geometric, and harmonic sign comparison. Across the 169 observed-matched worlds,
167, or 98.8 percent, are sign-concordant under each smooth aggregator.

## Figure 7. Coordinated development and the rising-tide test

**Status:** Reserved until the prospectively frozen Stage-5 campaign completes.

**Source:** Stage-5 analysis outputs generated by
`analyze_stage5_rising_tide.py`.

The final form should show both:

1. equal-total-effort breadth premiums, especially comparing the near-tie
   structure with the three dominant-bottleneck structures; and
2. equal-channel-dose factorial interactions for the pairwise and three-way
   coordinated-development arms.

The figure must report all preregistered structure-by-intensity results rather
than displaying only positive complementarity cells.
