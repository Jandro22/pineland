# Continuation audit and Phase 1 implementation report

## Pre-change verification

The inherited runtime passed all 12 tests and completed a 1,000-agent, 30-day smoke trajectory with 72 localities, 18 formations, and 2,275 events. The four established outputs were structurally valid:

- `summary.json` contained headline run and control measures.
- `checkpoints.json` retained actor-by-locality seven-dimensional control vectors.
- `synthetic_records.jsonl` contained noisy, selectively recorded event observations.
- `causal_ledger.jsonl` linked realized control deltas to event IDs and mechanisms.

## Findings and dispositions

| Finding | Disposition |
|---|---|
| No social-community or social-edge state existed | Resolved in Phase 1 |
| Civilian behavior used locality conditions without explicit network exposure | Resolved in Phase 1 |
| Patrol route choice consulted true control | Corrected to consult actor belief estimates |
| Stochastic transition handlers shared one RNG | Corrected with named per-process streams |
| No-insurgency worlds retained phantom insurgent control and allowed insurgent-sympathy behavior | Corrected and covered by a stronger null test |
| Social-edge semantics and representative-weight behavior were implicit | Resolved with aggregate-channel semantics, harmonic multiplicity, normalized exposure, and scale tooling |
| Language compatibility was applied once in edge weight and again during influence | Corrected; language and trust are now distinct and compatibility is applied once |
| `burn_in_days` is configured but not executed as a distinct unrecorded phase | Open; schedule for runtime lifecycle work |
| Most transition constants remain local code priors | Open; Phase 1 parameters documented, broader registry still required |
| Internal locality physical graphs and response-time mechanics were absent | Resolved in Phase 2 |
| District headline aggregation did not expose dispersion/topology | Improved with `district_control_distribution`; richer corridor/island metrics remain open |
| JSON checkpoint size will grow rapidly at research scale | Open; retain current contract until columnar storage is added |

## Phase 1 delivered

- `SocialCommunity` and `SocialEdge` scientific state objects.
- Household-preserving person-to-community membership.
- Sparse household, community, and bridge layers.
- Edge-level language compatibility, trust, and effective strength.
- Deterministic `social-network-generation` and `process:social_influence` random streams.
- Network-based government and insurgent exposure.
- Unified observable civilian behavior choice across inactivity, cooperation, parties, civil society, protest, sympathy, armed participation, and migration.
- Recruitment linkage to explicit insurgent-network exposure.
- Community and locality aggregation.
- Causal-ledger entries for network-driven social-control transitions.
- Degree, component, bridge, clustering, and language-compatibility diagnostics.
- Population-weighted district control variance and connected-control diagnostics.

## Performance checkpoint

On the bundled development runtime, a 25,000-agent world generated 252 communities and 118,733 social edges in approximately 0.79 seconds. A one-day run took approximately 0.61 seconds. These are engineering measurements from one local run, not formal benchmarks; repeat across 25,000, 75,000, and 150,000 agents before optimization decisions.

A final fixed-population, two-day scale comparison produced the following 25,000-versus-75,000 differences: government effective control `-0.00000610`, insurgent effective control `0.00000000113`, and maximum public-behavior share `0.00332`. Longer multi-seed ensembles remain necessary.

## Phase 2 delivered

- Locality-internal connected microzone graphs with explicit road edges.
- Fixed police and formation posts.
- Formation-linked patrol state and actual route histories.
- Travel time from distance, roads, terrain, disruption, and formation mobility.
- Patrol availability during movement.
- Exponentially decaying recent-presence memory.
- Multi-source shortest-path response times.
- Actor-specific zone-control beliefs and noisy patrol observation.
- Patrol routing from perceived weakness rather than model truth.
- Microzone control generated from presence and response capability.
- Strict upward population-weighted aggregation into locality physical control.
- Physical diagnostic output with per-zone control, memory, and response time.
- Removal of direct coarse-combat writes to locality physical control.

## Remaining scientific limitations

Phase 1 establishes network-mediated behavior but not a calibrated social model. Edge formation priors, behavior utilities, influence rates, and control coupling require sensitivity and identifiability analysis. Migration does not yet rewire social ties or retain explicitly decaying origin ties. Information messages are still summarized signals rather than persistent message objects with source attribution and aging. Those extensions should follow physical occupation and information-fusion milestones rather than being bundled into this phase.
