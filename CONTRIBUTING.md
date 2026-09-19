# Contributing to Pineland

Pineland is both a software project and an active research program. Changes
therefore need to preserve more than code correctness: they must preserve the
scientific meaning of experiments, outputs, and provenance.

## Before changing the model

1. Read [docs/repository-layout.md](docs/repository-layout.md) for the
   source/evidence retention policy.
2. Read the documentation for the subsystem you are changing.
3. Check whether the affected study has a preregistration or freeze contract.
   A frozen confirmatory design must not be silently edited.

## Development setup

    python -m pip install -e ".[research,dev]"
    python -m pytest -q
    cargo test --workspace --manifest-path rust/Cargo.toml

For a narrow change, run the smallest relevant tests while iterating, then run
the broader applicable suite before committing.

## Scientific-change rules

- Keep exploratory, confirmatory, and held-out analyses distinguishable.
- Do not tune a synthetic mechanism against a historical outcome unless the
  governing protocol explicitly permits it.
- Preserve deterministic random-stream and matched-seed contracts.
- Add or update invariant tests when a mechanism changes.
- Record provenance for new empirical inputs.
- Prefer machine-readable contracts and result summaries to undocumented prose.
- Retain scientifically informative negative results and falsifications.

## Repository hygiene

Generated caches, build outputs, raw run panels, and temporary smoke products
should not be committed. Use:

    python scripts/cleanup_generated_artifacts.py

before deleting anything manually. The script is dry-run by default and refuses
to delete tracked files.

Large scientific panels normally remain outside Git; compact contracts,
falsification ledgers, audit records, and claim-supporting summaries should be
retained when appropriate.

## Pull requests

A useful pull request explains:

- what behavior or scientific contract changed;
- why the change is needed;
- which tests or validation checks were run;
- whether outputs or schemas changed;
- whether the change affects a frozen experiment or historical comparison.

Avoid mixing unrelated refactors with scientific mechanism changes when they
can be separated cleanly.
