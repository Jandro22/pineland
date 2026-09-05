# Phase 5 combat model

Phase 5 resolves an armed confrontation after the organized-action layer (or
the replayable legacy contact path) has selected a reachable opposing
formation. The resolver consumes formation, logistics, information, and
microzone state. It does not decide whether the actor chose violence, and it
never writes territorial control directly. Other action families are defined
in [the organized action model](action-model.md).

## Resolver boundary

Both formations must be operationally effective, have positive personnel, be
inside Pineland, not be moving, and occupy the same locality and microzone.
These checks are repeated at the resolver boundary even though the scheduler
also excludes ineligible formations. This prevents stale or manually
constructed events from allowing zombie formations to fight.

The caller passes `detected_by`, `initiator_organization_id`, and
`contact_cause`. The v0.13 organized-action path uses
`organized_action_armed_confrontation`; legacy replay can still emit
government-initiated, insurgent-initiated, or accidental contact causes. Cause
is provenance; tactical capability is still computed from formations present.

## Capability

For formation \(f\), the live tactical capability is

\[
X_f=\max\left(\epsilon,
(N_f^{available})^{0.72}
Q_f K_f O_z M_f^{0.35} B_f I_f
\right),
\]

where

- \(N_f^{available}\) is `available_personnel()`, which already contains
  availability and effective readiness;
- \(Q_f\) is quality and \(K_f\) cohesion;
- \(O_z=0.35+0.65\,observability_z\);
- \(M_f\) is mobility divided by terrain friction and bounded to \([0.15,1]\);
- \(B_f=0.55+0.45\,embeddedness_f\); and
- \(I_f\) is the first-interval initiative multiplier.

Effective readiness therefore enters capability **once**, inside available
personnel. Because effective readiness already contains stored readiness,
fatigue, supply, and command, those factors must not be multiplied into
capability again.

If exactly one formation detected the opponent before contact, that formation's
initiative is \(1+\text{surprise_initiative}\); otherwise initiative is 1 for
both. Surprise is thus an information asymmetry at engagement onset rather
than a faction-specific bonus.

## Exposure and casualties

Relative tactical advantage is

\[
\Delta=\log X_a-\log X_b.
\]

Shared engagement exposure is

\[
E_z=\operatorname{clamp}\left(
\frac{observability_z}{\max(0.55,terrain\_friction_z)},0.2,1.35
\right).
\]

Each side's fractional loss is its bounded baseline attrition rate multiplied
by \(E_z\), shifted by relative advantage, and perturbed by an independent
lognormal shock. The realized personnel loss is then the fraction of **assigned
personnel**, not the fraction of available personnel.

That distinction is intentional. Availability limits how much manpower a
formation can put into the fight through capability, but low availability does
not make the rest of its assigned personnel immune to an involuntary attack.
Likewise, a target's low readiness or supply cannot directly suppress the
attacker's contact opportunity.

Losses reduce personnel, readiness, and cohesion. Cohesion damage increases
with realized fractional loss and decreases with formation quality.

## Combat supply and post-contact degradation

After losses, each formation demands combat supply in proportion to surviving
personnel, availability, engagement duration, `supply_per_person_hour`, and
exposure. The conserved logistics subsystem supplies what is available. A
shortfall imposes additional readiness and cohesion degradation.

Supply is therefore used differently at different causal stages:

1. it contributes to effective readiness and thus combat capability;
2. under non-default contact-supply experiments it can affect deliberate
   initiation or a pair-level contact gate; and
3. combat expenditure can generate a post-engagement shortfall.

Those are separate mechanisms, not repeated multipliers on the same decision.

## Disengagement uses actor-local estimates

Disengagement does not inspect the opponent's realized personnel, quality,
cohesion, readiness, or supply. Each formation queries its freshest usable
formation-node or organization-level presence belief for the opponent's
personnel. If no quantitative estimate exists, direct experience of contact
produces a neutral parity prior rather than privileged truth.

The own-force reference is pre-loss assigned personnel multiplied by
availability. Perceived disadvantage is the bounded log ratio of estimated
opponent personnel to that reference. The probability of remaining combines
current cohesion, effective readiness, realized loss fraction, and perceived
disadvantage:

\[
p_{remain}=
\operatorname{logistic}\left(
1.1K_f+R_f^{effective}
-2.1L_f-D_f^{perceived}
\right).
\]

Command is not added separately because it is already contained in effective
readiness. The disengagement draw uses `disengagement_base` plus the live
penalty derived from \(1-p_{remain}\). A disengaging formation loses
availability but is not automatically destroyed. It also attempts to issue an
explicit withdrawal movement order toward a refuge selected from actor-local
beliefs, persistent local-member footholds, and, where present, spatial sponsor
sanctuary. Withdrawal is recorded separately from reinforcement and ordinary
reallocation.

A formation becomes operationally ineffective if personnel reach zero,
cohesion crosses `ineffective_cohesion`, or effective readiness crosses
`ineffective_readiness`. Ineffective formations are excluded from both contact
scheduling and combat resolution until the logistics/recovery process restores
the required state.

## Information, civilians, and control

Each realized engagement creates explicit `engagement_outcome` observations
for the two organizations. Their momentum and civilian-harm estimates are noisy
and can be misattributed. Local political expectations update from these
reported/interpreted values rather than directly from tactical truth.

Combat changes personnel, cohesion, readiness, availability, supply, violence,
and reinforcement demand. It does **not** directly write microzone or locality
control. Later physical-refresh processes recompute presence, response
capacity, and physical control from the changed force state. This preserves
the theory that combat changes the causes of territorial control rather than
assigning a primitive winner-control outcome.

Reinforcement likewise creates an ordinary `FormationMovementOrder` for an
existing effective formation. Command reliability, latency, route travel, and
movement supply remain owned by the logistics subsystem; no reinforcement unit
is spawned at the battle.

## Outputs and scope

`engagements.jsonl` is the latent event-level analytical record.
`combat_diagnostics.json` summarizes engagement count, civilian harm,
formation losses, and ineffectiveness. The causal ledger records personnel,
cohesion, and readiness degradation under the originating contact event.

The model remains a bounded engagement abstraction. It does not simulate
weapon inventories, fire teams, ballistics, or detailed tactical maneuver.
Those omitted mechanisms are structural scope choices, not hidden calibrated
parameters.
