# Release policy

Pineland separates **software releases** from **scientific freezes**. A version
number says which software snapshot is being distributed; a scientific freeze
says which exact code, contracts, inputs, and analysis rules produced a result.
They may point to the same commit, but they are not interchangeable.

## Software releases

Software releases use semantic-style tags such as `v0.14.0`.

- **Patch** releases repair implementation or documentation defects without
  intentionally changing scientific model semantics.
- **Minor** releases may add mechanisms, schemas, inference features, or
  research infrastructure while the project remains pre-1.0.
- **1.0.0** should be reserved for a deliberately public, documented, stable
  interface rather than merely the next chronological milestone.

Every public software release should have:

1. a clean Git commit and annotated tag;
2. a matching package version;
3. a changelog entry;
4. passing clean-clone CI;
5. a documented test/reproduction record;
6. a resolved license and citation file;
7. no required private data, credentials, or undocumented local state.

## Scientific freeze tags

Paper and confirmatory-study freezes should use descriptive annotated tags,
for example:

- `paper1-analysis-freeze-v1`
- `partner-force-stage3-freeze-v1`

A freeze tag should identify an exact commit and point to the governing
preregistration, manifest, or analysis contract. Never move or reuse a freeze
tag after results are generated from it.

If a post-freeze defect is discovered, preserve the original tag and create a
new freeze with a documented correction.

## GitHub Releases

GitHub Releases should be reserved for snapshots that another person can
reasonably install, inspect, or reproduce. Experimental commits and internal
checkpoint states do not need GitHub Releases.

The first public release should include:

- concise release notes;
- the exact commit/tag used for the first paper, if available;
- a statement of known limitations and non-uses;
- reproducibility instructions;
- citation instructions;
- links to frozen contracts rather than copied prose claims.

Large run panels should not be attached automatically. Prefer compact
machine-readable summaries, manifests, checksums, and external archival storage
for data that is too large for Git.

## Branches

`main` is the canonical integration branch. Research branches may move quickly
and may contain exploratory work. A public release is cut from a reviewed
`main` commit, not directly from an experimental worktree.

## Version-to-paper rule

Every paper, preprint, or externally circulated scientific result should cite
an exact commit or immutable tag. "Current main" is never a sufficient
reproducibility identifier.
