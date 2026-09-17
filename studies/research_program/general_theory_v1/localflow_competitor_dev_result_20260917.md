# Local-flow competitor development result — 2026-09-17

Status: **INVALIDATED / SUPERSEDED BY ANALYZER CORRECTION**.

> Correction: the first analysis omitted candidate-specific future outcomes for
> `rootedstock_execnet_ring1_localflow17v7`. In particular, it did not audit
> the ring-1 transport/source outcomes plus the newly matched raw-net-transport
> and recruitment-hazard outcomes. The apparent 1/6 failure rate below was
> therefore produced by a weaker outcome battery and is not scientifically
> comparable to ring 1 or ring 2. The corrected result is recorded below.

## Frozen candidate

`rootedstock_execnet_ring1_localflow17v7` extends the rejected ring-1 state by
matching two additional local coordinates:

- signed local net transport pressure; and
- local recruitment hazard.

The candidate and its fresh development seed block were frozen before its
fresh outcomes were inspected in
`live_insurgency_closure_localflow_competitor_contract_v1.json`.

The screen was intentionally compute-light because the workstation is shared:

- 48 dynamic worlds;
- 300 agents;
- 34 localities;
- 60-day anchor;
- 30-day forecast horizon;
- 6 matched pairs, balanced 2/2/2 across low/mid/high activity;
- 4 continuation branches per side;
- 2 worker threads;
- recruitment multiplier 0.0625;
- live anchors required.

## Original result — invalid

The incomplete equivalence analyzer originally classified:

- 0/6 equivalent;
- **1/6 demonstrably non-equivalent**;
- 5/6 inconclusive.

This result is invalid because those candidate-specific transport/source
outcomes were not included in the local-flow analyzer registry.

Maximum selected match distance was 1.1993, below the frozen 1.25 gate but much
worse than the earlier exact ring-1 screen. This small pool therefore trades
match quality for compute economy and cannot certify equivalence.

## Low-branch power control from completed ring-1 data

To check whether the apparent improvement was merely caused by using only four
continuation branches, the completed exact ring-1 CSV was reanalyzed after
retaining only branches 0–3.

Across all 24 existing ring-1 pairs, the four-branch reanalysis produced:

- 0/24 equivalent;
- **18/24 demonstrably non-equivalent (75%)**;
- 6/24 inconclusive;
- 11 demonstrable failures involving `final_executable_net_transport_pressure`.

Restricting that control further to the first six ring-1 pairs gave 5/6
demonstrably non-equivalent and 1/6 inconclusive. That six-pair subset is all
low-activity because the original matcher stores strata sequentially, so it is
not an activity-balanced comparator.

The control nevertheless shows that four branches alone do **not** generally
erase the ring-1 failure signal.

## Original interpretation — retracted

The original analysis appeared to support a competing explanation for the
earlier transport-dominated closure failures, but that interpretation is
retracted because the outcome battery was incomplete:

> A meaningful share of the apparent nonlocal transport memory may actually be
> omitted *local flow/regeneration state*—particularly the distinction between
> movement demand, executable movement flux, and the focal locality's current
> recruitment hazard.

This is mechanistically plausible. The production movement diagnostics treat
raw net transport demand and command-reliability-weighted executable net flux
as distinct quantities. Matching only the executable scalar can hide different
underlying demand/reliability regimes. The focal recruitment hazard is also an
instantaneous local regeneration-rate field and was absent from the ring-1
state even though neighboring recruitment hazard was included.

The mechanism remains theoretically possible, but this pilot no longer
provides evidence for it. The two hypotheses remain candidates rather than an
empirically ordered pair:

1. an expanding horizon-dependent spatial causal cone; and
2. insufficient local stock-flow-regeneration state.

## Originally planned discriminator

The next high-value experiment is a **same-world, same-budget development
comparison** on the frozen local-flow world block:

- original `rootedstock_execnet_ring1_15v5`;
- `rootedstock_execnet_ring1_localflow17v7`;
- optionally the preregistered ring-2 candidate only after preserving its
  separate fresh-block interpretation.

Run the comparator at two threads and the same 48-world / 6-pair / 4-branch
budget. If the original ring-1 state again shows transport-dominated
demonstrable failures while local-flow does not, the local-state explanation
becomes substantially stronger. If both become mostly inconclusive on the same
pool, the current result is likely selection/matching noise.

This discriminator was run, then reanalyzed after the analyzer defect was
found.

## Same-pool three-way discriminator — corrected

That discriminator was subsequently run with `closure-battery`, which built
the 48 anchored worlds once and reused them across all three candidate
matchers. Each candidate received the same six-pair/four-branch/two-thread
budget on dynamic seeds beginning at 2026170000.

| Candidate | Demonstrably non-equivalent | Inconclusive | Max match distance | Selected failure outcomes |
| --- | ---: | ---: | ---: | --- |
| ring 1 (`rootedstock_execnet_ring1_15v5`) | **3/6** | 3/6 | 1.0647 | executable net transport in 2 pairs; neighbor rooted mass in 1 |
| ring 2 (`rootedstock_execnet_ring2_18v6`) | **5/6** | 1/6 | **1.2674 (gate violation)** | executable net transport in 3; multiple ring-2/source outcomes |
| ring 1 + local flow (`rootedstock_execnet_ring1_localflow17v7`) | **5/6** | 1/6 | 1.1993 | raw net transport in 4; executable net transport in 3; recruitment hazard in 1; source-state failures |

The ring-2 candidate also exceeded the frozen 1.25 maximum match-distance gate,
so this small-pool screen cannot be used as evidence for ring-2 sufficiency even
apart from its five demonstrable failures.

After registering the correct candidate-specific future outcomes, the
local-flow candidate fails 5/6 pairs. Four pairs are demonstrably
non-equivalent in future raw net transport pressure and three in executable net
transport pressure. The added coordinates therefore do **not** close their own
future distributions on this development block.

This remains a development mechanism screen rather than a paired treatment
effect because each matcher selects its own pairs. The corrected evidence does
not support local-flow as an improvement: ring 1 has the lowest demonstrable
failure fraction of the three candidates on this small shared pool.

The current evidence therefore supports neither tested repair. Radius-2
expansion performs poorly and violates the small-pool match-distance gate;
adding raw local net transport plus focal recruitment hazard also performs
poorly once audited against the complete future state. The robust surviving
fact is the original one: **ring 1 itself is insufficient, with residual
failure dominated by future executable transport/source dynamics.**

## Analyzer correction

Two analysis defects were corrected before any further closure experiment:

1. Candidate-specific future outcomes are now explicitly registered for the
   local-flow and component-ablation candidates.
2. Bootstrap resampling streams are derived from immutable pair provenance
   (`left_seed`, `right_seed`, `locality`) rather than candidate-local pair
   ordinal / analyzer iteration order. Identical state pairs now receive
   identical bootstrap resamples across candidate analyses.

Reanalysis of the formal 24-pair ring-1 screen with the corrected analyzer
leaves its headline conclusion unchanged: **0/24 equivalent, 14/24
demonstrably non-equivalent, 10/24 inconclusive, maximum match distance
0.55568**. Eleven of the fourteen demonstrable failures still include future
executable net transport pressure. The methodological correction therefore
retracts the local-flow improvement without weakening the preregistered ring-1
rejection.

