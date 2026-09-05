# Organized action and event model

Pineland v0.13 separates persistent organizational state from its intermittent
expression as violence. The causal order is:

`state -> observation -> belief -> action choice -> execution -> latent event -> recorded observation`.

The action layer reuses existing accounts. Represented membership is a source
population, not fighter strength. Local fighter-equivalent capacity is the
local organization manpower pool plus local `ArmedFormation.personnel`, counted
exactly once. Formation materialization and relocation therefore change form or
geography without creating capacity.

A common continuous-time opportunity clock uses
`1 - exp(-contact_rate * capacity_saturation * elapsed_days)`. The saturation
scale reuses `minimum_formation_personnel`; it is smooth, so crossing a
formation threshold cannot switch every action family from impossible to possible.

After an opportunity, the actor chooses one of `wait`, armed confrontation,
violence against a nonfielded human target, violence against an asset, or
nonviolent coercion. Choice reads actor beliefs and known own capacity only.
Target truth is consulted only during execution. One organization/locality
action event can select at most one channel per interval, supplying a shared
personnel/time budget. Non-battle violent attempts consume only local formation
or organization supply-source stock using the existing combat expenditure scale.

Armed confrontation still requires mutually reachable effective opposing
formations and uses the existing combat resolver. A nonfielded human-target
attack can instead target explicit fixed security-post personnel. Asset
violence targets an explicit local political institution. Coercion produces a
compliance outcome but does not automatically manufacture resources or control.

Only armed confrontation and realized violence against a nonfielded government
human target carry the `state_based_violence` empirical mark. Asset violence
and nonviolent coercion are separate marks. Recording remains downstream.

`combat.organized_action_architecture="legacy_contact_only"` preserves the v4
contact scheduler for exact replay. The v0.13 default is `multichannel_v5`.
The architecture was promoted only after the data-free battery in
`studies/research_program/v5_action_architecture_validation.json`; historical
fit did not set its equations, and COIN intervention claims remain gated.

