# Phase 5 combat model

Phase 5 resolves detected, same-locality armed contact as a spatial and
stochastic engagement. It consumes formation, logistics, information, and
microzone state created by earlier phases. It does not assign a primitive
winner and never writes physical control directly.

## Engagement state

Each `Engagement` records its locality and microzone, formations, asymmetric
detection, initiative, effective capability, personnel/cohesion/readiness
losses, supply expenditure, civilian harm, disengagement, operational
ineffectiveness, reinforcement orders, and a perceived-momentum signal.

Effective capability combines available personnel, quality, cohesion,
effective readiness, local observation, mobility under terrain friction,
embeddedness, and contact initiative. Terrain therefore changes exposure,
observation, mobility/coherence, and civilian risk; it is not a faction bonus.
Independent lognormal shocks turn relative capability into outcome
distributions. Stronger formations have a repeated-trial advantage without a
deterministic victory rule.

## Tactical consequences

An engagement interval consumes conserved Phase 3 supply and reduces readiness.
Personnel loss produces nonlinear cohesion loss. A formation becomes
operationally ineffective when cohesion or effective readiness crosses its
configured threshold, even if personnel remain. An ineffective formation has
zero available presence until logistics recovery restores readiness and
cohesion. Formations may instead disengage and survive.

Reinforcement creates an ordinary `FormationMovementOrder` for an existing
formation. Command reliability, latency, route travel, and movement supply cost
remain owned by the Phase 3 engine; no reinforcement is spawned at the battle.

## Information and politics

Asymmetric detection changes first-interval initiative. This is surprise as a
revealed belief error, not a categorical combat bonus. Each realized engagement
generates explicit `engagement_outcome` observations, which enter the existing
relay system. Local people receive heterogeneous noisy interpretations and
update expected future control. Civilian harm affects those expectations only
through that observation/interpretation path.

Combat changes formation availability, position, stocks, patrol capacity,
violence, and perceived momentum. Subsequent Phase 2 refreshes recompute
microzone presence and control. This preserves the causal rule that battle
changes the causes of control rather than control itself.

## Outputs and scope

`engagements.jsonl` is the event-level analytical record and
`combat_diagnostics.json` summarizes engagement count, civilian harm, formation
losses, and ineffectiveness. The causal ledger records formation personnel,
cohesion, and readiness degradation under the originating contact event.

The model remains an intentionally bounded engagement abstraction. It does not
simulate weapon inventories, fire teams, ballistics, or detailed tactical
maneuver. Those details require separate calibration evidence and are not
needed for the causal integration tested in Phase 5.
