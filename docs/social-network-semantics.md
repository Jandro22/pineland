# Social-network semantics and weighted-agent scaling

## Representative agents are population carriers

A `Person` is a representative agent with weight \(w_i\). The weight is
represented population mass, not a claim that \(w_i\) literal people have
independent identical friendships or make \(w_i\) independent stochastic
choices. Substantive population totals and shares therefore use weights, while
the sampled graph remains a computational representation of social structure.

Under empirical geography, representative civilians are stratified by locality:
every locality receives at least one representative, the remaining agent budget
is allocated proportional to locality population, and weights are chosen so
each locality's represented population is conserved exactly.

## Communities are packed by represented population

Households are indivisible sampled archetypes, but social communities are
packed according to represented household population. The legacy
`minimum_community_size`, `target_community_size`, and
`maximum_community_size` knobs are multiplied by
`community_size_unit_population`. With the default 120 residents per unit,
the nominal target of 100 means roughly 12,000 represented residents, not 100
simulated people.

This is a structural/scaling choice. It prevents changing `agent_count` from
changing the substantive size threshold for community construction.

## What one edge means

A `SocialEdge` is a **sampled aggregate channel of influence between two
representative agents**. It is not interpreted as exactly one literal
friendship. Layers identify household, ordinary community, or cross-community
bridge mechanisms.

The edge stores:

- `language_compatibility`: best mutually comprehensible shared language;
- `trust`: source acceptance, independent of language;
- `weight`: channel strength after language attenuation; and
- `represented_relationships`: the represented mass carried by the sampled
  channel.

With language topology enabled,

\[
W_{ij}=W^{base}_{ij}(0.35+0.65L_{ij}).
\]

Shared language does not create trust, and language mismatch does not delete
communication because the multiplier retains a 0.35 floor.

## Represented relationship multiplicity

For representative weights \(w_i\) and \(w_j\), a sampled edge carries

\[
m_{ij}=\frac{2w_iw_j}{w_i+w_j},
\]

the harmonic mean of endpoint weights. Its influence mass is

\[
q_{ij}=m_{ij}W_{ij}T_{ij}.
\]

For receiving person \(i\), neighbor signals are normalized by
\(\sum_j q_{ij}\). Equal representative weights therefore cancel their common
scale, while unequal weights alter relative social mass without allowing raw
agent count to become unbounded influence.

Cross-community bridge roles follow the same represented-capacity rule. A
bridge member ID is only a sampled graph anchor; it is not one literal broker.
The substantive bridge capacity of a community is bridge_fraction times
represented community population. That capacity can occupy only a fraction of
a coarse representative cohort, or be distributed across several finer
representative cohorts. Organization-formation reach reads this represented
capacity directly, so the old minimum-one-representative rule cannot inflate a
coarse community from a small bridge fraction to an entire representative
person's weight.

The sampled degree parameters (`mean_social_degree` and
`maximum_social_degree`) describe the computational graph, not a literal
population friendship count. Network diagnostics consequently report both
sampled graph measures and represented-weighted measures where substantive
interpretation differs.

## Exposure and fractional armed membership

The social-influence process computes government and insurgent signals from
neighbor public behavior using \(q_{ij}\), then normalizes them to bounded
exposure. If a neighbor belongs to an insurgent organization, the insurgent
signal is conditioned on that person's `armed_fraction`; a representative
with only a small mobilized subcohort does not broadcast the same armed signal
as a fully mobilized representative.

Exposure is not itself persuasion, participation, or recruitment. Public
behavior separately considers private preference, expected control, fear,
efficacy, grievance, political access, displacement, and organization
membership. `behavior_exposure_weight` controls the exposure term in that
behavior utility.

Existing-organization recruitment is owned by
`organization_ecology.recruit_and_retain`. Stored network exposure is one
access channel and one term in its recruitment logit, but the currently exposed
`social_network.recruitment_exposure_weight` is not read by that live
equation. It is therefore a reserved/legacy configuration field at present,
not an active scientific coefficient.

The causal chain is:

```text
sampled edge + represented multiplicity + neighbor signal
-> normalized stored social exposure
-> behavior utility and/or recruitment-access/recruitment equation
-> stochastic transition on a weighted representative or subcohort
-> represented-population/manpower aggregate
```

## Bridge construction and resolution

Bridge representatives are preferentially selected for multilingual ability.
Bridge count is a fraction of sampled members in each community rather than a
fixed raw-node cap. Because communities target stable represented population
mass, this avoids the earlier failure mode in which a fixed number of bridge
nodes changed represented bridge mass sharply with simulation resolution.

The exact sampled topology can still vary with resolution; that is why
degree-preserving topology ablations and matched represented-population
resolution tests remain required. Resolution robustness is an empirical
software/model property to test, not an assumption to declare.
