# Changelog

Pineland uses this changelog for human-facing software and research-platform
changes. Fine-grained scientific provenance remains in Git history, frozen
contracts, manifests, and study-specific ledgers.

## Unreleased

### Added (post-freeze: ETF resurrection, 2026-10)

- Autonomy-trap campaign: 66,576 paired production worlds (1,000 agents, 72
  localities, 64 seeds, 24 variants) testing when continued support leaves a
  partner force weaker than withdrawing it, with local (300-agent) replications,
  robustness, development-dose and fresh-seed checks. Results, tables and
  figures in `experiments/etf_resurrection/findings/`; campaign tooling
  (builder, node runner, collector, Slurm scripts) in
  `experiments/etf_resurrection/arc/`.
- Use-it-or-lose-it institutional learning in the Stage-4 harness
  (`partner_force_support.learning_rate_per_30d`, `learning_reference_share`,
  per-channel capacity indexes) and per-channel withdrawal delays.
- Event-keyed random streams (`combat.rng_event_resync`) so paired ON/OFF twins
  stay synchronized after they diverge.
- The `multichannel_v6` organized-action architecture: operational-reach armed
  strikes, intelligence-gated targeting, speculative sweeps, insurgent tempo.
- Territorial contestation (institutional erosion under insurgent dominance,
  shadow governance, a Lanchester coercive balance, police reinsertion gating),
  insurgent organization splits, defection cascades, and abandonment of
  government posts.
- Locality telemetry and the NATO-style paired-branch situation map.
- Presentation figures (learning dose-response, dependency valley, mechanism).

### Changed (post-freeze)

- The model on `main` now includes the post-freeze repairs above and does not
  reproduce the frozen Stage-4/5 datasets bit for bit. The frozen paper cycle
  is pinned to the git tag `paper-freeze-2026-09-21`.
- Default `combat.organized_action_architecture` is `multichannel_v6`
  (previously `multichannel_v5`), and `combat.rng_event_resync`,
  `combat.defection_base_hazard_per_day` and `logistics.security_pursuit_weight`
  have non-zero defaults. Set them back to reproduce older behavior.
- The Stage-4 harness applies cell-level learning and the SHA-256 and
  information paths were optimized with bit-identical hashes.

### Fixed (post-freeze)

- Patrol-presence memory is clamped at full coverage (a state-range crash at
  day 240), the command-collapse assay shock now breaks cohesion and readiness,
  and the particle filter initializes the new random-stream fields so the whole
  Rust workspace builds.
- The force-generation stress cell of `test_binding_constraint_assay` was
  rescaled (capacity 0.15 to 0.35, training boost 0.05 to 0.12): the repaired
  model has realistic combat losses (several times the old combat-dead world's),
  so the original cell could no longer cover the replacement deficit it was
  meant to cross. All Rust workspace tests pass.

### Added

- Finalized the first Partner-Force paper cycle, including the review-rebuilt
  relief-yield-retention manuscript, deterministic figure set, anonymized
  submission package, manuscript evidence validator, rendered-document QA, and
  paper-facing freeze documentation.
- Completed Partner-Force Autonomy Stage 4: 2,808 production worlds across the
  autonomy phase map, bottleneck-migration, and substitution-versus-development
  modules, with complete cryptographic task/shard provenance.
- Added the Stage-4 integrated protocol, run ledger, preregistered paper-level
  secondary-analysis plan, post-completion interpretation memo, and compact
  tracked evidence package.
- Public-release preparation: release, archive, and subsystem-status policies.
- GitHub contribution and security-reporting scaffolding.
- Full-history Gitleaks configuration and release security-scan wrapper.
- Explicit redistribution/license dispositions for the historical case source manifests.
- Windows/Python 3.14 pytest temp-root hardening and cross-platform CI coverage.
- Rust workspace and full-history secret scanning in GitHub CI.
- Clean-clone/publication guards for missing Rust modules, restricted source
  artifacts, and historical generated/raw-data blobs.

### Changed

- Put the repository into maintenance mode after the 2026-09-21 scientific
  freeze; future changes should be corrections, reproducibility/packaging
  repairs, or peer-review revisions rather than new exploratory development.
- Partner-Force Autonomy is now documented as a completed integrated Stage-4
  research program rather than an active Stage-3-only discovery program.
- The default development branch is now `main`.
- The public README is organized around the current research program rather
  than a chronological list of implementation phases.
- Python package metadata identifies the project repository and primary author
  consistently with `CITATION.cff`.
- The public software license is finalized as Apache License 2.0, with a root
  `NOTICE` file for project attribution.

## 0.13.0 - development line

The package metadata currently reports `0.13.0`, but this version has not yet
been cut as a Git tag or GitHub Release. The development line adds the
belief-based organized-action layer, the Research-v1 recovery program, the
General Theory v1 program, and the Partner-Force Autonomy Stage-3 research
architecture.

Before a public release, the exact release commit, test evidence, paper
reproduction status, and license choice should be frozen and recorded.

## Historical tags

Git tags `v0.2.0` through `v0.12.0` are retained as historical development
snapshots. They should not be interpreted as peer-reviewed scientific releases
unless a corresponding study artifact explicitly says so.
