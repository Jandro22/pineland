# Repository layout and evidence policy

Pineland mixes executable model code with a large empirical research program.
The repository should keep the two easy to distinguish so that cleaning a
working tree never destroys scientific evidence.

## Canonical tracked material

- `src/` — Python model and analysis-facing API.
- `rust/` — native workspace source. Cargo `target*` directories are rebuildable
  and intentionally ignored.
- `tests/` — regression, exactness, and scientific-invariant tests. Historical
  one-off configs live under `tests/fixtures/legacy_configs/`, not at repo root.
- `scenarios/` — hand-authored simulation configurations.
- `docs/` — implementation/audit documentation and professor-facing packets.
- `studies/*/scripts/` and `studies/*/data/manifests/` — empirical ingestion and
  provenance definitions.
- `studies/research_program/general_theory_v1/` — theory contracts, analysis
  code, compact result summaries, status ledgers, and the native probe source.
- `studies/research_program/native_validation/` — retained native/Python parity
  certificates and other historical validation evidence.

## Generated but scientifically valuable material

Large run panels, case data products, study `runs/`/`results/`, and raw CSV
outputs are intentionally kept out of ordinary Git commits. They stay at their
stable paths for analysis and may be transparently NTFS-compressed by
`scripts/cleanup_generated_artifacts.py`. Compact JSON summaries, contracts,
falsification ledgers, and audit/status records should be committed when they
matter to a scientific claim.

Ignoring a generated result is not a license to delete it. Before removing a
research output, confirm that it is either reproducible from tracked inputs or
superseded by a retained result with equivalent provenance.

## Disposable local products

The following can be regenerated and should never accumulate in Git:

- Python/test caches (`__pycache__`, `.pytest_cache`, coverage caches).
- Cargo build directories (`rust/target`, `target-*`, nested probe targets).
- locally copied native extension binaries (`src/pineland_sim/_native/`).
- `tmp/`, `json/`, debug dumps under `artifacts/`, and rendered preview files.

Use a dry run first:

```powershell
python scripts/cleanup_generated_artifacts.py
```

Then apply cleanup once the candidates look correct:

```powershell
python scripts/cleanup_generated_artifacts.py --apply --safety-age-hours 6
```

The cleanup script refuses to delete a candidate containing Git-tracked files.

## Root-directory rule

The repository root is reserved for project entry points and metadata
(`README.md`, `pyproject.toml`, lockfiles, and VCS files). Ad-hoc configs,
certificates, experiment outputs, and reports belong in `tests/fixtures/`,
`studies/`, or `docs/` according to purpose.
