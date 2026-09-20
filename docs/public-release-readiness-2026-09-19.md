# Public-release readiness snapshot — 2026-09-19

This is a dated engineering/repository snapshot, **not** a declaration that
Pineland is ready to become public. It records what was actually tested from a
fresh checkout and which blockers remain.

Release-prep commit tested: `f36934c5094fa62f25899230f8afa2393a8f4ced`

Integrated `main` baseline:
`dfdf2370ef9c4a367a13a210c0d5a7b8b05fcd6c`

## Fresh-clone checks

A separate temporary clone with no ignored research outputs or local build
state was created on Windows using Python 3.14.

### Passed

- `python -m pip install -e ".[research,dev]"`
- repository-local `python pineland.py --help`
- installed `pineland-sim --help`
- `python scripts/public_release_audit.py`
  - 8 passes
  - 4 warnings
  - 0 failures before the Rust-module guard was added
- focused clean-clone regression battery:

      python -m pytest +        tests/test_recovery.py +        tests/test_research_v1_runner.py +        tests/test_state_estimation.py +        tests/test_empirical.py -q

  Result: **50 passed**.

- clean-clone portable regression suite matching the public CI exclusions:

      python -m pytest -q +        --ignore=tests/test_afghanistan_acled_mapping.py +        --ignore=tests/test_afghanistan_case.py +        --ignore=tests/test_afghanistan_filtered_state_estimation.py +        --ignore=tests/test_afghanistan_historical_inputs.py +        --ignore=tests/test_case_readiness.py +        --ignore=tests/test_historical_database_v2.py +        --ignore=tests/test_mechanism_evidence.py +        --ignore=tests/test_predictive_competition_gate.py +        --ignore=tests/test_research_program.py

  Result: **681 passed, 2 skipped** in 320.45 seconds on the clean Windows
  checkout with numerical libraries limited to one thread.

- `python -m pip check`: **no broken requirements found**.

- standard Python wheel build:

      python -m pip wheel . --no-deps

  Result: `pineland_coinsim-0.13.0-py3-none-any.whl` built successfully.
  Wheel metadata reports Alejandro Grenier as author, Apache-2.0 as the
  software license, and the canonical GitHub repository/issue URLs.

- literal Python README quick start:

      pineland-sim run --agents 1000 --days 30 --output outputs/readme-smoke

  Result: exit 0 from the clean checkout and a complete forensic run product.

- Paper-1 software/reproduction smoke:

      python pineland.py reproduce paper1 --profile smoke

  Result: exit 0, output written under `outputs/research-v1/`, with status
  `synthetic_only_no_historical_claim`.

- Dependency-free high-signal full-history credential scan:

      python scripts/scan_git_history_secrets.py --builtin-only

  Result: pass.

The built-in history scan is a fallback, not a substitute for the configured
Gitleaks CI gate.

## Critical blocker: clean-clone Rust build

The fresh-clone command:

    cargo test --workspace --locked --quiet --manifest-path rust/Cargo.toml

fails immediately with Rust error `E0583`:

    rust/pineland-model/src/lib.rs
    pub mod assays;

references `rust/pineland-model/src/assays.rs`, but that source file is not in
the committed tree represented by this snapshot.

The active research checkout contains untracked:

- `rust/pineland-model/src/assays.rs`
- `rust/pineland-model/tests/safeguards_and_assays.rs`

Those files appear to be substantive Stage-3 v2 assay code and tests, not
generated debris. They are being left untouched in the active research
worktree. The release-prep branch must not silently copy or freeze active
scientific work merely to make CI green.

**Disposition:** public release and merge of a supposedly green release
candidate are blocked until the research owner deliberately commits, removes,
or otherwise resolves the `assays` module dependency on `main`. The public
release audit now checks external Rust module declarations so this class of
clean-clone defect fails early.

## Rights / redistribution status

Source manifests now explicitly distinguish confirmed redistribution from
conservative review-required cases. Remaining audit warnings are:

- Afghanistan: 1 of 5 sources remains `review_required`.
- Colombia: 6 of 9 sources remain `review_required` (CNMH Geoportal/ArcGIS
  artifacts; public access/download was identified, but an explicit
  dataset-level redistribution grant was not verified).
- Vietnam: 1 of 7 sources remains `review_required` (underlying NARA record
  series; item-level rights can vary).

These warnings do not require deleting the case packages. They mean the public
repository should retain provenance, scripts, and hashes while withholding
source artifacts whose redistribution rights are not established.

## Other deliberate blockers / unfinished release work

- Reachable private Git history still contains generated/debug/build and raw-data
  blobs that are absent from the current tree. The 2026-09-19 history audit
  found 3,871 reachable blobs, including 8 blobs at least 10 MiB and 983 paths
  under publication-sensitive generated/data locations. The largest are
  generated debug JSONs around 74 MiB and a generated checkpoint around 50 MiB.
  A private archival copy plus a deliberate sanitized publication history is
  required before visibility changes.
- `v0.13.0` has not been cut as an immutable software tag or GitHub Release.
- The first-paper scientific analysis/freeze tag does not yet exist.
- The public software license is finalized as Apache License 2.0; the root
  `LICENSE`, `NOTICE`, package metadata, README, and citation metadata should
  remain synchronized through release.
- Full public CI has not yet passed on the eventual release commit.
- The configured Gitleaks scan should pass on the release candidate before
  visibility changes.
- General Theory archival/reorganization should wait for scientific freeze;
  the current review found no active evidence that is safe to delete merely
  for tidiness.

## Current decision

**Do not make the repository public yet.**

The repository is substantially closer to public-release shape, and the
clean-clone Python path is healthy. The missing committed Rust module is a
concrete release blocker that should be resolved through the active scientific
development process rather than patched around in release-prep.
