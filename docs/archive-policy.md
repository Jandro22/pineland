# Archive policy

The goal of archiving is to make the active repository easier to understand
without destroying scientific provenance.

Pineland classifies material into four categories.

## 1. Canonical current material

Code, tests, contracts, scenarios, and documentation that a new researcher
should use today remain in their normal top-level locations.

## 2. Superseded but scientifically meaningful material

Old implementations, replaced protocols, historical schemas, and falsified
theory variants may be moved to an explicit archive when they no longer belong
on the active path.

Archived material should retain:

- its original filenames when practical;
- a short README explaining why it was archived;
- the replacement path, if one exists;
- the date of archival;
- the last commit where it was canonical.

An archive is not a trash directory. If a file has no scientific, historical,
or reproducibility value, deletion is preferable.

## 3. Generated scientific evidence

Large run panels, raw simulation outputs, processed historical products, and
other generated evidence generally should **not** be moved into a Git archive.
Keep them at stable ignored paths, on appropriate research storage, or in a
formal external archive. Track compact manifests, hashes, contracts, and result
summaries needed to establish provenance.

Ignoring generated evidence in Git is not permission to delete it.

## 4. Disposable products

Build outputs, caches, temporary smoke products, duplicated downloads, and
other reproducible scratch products may be deleted under the repository hygiene
rules.

Use `scripts/cleanup_generated_artifacts.py` before manual bulk deletion.

## Archive manifest

When the first substantial archival pass happens, create
`archive/manifest.json` with one entry per archived group:

    {
      "path": "archive/legacy_native",
      "status": "superseded",
      "superseded_by": "rust/",
      "archived_at": "YYYY-MM-DD",
      "reason": "pre-Rust native implementation",
      "last_canonical_commit": "<git commit>"
    }

Do not create archive entries speculatively. First verify that the candidate is
actually superseded and that no active study imports or references it.

## Initial candidates for later review

The following are **review candidates, not approved deletions**:

- superseded General Theory development artifacts once the current theory
  program is frozen;
- older protocol/document versions whose provenance matters but whose presence
  in the active documentation path causes ambiguity.

No active research directory should be reorganized during a confirmatory or
long-running experiment unless the experiment's paths and hashes are already
fully frozen.

### Explicit non-candidate: `native/`

`native/pineland_kernels.rs` is **not currently archival material**. It remains
the source for the Python native-kernel build path used by
`studies/research_program/scripts/build_native_kernels.py` and exactness
batteries. The newer `rust/` workspace is the canonical standalone runtime,
but the older native-kernel path still has an active verification role.

Revisit `native/` only after that build/exactness dependency is deliberately
retired or migrated.

The first concrete General Theory inventory is recorded in
[`docs/general-theory-archive-review.md`](general-theory-archive-review.md).
