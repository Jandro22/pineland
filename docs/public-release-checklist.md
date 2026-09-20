# Public release checklist

This checklist is the gate for changing Pineland from a private research
repository into a public research artifact. It is intentionally stricter than
"the code runs on the maintainer's machine."

## Scientific freeze

- [ ] First-paper claims and estimands are frozen.
- [ ] The exact analysis commit is identified by immutable tag.
- [ ] Confirmatory/held-out analyses are distinguishable from exploratory work.
- [ ] Frozen contracts and manifests agree with the executed configuration.
- [ ] Known negative/falsifying results needed to interpret the claims are retained.
- [ ] The paper's tables/figures can be traced to reproducible artifacts.

## Clean-clone reproducibility

- [x] Fresh clone installs on a documented supported Python version
      (Python 3.14 clean-clone verification on 2026-09-19).
- [ ] Rust workspace builds from the checked-in lockfile/toolchain.
- [ ] Public CI passes from a clean clone.
- [ ] Linux Python, Windows Python, and Rust CI jobs pass on the release candidate.
- [ ] README quick-start commands are tested literally.
      The Python quick-start command has passed from a clean clone; the native
      Rust quick start remains blocked by the missing committed `assays`
      module described in the dated readiness snapshot.
- [x] Small reproduction/smoke profile completes without private files.
- [ ] Paper reproduction either completes publicly or documents required archived inputs.
- [ ] Required random seeds, schemas, and environment information are recorded.

## Repository organization

- [ ] Active code and docs are clearly separated from superseded material.
- [ ] Archive candidates have been reviewed under `docs/archive-policy.md`.
- [ ] No generated cache/build/smoke products are tracked accidentally.
- [ ] Large generated panels use manifests/checksums rather than unnecessary Git blobs.
- [ ] Historical case directories follow understandable, documented conventions.
- [x] The canonical role of `pineland.py` versus `pineland-sim` is documented.
- [x] The status of `native/` is resolved or explicitly documented.

## Security, privacy, and redistribution

- [ ] Full Git history is scanned for secrets, credentials, tokens, private identifiers,
      and accidentally committed configuration.
- [ ] Reachable Git history is reviewed for raw third-party data and obsolete
      generated/debug/build blobs, not just credentials.
- [x] Current tree is scanned separately from history.
- [ ] No CUI, export-controlled, restricted, or otherwise non-public material is present.
- [ ] Every redistributed third-party dataset has compatible licensing/terms.
- [x] Historical manifests identify sources without tracking source artifacts
      whose recorded redistribution state is restricted or unresolved.
- [ ] Personal contact information is intentional.

Historical-source decisions should follow
[`docs/data-redistribution.md`](data-redistribution.md).

The full-history credential scan is:

    python scripts/scan_git_history_secrets.py

It uses the repository's narrow `.gitleaks.toml` checksum allowlists and
redacts detected values from reports.

The historical-blob/publication-surface audit is:

    python scripts/audit_git_history_blobs.py

See [`docs/git-history-publication-review.md`](git-history-publication-review.md)
for the current findings and the recommended pre-public sanitization strategy.

## Licensing and attribution

- [ ] Final software license is explicitly chosen (currently MIT; Apache-2.0 remains
      an option before outside contributions).
- [x] `LICENSE`, package metadata, and README agree on the current MIT license.
- [x] `CITATION.cff` identifies the current package version and authorship consistently.
- [ ] Third-party code/assets retain required notices.
- [ ] Contribution terms are clear before accepting outside contributions.

## Public-facing scientific communication

- [ ] README states what Pineland is and is not.
- [ ] Subsystem status distinguishes implementation, validation, and current research use.
- [ ] Historical validation claims are no stronger than retained evidence.
- [ ] "Synthetic result" and "historical finding" are not conflated.
- [ ] Government/operational use is framed as research and analytical experimentation,
      not validated prediction or decision authority.
- [ ] Virginia Tech Advanced Research Computing (ARC) is expanded on first public use.

## Release mechanics

- [ ] Package version, changelog, tag, and GitHub Release agree.
- [ ] Release commit is clean.
- [ ] Full test/reproduction record is retained.
- [ ] Release notes list known limitations.
- [ ] DOI/archive strategy is decided if the paper needs a citable immutable snapshot.
- [ ] Repository visibility changes only after the release candidate passes this checklist.

The inexpensive repository-only portion of this gate can be rerun at any time:

    python scripts/public_release_audit.py

Immediately before release, run it with `--strict` after resolving every
warning that is relevant to public distribution.

The latest dated engineering snapshot is
[`docs/public-release-readiness-2026-09-19.md`](public-release-readiness-2026-09-19.md).

## After publication

- [ ] Define whether the project is actively maintained or in maintenance mode.
- [ ] Record the supported branch/version.
- [ ] Preserve paper-producing tags indefinitely.
- [ ] Do not promise operational suitability unsupported by validation.
