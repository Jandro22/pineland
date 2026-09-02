# Phase 3 logistics and force projection

## Scientific question

How much armed presence can an organization actually sustain across space?

Phase 3 distinguishes nominal assigned personnel from effective available personnel. For formation (f):

\[
N_f^{available} = N_f A_f R_f^{effective}.
\]

Effective readiness combines the stored readiness state with supply fraction, fatigue, and command reliability. A formation can therefore retain unchanged nominal manpower while losing most of its usable presence.

## Supply conservation

Formation and source stocks use explicit sources, sinks, transfers, and losses:

\[
S(t) = S(0) + Production - Consumption - Losses.
\]

In-transit deliverable shipments remain part of current stock. A shipment withdraws its sent quantity from the source immediately; the difference between sent and deliverable quantity is recorded as loss. On delivery, the deliverable amount enters formation stock. Every update is checked against the conservation identity.

Consumption is separated into sustained presence, locality movement, and patrol activity. A movement order cannot depart without its full movement requirement. No stock is allowed below zero.

## Movement and deployment

Formation movement follows a shortest path over the existing locality graph. Each leg derives distance and duration from connectivity cost, terrain, infrastructure, and formation mobility. Orders include:

- origin and destination;
- complete route;
- command issue and execution times;
- travel duration and distance;
- movement supply cost;
- command reliability and latency;
- explicit pending, failed, blocked, moving, and arrived states.

Commanders select destinations from actor-specific locality beliefs. Model truth is not used in allocation utility. While moving, a formation has zero locally available personnel, its patrol is unavailable, and its formation-linked post loses formation-derived presence.

## Command graph

Each organization begins with an HQ node linked to its formations. Every command edge carries reliability and latency. Command-path reliability is the product of edge reliabilities; latency is additive. Orders can fail before execution, and successful orders execute only after communications delay.

The initial graph is deliberately simple. It demonstrates coordination constraints without encoding doctrine.

## Readiness and recovery

Daily sustainment demand depends on assigned personnel and current availability. A shortfall reduces readiness and availability and increases fatigue. A fully supplied formation recovers, with faster recovery at an operational source locality than at a remote deployment.

This makes logistics constrain deployment and presence directly. It is not merely a combat modifier.

## Physical-control coupling

Patrol presence uses effective available strength. Formation-linked post presence and response capacity disappear while the formation is moving and decline with readiness, availability, supply, fatigue, or command degradation. Microzone physical control remains upstream of locality physical control.

When those constraints change locality physical control, provenance is recorded as `logistics_constrained_physical_aggregation`.

## Control cost and sustainability

Government security-resource consumption is accumulated by locality. Diagnostics report total supply units per day, units per 1,000 residents per day, physical control, and an initial cost-adjusted sustainability measure:

\[
Sustainability_m = \frac{C_m^{physical}}{1 + Cost_{m,per\ 1000}}.
\]

This dashboard diagnostic is not a calibrated welfare function. Its purpose is to distinguish similar control levels maintained at sharply different continuing costs.

## Scope boundary

Phase 3 does not deepen combat. The inherited coarse contact event remains only for regression coverage. Formation routing, stocks, command, readiness, availability, presence, and control costs are tested independently before a later combat phase.
