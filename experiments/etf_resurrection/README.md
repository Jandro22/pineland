# ETF resurrection: model repair and the autonomy-trap campaign

This directory holds the post-freeze work on the Partner-Force Autonomy
question: first repairing model failures that made counterfactual comparisons
uninformative, then running a large paired-counterfactual campaign on one
question.

> When does continued external support leave a partner force **weaker** than
> withdrawing it?

Headline, in one paragraph: if a partner's institutions learn by doing (a
channel's capacity grows when the partner serves itself and fades when outsiders
serve for it), continued support turns from neutral-to-mildly-helpful into
harmful. The harm deepens with the learning rate, is worst at intermediate
support doses (the *dependency valley*), and is reversed only by very large
support or by building the partner's own binding capacity. The mechanism is an
**assumption** of the experiment, not a finding; see *Limits* below.

Full numbers and tables: [findings/RESULTS.md](findings/RESULTS.md).

## What is in here

| Path | Purpose |
|---|---|
| [findings/](findings/) | Results write-up, analysis tables, summary CSVs and figures |
| [arc/](arc/) | Campaign builder, per-node runner, collector, local analysis, Slurm scripts |
| `plot_*.py` | Figure scripts (`plot_dose_valley`, `plot_learning_response`, `plot_mechanism`, `plot_locality_map`, `plot_dose_response`) |
| `validate_seeds.py` | Multi-seed paired ON/OFF validation for a cell, with `--dose`, `--patch`, `--withdrawal` |
| `dose_response.py`, `autonomy_phase_map.py` | Dose-response and phase-map analysis |
| `withdrawal_sequencing.py` | Sequenced-withdrawal experiment: which channel should go last |
| `sensitivity_morris.py`, `stylized_facts.py` | Morris screening and pattern-oriented checks of the v6 model |
| `inventory.py`, `compare_replay.py` | Shard audits and byte-exact replay comparison |
| `quick.sh`, `quick3.sh`, `fullcheck.sh` | Low-resource smoke and full-horizon checks used during the repair |
| [contracts/](contracts/) | Single-cell v6 engineering-smoke contracts |

Raw run output (`results/`, `raw/`, `data/`) is not tracked.

## The model switches the experiments depend on

The campaigns use the `multichannel_v6` organized-action architecture and the
following settings, which are the defaults on this branch:

| Setting | Meaning |
|---|---|
| `combat.organized_action_architecture = "multichannel_v6"` | operational-reach armed strikes, intelligence-gated targeting, insurgent tempo |
| `combat.rng_event_resync = 1.0` | each random stream is re-seeded per event from (stream, event time, locality), so ON/OFF twins stay synchronized after they diverge |
| `combat.strike_speculative_fraction = 0.4` | share of strike sweeps that are speculative and can find nothing |
| `combat.defection_base_hazard_per_day = 0.002` | defection and government post abandonment under insurgent pressure |
| `partner_force_support.learning_rate_per_30d` | institutional learning rate (0 = no learning; the campaigns sweep 0 to 1) |
| `partner_force_support.learning_reference_share = 0.9` | share of the work the partner must do itself for capacity to grow |

Institutional learning is applied by the Stage-4 harness
(`rust/pineland-model/examples/partner_force_autonomy_stage3.rs`): each
telemetry step it moves a capacity index per channel by
`exp(rate * (own_share - reference_share) * elapsed_days / 30)`, clamped to
[0.25, 1.5], where `own_share` is the partner's own service divided by its own
plus outside service in that channel.

## Reproducing the results

### Local, small worlds (minutes to hours, no cluster)

    cargo build --release -p pineland-model --example partner_force_autonomy_stage3 --manifest-path rust/Cargo.toml
    python experiments/etf_resurrection/arc/build_campaign.py \
        --design studies/research_program/general_theory_v1/partner_force_autonomy/contracts/stage4_autonomy_phase_map_v1.json \
        --out experiments/etf_resurrection/results/local --local --seeds 16
    cp rust/target/release/examples/partner_force_autonomy_stage3 experiments/etf_resurrection/results/local/bin
    python experiments/etf_resurrection/arc/run_bundle.py --campaign experiments/etf_resurrection/results/local \
        --binary "$PWD/experiments/etf_resurrection/results/local/bin" \
        --scratch experiments/etf_resurrection/results/local/scratch --bundle 0 --bundle-size 1000 --workers 8
    python experiments/etf_resurrection/arc/analyze_local.py --campaign experiments/etf_resurrection/results/local

`build_campaign.py` has local modes: `--local` (one cell per constraint
structure at 300 agents), `--local --allcore` (all capacity levels),
`--local --robust` (learning-rate and reference-share robustness),
`--local --robust --devsweep` (development-dose sweep),
`--local --robust --confirm` (learning off versus on, many seeds) and
`--local --prodscale` (production environment, few cells).

### Production campaign on a cluster (Slurm)

The full campaign is 66,576 paired worlds (1,000 agents, 72 localities, 64
seeds per condition, 24 variants). On Virginia Tech ARC (Tinkercliffs):

    bash experiments/etf_resurrection/arc/build_arc.sh
    bash experiments/etf_resurrection/arc/submit.sh --max-nodes 40

Each array element is a 32-core allocation running a bundle of tasks; finished
tasks publish a `_SUCCESS.json` with a SHA-256 of their outputs and are skipped
on resubmission, so an interrupted campaign resumes. The whole campaign costs
about 1,800 service units (about 95 s per world). Collect and analyze with
`arc/collect.py` (phase maps, per-cell and per-structure summaries); the
analysis uses numpy, pandas and scipy, which the ARC login node may lack, so
copy the compact `w.csv` outputs back and run `collect.py` locally. Details in
[arc/README.md](arc/README.md).

### Figures

    python experiments/etf_resurrection/plot_learning_response.py
    python experiments/etf_resurrection/plot_dose_valley.py
    python experiments/etf_resurrection/plot_mechanism.py

These read the collected production `effects.csv` (not tracked) and write to
`findings/`.

## Limits

- The learning rule is a **hypothesis**. Its rate is bounded (about 0.1 to 0.5)
  by one plausibility check against the speed of the Afghan Black Hawk
  grounding after contractor withdrawal, not identified from data.
- The reference share and the development-assistance dose are uncalibrated.
- The capability index is a constructed composite; effects are a few
  hundredths of an index point.
- Not validated against a real case.
- At production scale the no-learning baseline is small and positive, so the
  finding is "neutral or mildly helpful, then harmful", not a clean sign flip.
- The force-generation stress cell of `test_binding_constraint_assay` was
  rescaled because the repaired model has realistic combat losses; the assay
  now tests binding under the repaired model.

## Relationship to the frozen paper cycle

The first paper cycle is frozen at the git tag `paper-freeze-2026-09-21`. The
model on `main` contains the post-freeze repairs below and does **not**
reproduce the frozen datasets bit for bit; check out the tag to reproduce them.

Post-freeze model changes: territorial contestation (institutional erosion
under insurgent dominance, shadow governance, a Lanchester coercive balance,
police reinsertion gating); insurgent organization splits; intelligence-gated
strikes with speculative sweeps; defection and post abandonment; insurgent
tempo; sequenced-withdrawal delays per support channel; locality telemetry;
event-keyed random streams for coupled counterfactual twins; SHA-256 and
information-path performance work with bit-identical hashes; a patrol-presence
clamp (fixing a state-range crash at day 240); and a command-collapse assay
fix.
