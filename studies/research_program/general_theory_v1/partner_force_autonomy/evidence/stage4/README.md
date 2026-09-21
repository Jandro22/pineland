# Stage-4 compact evidence package

This directory retains the **small, claim-supporting outputs** from the completed
Partner-Force Autonomy Stage-4 campaign. The 2,808 raw production worlds and
large merged panels remain outside ordinary Git history under the repository
evidence policy.

The package is intended to make the GitHub repository sufficient to audit the
headline Stage-4 claims without committing the large HPC output tree.

## Completion manifests

- `READY_STAGE4_INTEGRATED.json` — final 2,808-world integrated READY artifact.
- `READY_PHASE_MAP.json` — Phase-Map module completion/hashes.
- `READY_BOTTLENECK_MIGRATION.json` — Bottleneck-Migration module completion/hashes.
- `READY_SUBSTITUTION_DEVELOPMENT.json` — Substitution-vs-Development module completion/hashes.
- `READY_STAGE4_PAPER_SECONDARY.json` — completion artifact for the precommitted
  paper-level secondary analysis.
- `stage4_paper_secondary_summary_v1.json` — analysis input/output hashes and
  frozen paper-level estimands.

## Compact result tables

- `phase_cell_summary_v1.csv` — 140 Phase-Map cell summaries, bootstrap
  intervals, seed fractions, and robust regime classifications.
- `phase_support_transition_intervals_v1.csv` — observed support-intensity sign
  crossings on the preregistered grid.
- `phase_capacity_transition_intervals_v1.csv` — observed indigenous-capacity
  sign crossings.
- `mechanism_cell_summary_v1.csv` — absolute Module-C treatment-cell summaries.
- `mechanism_mode_contrasts_v1.csv` — matched development-minus-substitution and
  hybrid-minus-substitution contrasts with deterministic bootstrap intervals.
- `migration_target_match_summary_v1.csv` — bottleneck-migration summaries by
  starting structure, support target/intensity, and observed target match.

## Provenance

- production commit: `e369c107f4465ce8cd385a366cafca8c28c04b65`
- final postprocessing commit: `7697e6eac83248c7bc03830e58d94a2d878c6635`
- precommitted paper-analysis commit: `9b0e975c7e4073f2f5abd94e72cd125beb75f20d`
- production worlds: **2,808 / 2,808**
- final integrity sweep: **zero missing/duplicate logical IDs, SHA mismatches,
  row-count errors, commit mismatches, or filename/metadata mapping errors**.

`MANIFEST.json` records the SHA-256 of every retained evidence file.

Interpretation belongs in
[`../../STAGE4_RESULTS_INTERPRETATION_2026-09-20.md`](../../STAGE4_RESULTS_INTERPRETATION_2026-09-20.md),
not in the READY manifests themselves.
