# Phase 2 physical occupation model

## Scientific question

Given fixed security resources, how do internal road topology, posts, patrol movement, availability, travel time, terrain, response capability, and recent-presence memory generate uneven physical control inside a locality?

## Causal direction

Microzone state is causally upstream:

```text
physical graph + posts + patrol paths + availability
-> travel and response times
-> current and remembered presence
-> microzone physical control
-> population-weighted locality physical control
```

Locality physical control is never distributed downward into zones. Each physical refresh recomputes zone values and replaces the locality value with:

\[
C^{physical}_{m} = \sum_{z\in m} p_z C^{physical}_z,
\]

where (p_z) is the zone population share.

## Response and presence

Response time is a multi-source shortest-path calculation from available posts and patrols. Edge cost combines distance, road quality, terrain friction, disruption, and formation mobility. Response capability decays exponentially with travel time.

Current formation occupation and residual patrol memory are separate state
channels. An effective formation that is not moving or outside Pineland
contributes instantaneous presence at its explicit current microzone through
`formation_presence_gain`; this rule is actor-symmetric and does not write the
memory stock. Fixed posts provide persistent immediate presence.

Explicit patrol objects generate a separate exponentially decaying memory stock.
Only the deployed patrol element contributes: effective parent strength is
multiplied by `Patrol.response_fraction`, normalized locally, and scaled by
`patrol_memory_gain`. The contribution is integrated analytically over actual
completed dwell time. A per-patrol accounting timestamp makes one matched dwell
window equivalent to any numerical subdivision of that same window, so physical
refresh or callback frequency cannot manufacture extra memory.

Ordinary insurgent formations currently have no patrol objects. They therefore
receive the same current formation presence and response semantics as state
formations but do not acquire an implicit patrol-memory stock merely by being
stationary. This is an explicit role asymmetry, not an identifier-dependent
special case. If an insurgent organization is ever given an explicit patrol
object, that patrol uses the same memory integration machinery and writes the
insurgent-side memory label.

Movement preserves the distinction. Before a scheduled event can change
formation strength, location, availability, or operational status, completed
patrol dwell is accounted through that event time. A moving or outside formation
then contributes neither current formation presence nor response, and transit
does not create new patrol dwell memory. Previously accumulated memory continues
to decay normally.

Zone control combines current formation presence, fixed-post presence, residual
patrol memory, and response. It does not use arbitrary downtown, market, urban,
rural, or terrain bonuses.

## Partial observation and routing

Each relevant organization has a noisy `ActorZoneBelief`. A patrol observes its current zone, updates that belief according to zone observability, and selects among graph-adjacent destinations using perceived weakness and travel cost. True zone control is not an input to destination choice.

This permits repeated patrol of mistakenly perceived weak zones and neglect of deteriorating zones that the actor has failed to observe.

## Scope boundary

Combat remains a separate bounded process and never writes territorial control
directly. Both government and insurgent formations carry explicit microzone
positions; current formation presence, formation response, and locality
aggregation are symmetric. Patrol memory is tied to the explicit patrol role,
not copied onto all formations. Local armed membership and social-network
exposure belong to recruitment/access semantics and do not directly write
physical control. Combat effects reach physical control only through subsequent
formation state, presence, memory, and response refreshes.
