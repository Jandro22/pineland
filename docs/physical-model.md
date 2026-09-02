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

Recent patrol presence is a stock with exponential decay. Fixed posts provide persistent local presence, while patrol arrivals add temporary memory. Zone control combines the resulting presence and response fields; it does not use arbitrary downtown, market, urban, rural, or terrain bonuses.

## Partial observation and routing

Each relevant organization has a noisy `ActorZoneBelief`. A patrol observes its current zone, updates that belief according to zone observability, and selects among graph-adjacent destinations using perceived weakness and travel cost. True zone control is not an input to destination choice.

This permits repeated patrol of mistakenly perceived weak zones and neglect of deteriorating zones that the actor has failed to observe.

## Scope boundary

Phase 2 does not add combat mechanics. The inherited coarse contact process retains personnel, readiness, expected-control, and social effects, but it no longer writes directly to locality physical control. Physical combat effects require explicit microzone locations and belong in a later bounded extension.
