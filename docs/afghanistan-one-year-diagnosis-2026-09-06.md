# Afghanistan: one-year diagnosis and execution repair

The full-horizon runs remain stopped. Structural gate success is not empirical acceptance. No parameters, historical inputs, observation probabilities, or action rates were fitted in this repair.

## Verified empirical failure

The fresh baseline reproduces the saved v5 year-one summary and violence scores exactly. Over the runner's existing 1,802 province-week cells through day 366:

| Layer | Active cells | Correct active cells | Sensitivity | Precision | Jaccard |
|---|---:|---:|---:|---:|---:|
| Historical | 148 | — | — | — | — |
| Latent | 24 | 1 | 0.006757 | 0.041667 | 0.005848 |
| Recorded | 4 | 0 | 0 | 0 | 0 |

The spatial-temporal mismatch precedes recording. These metrics use the existing scoring convention, including the final partially exposed week; they do not introduce a new validation split.

The action funnel contains 21,905 scheduled actions, including 20,412 rejected by the action-opportunity draw. Only 67 select armed confrontation; 61 of those find no eligible battle pair. The 153 realized latent actions include other channels and should not be equated with 153 state-based violence events.

## Capacity and control decomposition

The final Taliban formation stock is approximately 39,760 personnel, but the sum of `available_personnel()` is only **614.72**. This is a model-derived capability measure after availability, fatigue, readiness, supply, and command modifiers, not an independently observed force estimate. Across 89 Taliban formations, median supply fraction is 0, median stored readiness is 0.006, and median availability is 0.03. The status label alone misses this degradation: 87 formations still carry `effective` status.

Mean insurgent physical control is **0.0136345**, positive in **40 of 401 localities**. Formal and administrative control are zero in every locality. The effective-control summary takes a geometric mean across seven dimensions, so either zero forces the composite to zero. The zero composite therefore does not demonstrate absent physical reach. No alternative aggregation weights were introduced to conceal this issue.

Code inspection identifies a hypothesis to test, not a demonstrated causal repair: source production is established from initial organizational manpower, while recruitment can create and enlarge formations without proportionate supply-source expansion. Formation birth receives finite startup materiel. Demand, delivery geography, depletion, and recovery need a controlled decomposition before changing these mechanisms. Automatically creating supplies to match recruitment would bypass the material constraint rather than explain it.

## Execution changes and verification

Recurring logistics now visits ordered indexes of active shipments and movement orders. Completed records remain in their original archives. Reallocation constructs its busy-formation set once instead of scanning all historical orders separately for every formation. These changes remove identified history-dependent quadratic work; they do not establish that every remaining subsystem scales linearly.

Physical response skips remote patrol readiness calculations and avoids recomputing the same `insurgent` actor twice. Corroboration stops after its existing evidence-weight cap is reached, preserving the capped numerical result.

The bounded runner is `studies/afghanistan_2004_2021/scripts/profile_year.py`. It rejects horizons above 366 days, logs 30-day timing windows, and exports control dimensions, formation capability diagnostics, activity overlap, and reproducibility hashes. Optional `--profile` adds function timings; profiling overhead must not be mixed with ordinary wall-time comparisons.

Fresh unprofiled runs on this machine:

| Measurement | Before | After |
|---|---:|---:|
| Simulation seconds | 322.615 | 216.819 |
| Events processed | 52,126 | 52,126 |

Observed speedup is **1.488×**, or a **32.8%** wall-time reduction. This is one before/after pair and is sensitive to machine load; the older saved run took about 223 seconds. It is not a claim of a corresponding full-horizon speedup.

All decision-state component hashes, checkpoint trajectory hashes, summaries, and violence scores match exactly between the fresh runs. Source hashes are stable within each run. The selected physical, information, logistics, combat, ecology, action, reproducibility, integrity, spatial-repair, and Afghanistan tests pass: **129 tests** total. New regression checks prohibit historical archive scans in recurring logistics, check remote patrol filtering, and compare capped corroboration against a complete reference scan.

The transfer runner also now labels legacy contact-hazard diagnostics as unavailable under multichannel v5. An empty legacy funnel previously reported a misleading probability of zero contacts equal to 1 despite realized v5 violence.

Evidence is retained in `studies/research_program/afghanistan_performance/year_before.json`, `year_after.json`, and `comparison.json`.

## Remaining work before the full horizon

The one-year empirical fit remains unacceptable and unchanged. The next bounded mechanism experiment should record local supply demand, deliveries, availability, action opportunities, selected channels, and target eligibility on a common province-week surface. Compare these against the declared historical surface without changing the held-out targets. Distinguish shortage and recovery failure from misplaced local capacity and absent targets before modifying rates. Subsequent performance work should profile later-year states and remaining spatial scans, with fixed-state scaling tests, before committing to another 17.6-year run.
