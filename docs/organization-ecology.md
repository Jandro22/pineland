# Phase 6 organization ecology

The organization-ecology layer separates political support, represented
membership, fielded fighter manpower, organizational capacity, and armed
formations. A representative civilian becoming partially mobilized is not the
same state transition as a new formation appearing, and an armed formation is
not itself the organization that sustains it.

## State and scale

Every armed organization carries social, political, organizational, and
material capital; ideology; lifecycle status and ancestry; an explicit leader;
and a strategic phenotype covering centralization, political/governance
investment, dispersion, risk tolerance, discipline, local embeddedness, and
resource dependence.

`ProtoOrganization` is the intermediate state between a mobilized social
cluster and a durable armed organization. `OrganizationTransition` is the
genealogical/causal record for birth, proto-collapse, succession, split, merger,
and collapse.

Person membership is weighted. For person \(p\), mobilized represented
membership is

\[
M_p=w_p a_p,
\]

where \(w_p\) is representative population weight and \(a_p\) is
`armed_fraction`. Substantive onset and split eligibility therefore use
represented population, not raw simulated-agent counts. Raw counts remain only
where needed for data-structure safety, such as requiring at least two sampled
member nodes before a split can partition them.

## Onset

Community mobilization combines grievance, social cohesion, insurgent sympathy,
and bridge reach. A probabilistic proto-organization hazard is followed by a
second maturation hazard based on accumulated capital and leadership
potential. The substantive minimum proto threshold is
`minimum_proto_represented_population`; `minimum_proto_members` is retained
only for backward-compatible serialization and is not the scientific onset
threshold.

Birth draws from the actually mobilized community, converts member resources
into startup material, creates fielded fighter manpower subject to
`minimum_formation_personnel`, and connects the initial formation to a command
node. It does not instantiate a national organization merely because a raw
number of synthetic agents is present.

## Recruitment access and fractional representatives

Recruitment into an existing armed organization requires an access channel by
default. Access channels are frozen at the start of each recruitment interval
so loop order cannot create a same-tick cascade. A person has access when at
least one of the following is true in the person's residence locality:

- the organization already has a physically available local formation
  (positive personnel, effective, not moving, and not outside Pineland);
- the organization has an already-armed member there; or
- the person's stored social-network exposure to that organization/insurgent
  side is positive.

With `recruitment_requires_access=true`, absence of all three prevents a
recruitment draw. Let \(A\in[0,1]\) be the maximum of network exposure,
normalized available-local-formation strength, and normalized represented local
armed membership, and let

\[
I_{recruit}=
\operatorname{logistic}\left(
1.5G+E+C_{compat}+K_{social}-F-2.6
-\pi_{peace}A_{political}+\beta_{rooted}L
\right).
\]

Then the interval probability for each eligible subcohort is

\[
p_{recruit}=1-\exp\{-r_{recruit} I_{recruit} A\Delta t\},
\]

with \(A=1\) when access gating is disabled. Here \(G\) is grievance,
\(E\) stored network exposure, \(C_{compat}\)
ideological compatibility, \(K_{social}\) organization social capital, \(F\)
fear, \(A_{political}\) peaceful political access, and \(L\in[-1,1]\) is
**constituency/franchise congruence**.  \(L\) is derived from the candidate's
local/district identity salience and the home origins of the organization's
already-armed members currently resident in that locality. A franchise made of
local residents therefore becomes more attractive to strongly local-identified
civilians; an externally implanted franchise becomes less attractive. If local
and district identity salience are both zero, the rootedness term is exactly
zero. No ethnic category or empirical-case exception enters the equation.

The coefficient \(\beta_{rooted}\) is
`organization_ecology.local_rootedness_weight`. It is an exposed general-theory
prior, not a historical fit parameter. The currently exposed
`social_network.recruitment_exposure_weight` is **not used by this live
organization-ecology recruitment equation** and must not be described as an
active recruitment coefficient.

When more than one active insurgent organization is accessible to an
unaffiliated representative, recruitment is a **competing-risks process**. The
per-franchise effective intensities are summed to obtain the probability that a
subcohort joins some organization during the interval; conditional on joining,
the franchise is selected in proportion to its effective intensity. Active
organizations are sorted by ID before this calculation, so dictionary/insertion
order cannot award recruits to the first franchise encountered. A person already
partly mobilized into one organization may deepen membership only in that same
organization during the interval.

Social exposure is also franchise-specific. Armed members broadcast primarily
to their current organization; unarmed sympathizers and ex-members carry an
`insurgent_affinity` distribution over organizations. The generic `insurgent`
signal remains for side-level behavior and backward compatibility, but in
multi-insurgent worlds it no longer makes every franchise socially
interchangeable. With exactly one active insurgent organization, generic
exposure maps to that sole organization and preserves the legacy one-insurgent
semantics.

Social-control accounting preserves both levels. A behavioral shift can update
the aggregate `insurgent` social-control vector and, when the civilian has a
specific franchise affinity, the corresponding organization-specific control
vector. `locality_franchise_support_profile()` reports represented affiliated
support, unaffiliated insurgent sympathy, franchise shares, HHI concentration,
and a bounded support-fragmentation index. This makes intra-insurgent
constituency division observable without assuming that fragmentation is
automatically violent.

Each representative is divided conceptually into
`recruitment_subcohorts` equal fractions. The code performs one independent
Bernoulli trial per eligible subcohort; multiple subcohorts may transition in a
long interval, while each subcohort can transition at most once in that update.
Exit uses the same elapsed-time hazard conversion on the already mobilized
portion but has its own `membership_exit_rate` hazard scale. Recruitment and
retention/desertion are therefore independently falsifiable mechanisms rather
than one mechanically coupled rate. A representative recruited in the current interval is not also
processed for exit in that same tick. This keeps the stochastic bounded-fraction
representation while making the underlying fixed-state calendar-time hazard
compose across numerical recruitment intervals.

Full armed-membership exit also has a distinct
`organization_ecology.exit_sympathy_retention` treatment. At the legacy default
of `1.0`, an ex-member retains the pre-existing `insurgent_sympathy` public
signal; lowering it permits political/social disengagement independently of
armed retention. This matters for spatial reproduction because sympathetic
ex-members can continue to transmit social exposure even when they no longer
provide armed-member recruitment access or fighter manpower.

The lifecycle process uses the existing seven-day ecology cycle as a **reference
timescale**, not as a hidden dependence on scheduler partitioning. Proto
incubation/maturation, succession, fragmentation, collapse, and merger
probabilities are composed to the actual elapsed ecology interval. Proto-capital
survival is composed the same way. At `interval_days = 7` this preserves the
previous lifecycle probabilities and the previous `1 - proto_decay_rate`
capital-survival factor exactly; changing only the numerical ecology interval
therefore no longer changes the fixed-state calendar-time process.

The change recorded in organization membership is \(w_p\Delta a_p\), not one
raw agent. Only `fighter_conversion_fraction` of that represented membership
change becomes fielded formation personnel.

## Formation decomposition and local manpower

Initial force tokens are generated by the outcome-independent
`ForceStructureConfig`. In `manpower_decomposition` mode, formation count is
derived from total represented side manpower divided by target formation size,
bounded by `maximum_initial_formations_per_side`. The default target sizes are
3,500 personnel for government forces and 1,000 for insurgent formations.
These target sizes are force-token/scaling assumptions unless a case package
explicitly supplies empirical force-structure evidence; they are not conflict
outcome fits.

Recruitment does not pour all new manpower into one national formation. Positive
fighter-equivalent manpower first fills a physically available local formation
(effective, not moving, and not outside Pineland) in the recruit's locality
toward the insurgent target size. A formation in transit cannot provide local
recruitment access and cannot absorb recruits at the locality it has departed.
Remainder enters an
organization/locality manpower pool and materializes into one or more local
formations when it reaches `minimum_formation_personnel`. Exit draws down the
local pool and formations before geographically nearest same-organization
formations. Supply capacity is resized with personnel without silently
destroying existing stock.

For empirical initial insurgent placement, `initial_insurgent_locality_ids` is a
case input. Additional initial force tokens disperse outward from supplied
origins over the exogenous locality graph; without supplied origins, placement
uses administrative capacity with a dedicated force-generation RNG stream so
civilian sampling resolution cannot change force placement tie-breaks.

## Adaptation, fragmentation, merger, and collapse

Organization cohesion responds to social capital, represented member identity
variance, and accumulated military losses. Phenotypes imitate apparently
successful peers with bounded mutation and heterogeneous learning. Phenotype
feeds command reliability, dispersion/mobility, discipline, and local
embeddedness. Succession creates a new explicit leader and records the event.

Split eligibility uses
`minimum_split_represented_population`. When a split occurs, members are
partitioned by their actual social-community/geographic structure rather than a
fixed 50/50 rule. Resources follow represented membership shares; formations,
local manpower pools, and supply ownership follow the resulting lifecycle
assignment.

Mergers conserve represented membership, organization resources, formations,
local manpower pools, and supply-source ownership. Merger opportunity is also
relational rather than national: ideological similarity and low cohesion can
raise a merger hazard only when both organizations share at least one locality
containing live armed constituency or fielded presence.
`organization_contact_overlap()` scales the opportunity by the fraction of the
smaller organization's occupied locality set that is shared, so two compatible
organizations in disjoint local arenas have zero merger hazard until an actual
arena of interaction exists. Collapse can follow
insolvency, cohesion failure, social-base loss, or sustained degradation and
can occur while nonzero manpower remains. Historical organizations remain as
inactive genealogy nodes rather than being erased.

The collapse social-base term is local/organizational rather than a share of
the entire national population. Represented armed membership saturates against
the same represented-population scale used for viable proto-organizations;
survival also reflects the deepest local membership foothold, explicit social
capital, and local embeddedness. Adding unrelated population elsewhere in the
synthetic country therefore cannot by itself make an unchanged organization
more likely to collapse.

## Empirical actor-persistence conditioning

`organization_ecology.observed_active_intervals` is a **case input for
actor-existence conditioning**, not a fitted hazard coefficient. During an
interval in which a named organization is historically observed to remain an
active actor, the live ecology suppresses identity-changing:

- organizational split,
- organizational collapse, and
- merger involving that conditioned actor.

It does not freeze the actor's operations. Recruitment, casualties, movement,
combat, adaptation, command rewiring, succession, resources, cohesion, and
other endogenous state changes continue. The conditioning therefore says
"this named actor persists as an identity during this observed window," not
"make this actor successful" or "hold its strength fixed."

Outside supplied intervals, lifecycle hazards operate normally. Because these
intervals encode historical actor existence, they belong in case provenance
and train/holdout leakage review rather than being mislabeled as calibrated
model parameters.

## Conservation and analysis

Transitions record parent/child IDs, represented member assignments, resource
assignments, formation assignments, inherited traits, and causal variables.
World invariants prohibit duplicate active ownership and reconcile reciprocal
person/organization membership. Population, manpower, resource, and supply
accounting remain active across lifecycle operations.

`organization_ecology.json`, `organization_transitions.jsonl`,
`organization_eligibility.jsonl`, and `organization_onset.jsonl` expose
the corresponding analyst diagnostics. These are latent/forensic simulation
records unless explicitly transformed through an empirical observation model;
they are not automatically equivalent to historical recorded observables.
