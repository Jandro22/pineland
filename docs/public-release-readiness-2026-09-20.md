# Public-release readiness update — 2026-09-20

This note supersedes the Stage-3-specific research-state discussion in
`public-release-readiness-2026-09-19.md`. It does not replace the permanent
release checklist or security/data-redistribution policies.

## Current scientific state

The Partner-Force Autonomy research line is no longer blocked at Stage 3.
Integrated Stage 4 completed on VT ARC with **2,808/2,808 production worlds**.
The final dataset passed a complete post-run integrity sweep with zero missing
or duplicate logical task IDs, zero content-hash mismatches, zero row-count
errors, and zero source-commit/provenance mismatches.

The repository now retains:

- frozen Stage-3 and Stage-4 contracts;
- Lean formalization of the autonomy coordinate;
- Stage-4 production, merge, postprocessing, and finalization code;
- a run ledger that records scheduler layout, correctness repairs, and job IDs;
- the precommitted paper-level analysis plan and implementation;
- a post-completion interpretation memo;
- compact READY manifests and claim-supporting Stage-4 summary tables under
  `studies/research_program/general_theory_v1/partner_force_autonomy/evidence/stage4/`.

Large raw HPC panels remain intentionally outside ordinary Git history.

## Repository/publication state

The repository uses Apache License 2.0 with a root `NOTICE`, dedicated
`SECURITY.md`, contribution templates, public-release audit scripts, Gitleaks
configuration, source-redistribution manifests, and the unified
`pineland-ci.yml` workflow.

### Consolidation-tree audit evidence

On the Stage-4 consolidation tree, the inexpensive public-release audit
reported **11 passes, 5 warnings, and 0 failures**. Confirmed passes include:

- required public/release metadata present;
- package/CITATION version agreement at `0.13.0`;
- Apache-2.0 agreement across package metadata, `CITATION.cff`, `LICENSE`,
  README, and `NOTICE`;
- main-branch unified CI badge;
- no Unicode replacement characters in tracked text;
- no tracked cache/build-output paths caught by the release audit;
- no high-signal secrets in the current tree;
- all tracked external Rust module declarations resolve;
- no tracked source artifacts whose manifests prohibit/default-block
  redistribution;
- all historical source manifests use the controlled redistribution vocabulary.

Focused release-audit tests passed **7/7**, ARC campaign tests passed **17/17**,
the focused Python CI set passed **50/50**, and the portable Python suite passed
**688 tests with 2 skips**.

The Rust consolidation gate also passed in full: workspace formatting was
clean, workspace Clippy passed with warnings denied, the safeguards/assays
suite passed **7/7** in 815.21 seconds, and the final 12-world
treatment-relevance integration gate passed **1/1** in 573.06 seconds. The
complete `cargo test --workspace --locked` chain exited successfully.

The full-history Gitleaks scan covered **398 commits** and reported **no
unallowlisted leaks**.

The historical-blob publication audit still identifies old large/debug/raw
objects in reachable history, including historical generated artifacts and raw
external-validation archives. This remains a blocker for changing repository
visibility without history sanitization/review; it is not a blocker for keeping
the private GitHub development repository synchronized.

Remaining non-failure release-audit warnings are expected pre-release items:

- no `v0.13.0` software tag yet;
- one Afghanistan, six Colombia, and one Vietnam source-manifest entries remain
  `review_required` for redistribution;
- the audit was run before the consolidation commit, so the worktree was
  intentionally dirty.

Public release remains subject to the permanent gates in
`docs/public-release-checklist.md`, especially:

1. clean-clone CI from the exact release commit;
2. full-history secret scan;
3. third-party/historical data redistribution review;
4. verification that no generated/raw restricted datasets have entered Git;
5. final citation/version/release metadata review.

## Scientific interpretation boundary

Stage-4 numerical results are synthetic-model causal findings. Completing and
publishing the repository does **not** convert Pineland parameters or transition
regions into empirical estimates for Afghanistan, Iraq, Mali, or another
historical force. Historical validation remains an explicit next research task.
