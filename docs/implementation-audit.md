# Continuation audit and Phase 4 implementation report

## Phase 9 closure

Version 0.9 adds persistent negotiations, explicit agreement provisions, faction-level
acceptance and spoilers, ceasefire violation, gradual implementation, conserved DDR stocks,
armed-to-political organizational conversion, foreign mediation and sponsor pressure, and
endogenous recurrence. The matched unified/fragmented experiment and its interpretation are
documented in `peace-process.md`; the phase is covered by 15 focused tests in addition to all
prior regression tests.

## v0.10 research-validation closure

Version 0.10 deliberately adds no new conflict-domain mechanisms. It provides
a complete scalar-parameter provenance registry, explicit sourced target
contracts, Latin-hypercube global sensitivity and interaction screening,
practical-equivalence identifiability labels, train/holdout calibration
workflow, and a capability-aware null/proxy/reduced/full model ladder. The
release reports inactive or non-identifiable mechanisms as findings rather
than forcing a positive conclusion. See `research-validation.md`.

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

Phase 1 establishes network-mediated behavior but not a calibrated social model. Edge formation priors, behavior utilities, influence rates, and control coupling require sensitivity and identifiability analysis. Migration does not yet rewire social ties or retain explicitly decaying origin ties. Those extensions should follow physical occupation and information-fusion milestones rather than being bundled into this phase.

## Versioned checkpoint and Phase 3

The verified Phase 1 + Phase 2 state was committed as `124df96` with message `v0.2 baseline: social networks and physical control` and annotated tag `v0.2.0` before Phase 3 began.

Phase 3 adds formation-locality pathfinding, delayed movement orders, explicit command reliability and latency, conserved supply sources and shipments, movement/presence/patrol consumption, readiness and availability degradation/recovery, resource-flow exports, and locality control-cost diagnostics. Detailed combat remains deferred.

The Phase 3 verification suite contains 34 passing tests. A 30-day, 1,000-agent smoke run processed 2,476 events, issued 24 movement orders (17 arrived, 4 supply-blocked, and 3 command-failed), and wrote 3,447 resource-flow records. Supply reconciled to a residual of approximately `7.04e-9` units. The run produced 969 `force_projection_reallocation` and 650 `logistics_constrained_physical_aggregation` provenance entries.

The post-Phase-3 two-day 25,000-versus-75,000 comparison retained the same resolution behavior: government effective-control difference `-0.00000607`, insurgent effective-control difference `0.00000000113`, and maximum public-behavior share difference `0.00332`.

## Phase 4 delivered

Phase 4 freezes the scientific question as: what can each actor actually know
about the conflict environment, and how does that knowledge affect action?

- First-class `Observation` objects carry target/subject, locality or
  microzone, timestamp, source ID/type, estimated values, confidence, quality,
  and provenance.
- Patrols, fixed posts, civilians, social networks, administrative channels,
  organization members, political/local elites, interpreters, and contact
  events are separate source classes with heterogeneous coverage, trust,
  latency, language comprehension, and decay.
- Formation detection uses condition-dependent true-positive and false-positive
  probabilities and a configurable attribution-error rate. Negative observations
  are retained, enabling false negatives and contradictory evidence without
  last-write-wins behavior.
- Control and presence beliefs use confidence-weighted fusion. Confidence ages;
  `information_age` records the time since the last reliable observation.
- Local node beliefs are immediately available while `InformationRelay` objects
  propagate evidence through command graphs with finite latency and compounded
  reliability. Movement leaves prior beliefs stale until new evidence arrives.
- Analyst-only `belief_error`, source mix, age, relay, presence-belief, and
  detection diagnostics are exported separately from actor state.
- Candidate contact events now depend on source detections and an explicit
  activity hazard. The inherited coarse combat placeholder remains only for
  compatibility; detailed combat is still Phase 5.

The Phase 4 suite contains 43 passing tests. Population and supply conservation,
matched-seed reproducibility, the no-insurgency null, and the existing
resolution-sensitivity checks remain passing. A 1,000-agent, 30-day information
smoke produced approximately 32,390 observations and 32,390 auditable command relays while
retaining the Phase 3 supply and control diagnostics.

## Phase 5: armed contact and tactical consequences

Phase 5 replaces the inherited coarse contact resolver with persistent,
microzone-located `Engagement` records. Relative capability consumes actual
formation personnel, quality, cohesion, readiness, command, supply,
embeddedness, detection state, and terrain-mediated mobility/exposure.
Stochastic attrition, readiness and cohesion damage, supply expenditure,
disengagement, temporary ineffectiveness, and existing-formation reinforcement
orders are explicit outputs. No combat function writes physical control.

Civilian harm is spatial and stochastic. It produces explicit noisy engagement
observations and heterogeneous perceived-momentum updates; political effects do
not bypass observation and attribution. The causal ledger records formation
degradation, which reduces patrol/presence capacity and is converted into
control only by later physical refreshes.

The Phase 5 suite contains 53 passing tests. A 30-day 1,000-agent smoke run
processed 2,566 events and one realized engagement while preserving population
and supply invariants. Its engagement produced 2.06 represented civilian-harm
units. The two-day 25,000-versus-75,000 comparison retained exact represented
population and produced government-control difference `-0.0000061011`,
insurgent-control difference `0.0000000159`, and maximum behavior-share
difference `0.00316`.

## Phase 6: endogenous armed-organization ecology

Phase 6 introduces organizational capital, mobilized proto-organizations,
probabilistic armed onset, recruit-composition effects, endogenous cohesion,
strategic phenotype, explicit leadership and succession, adaptation,
network/geography-structured fragmentation, merger, multi-path collapse, and a
genealogical transition ledger. Political support, organization, and armed
strength are now distinct state layers.

Birth, split, merger, succession, proto-collapse, and armed-organization
collapse record causal transition objects. Split and merger operations preserve
member identity, resources, formations, and supply ownership while transferring
command relationships. Collapse can disable a formation with nonzero manpower.
Population and supply conservation remain world invariants, and active
membership must be unique and reciprocal.

The Phase 6 acceptance suite includes controlled peaceful-null and endogenous
birth cases, a mixed probabilistic onset ensemble, a network-structure onset
contrast, recruitment/cohesion tradeoffs, nonzero-manpower collapse,
conservative split and merger, military-loss feedback, bounded adaptation,
leadership succession, genealogy, and matched-seed reproducibility.

The complete suite contains 66 passing tests. A 90-day, 1,000-agent integrated
smoke run processed 7,641 events, retained the seeded armed organization, and
preserved the represented population of 8,800,000 exactly. The two-day
25,000-versus-75,000 scale check produced government-control difference
`0.00018215`, insurgent-control difference `-0.000000657`, and maximum
behavior-share difference `0.0180`, all within the established engineering
tolerance. These checks establish implementation stability, not empirical
calibration or long-horizon identifiability.

## Phase 7: political order and governance competition

Phase 7 separates state, incumbent-government, and party legitimacy and creates
a federal, district, and municipal institutional ecosystem. Parties now have
local branches and overlapping membership; explicit local elites broker among
branches, institutions, and communities. Elections change ruling-party and
institutional influence without directly changing locality control.

Federal policy budgets flow through auditable public, patronage, broker, and
private-diversion transfers. Corruption redistributes resources. Local autonomy,
reach, compliance, integrity, and capacity generate heterogeneous policy
implementation and five-dimensional governance output. Institutional capacity
moves slowly and can deteriorate while patronage improves incumbent loyalty.

Political access raises peaceful participation and reduces Phase 6 onset and
recruitment pressure, closing the competition loop between institutional and
armed mobilization. Outputs include political diagnostics plus transfer,
implementation, and election ledgers. Scale analysis now includes ensemble
distributions for political behavior and stochastic armed onset.

The Phase 7 suite contains 78 passing tests. A 210-day, 1,000-agent integrated
run processed 17,777 events, held represented population exactly at 8,800,000,
completed two elections, changed the ruling party to `party-2`, exercised 95
institutions and 216 local party branches, and emitted 2,788 political-transfer
records. The final two-day 25,000-versus-75,000 comparison produced government
control difference `-0.00000405`, insurgent control difference `0.0000000228`,
and maximum behavior-share difference `0.00144`. Ensemble onset diagnostics
are tested separately because discrete births should not be interpreted as
continuous paired outcomes.

## Phase 8: foreign powers and internationalization

Phase 8 adds five heterogeneous neighboring states, 17 first-class border
segments, cross-border flight/migration/return, persistent diaspora links,
conserved remittances, eight-component external support, sanctuary, sponsor
dependence, foreign formations using the existing military engine, socially
embedded interpreter-brokers, imperfect foreign beliefs, heterogeneous
legitimacy effects, host dependence, capacity transfer/crowding-out, domestic
willingness, rival reaction, and logistics-routed withdrawal. The production
election interval is corrected to 1,460 days; accelerated calendars remain
test-only.

The Phase 8 suite contains 93 passing tests. A one-year, 1,000-agent integrated
run processed 30,887 events with exact represented population of 8,800,000. It
produced 12 external migrants/diaspora links, eight support events, 152 external
transfer records, one active intervention, and one engagement. End-year host
capacity was `42.33537`; foreign capacity was `0.005952`, for dependence
`0.0001406`. The baseline did not trigger rival cascading (`R_E=0`) in this
single realization.

The final two-day 25,000-versus-75,000 scale check produced government-control
difference `0.00001101`, insurgent-control difference `0.0000000236`, and
maximum behavior-share difference `0.00144`.

In the controlled ten-year A/B/C experiment, all interventions withdrew in year
8 and B/C began with identical foreign capacity. Final aggregate host capacity
was `30.28776` without intervention, `29.26238` under substitution, and
`31.31315` under capacity building. Relative to A, B ended `3.385%` lower and C
ended `3.385%` higher; the B-to-C gap was `2.05077` capacity units (`6.771%` of
initial host capacity). Peak derived withdrawal shock was `0.005454` for B and
`0.002928` for C, making the substitution shock `86.27%` larger. These are
mechanism-verification results under uncalibrated priors, not empirical claims.
