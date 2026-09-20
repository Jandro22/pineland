# Git-history publication review — 2026-09-19

The current Pineland tree is much cleaner than its early development history.
Changing repository visibility, however, exposes **reachable Git history**, not
just the files present at `HEAD`. This review therefore treats historical
blobs as a separate public-release surface.

## Current finding

The history contains several large files that are no longer part of the active
tracked tree. The largest observed historical blobs include:

| Approx. size | Historical path | Disposition before public release |
|---:|---|---|
| 74.4 MiB | `artifacts/native_presence_debug34.json` | generated debug artifact; remove from public history |
| 74.4 MiB | `artifacts/native_presence_debug35.json` | generated debug artifact; remove from public history |
| 73.2 MiB | `artifacts/debug_native_seed_max_init.json` | generated debug artifact; remove from public history |
| 50.4 MiB | `json/checkpoint_0000/rank_0000.pld` | generated checkpoint; remove from public history |
| 37.3 MiB | Nigeria external-validation UCDP raw archive | third-party raw source; remove from public history and retain provenance/hash |
| 14.8 MiB | Nigeria external-validation WorldPop raw archive | third-party raw source; remove from public history and retain provenance/hash |
| 13.4 MiB | historical civilian-harm cross-check CSV | generated/research evidence; review for external archival retention |
| 11.1 MiB | construct-representation audit JSON | generated/research evidence; review for compact replacement or external archive |

No history rewrite has been performed as part of this review.

The path-level audit currently classifies **983** reachable historical blobs in
publication-sensitive locations:

- 968 under the old `artifacts/` development/debug tree;
- 7 under the old `json/` generated-output tree;
- 4 locally built native binaries/symbol products under
  `src/pineland_sim/_native/`;
- 4 raw external-validation source artifacts under the Nigeria case.

This concentration is useful: most of the historical publication debt is in a
small number of path families rather than being scattered through model source.

## Why this matters

The current `.gitignore` prevents new raw data, build products, and ordinary
generated outputs from being added accidentally. It does not make blobs from
old commits disappear. A public repository would make historical raw data and
debug/checkpoint artifacts part of the publication surface even though a fresh
checkout no longer contains them.

This is both an organizational and rights-management concern. Raw third-party
data should not be exposed merely because an early private commit happened to
contain a copy.

## Recommended pre-public strategy

Do **not** rewrite the active scientific history during current experiments.
Perform one deliberate history-publication operation before the first immutable
paper/release freeze:

1. create a complete private archival copy of the original repository history
   (mirror/bundle plus cryptographic checksum);
2. preserve that archive under controlled storage for provenance;
3. produce a sanitized publication history that removes generated debug/build
   products and raw third-party data while retaining source code, contracts,
   compact evidence, and meaningful commit structure;
4. verify all branches/tags intended for publication against the same history
   audit and secret scan;
5. run clean-clone tests against the sanitized repository;
6. only **after** sanitization, create the paper freeze and first public release
   tags that outside work will cite.

Because a history rewrite changes commit identifiers, it should happen before
the first externally cited immutable Pineland commit. Existing private
development identifiers can remain recoverable through the preserved private
archive.

If preserving old public-facing SHAs becomes important before sanitization is
complete, publishing a new clean repository from a vetted snapshot is safer
than exposing an unsanitized private history.

The first-pass history-removal candidates are therefore the historical contents
of:

- `artifacts/`;
- `json/`;
- `src/pineland_sim/_native/` (built products only; the active source remains
  elsewhere);
- `studies/research_program/external_validation/*/raw/`.

Two additional large historical research products outside those families
(`civilian_harm_ucdp_event_crosscheck_v1.csv` and
`construct_representation_audit_v1.json`) should be reviewed individually for
external archival retention before a sanitization rule is finalized.

## Repeatable audit

Run:

    python scripts/audit_git_history_blobs.py

The audit reports:

- blobs at least 10 MiB by default;
- historical paths in generated-output/build/data locations even when smaller.

Immediately before publication, use:

    python scripts/audit_git_history_blobs.py --strict

after the publication history has been deliberately sanitized.

This is separate from `scripts/scan_git_history_secrets.py`: a blob can be
free of credentials and still be inappropriate to publish because it is
generated clutter or third-party source data.
