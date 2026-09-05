# Phase 3 logistics and force projection

## Scientific question

How much armed presence can an organization actually sustain across space?

Phase 3 distinguishes assigned personnel, deployment availability, stored
readiness, fatigue-adjusted readiness, and composite effective readiness. For
formation \(f\):

\[
N_f^{available} = N_f A_f R_f^{effective}.
\]

The live implementation defines

\[
R_f^{fatigue}=\operatorname{clamp}\left(R_f(1-0.65F_f)\right),
\]

\[
R_f^{effective}=\operatorname{clamp}\left[
R_f^{fatigue}(0.2+0.8S_f)C_f
\right],
\]

where \(A_f\) is availability, \(F_f\) fatigue, \(S_f\) the bounded supply
fraction, and \(C_f\) command connectivity/reliability. `deployable_personnel`
is \(N_fA_f\) and becomes zero while moving, outside Pineland, or explicitly
ineffective; `available_personnel` then applies effective readiness. A
formation can therefore retain unchanged assigned manpower while losing most
of its usable presence.

## Supply conservation

Formation and source stocks use explicit sources, sinks, transfers, and losses:

\[
S(t) = S(0) + Production - Consumption - Losses.
\]

In-transit deliverable shipments remain part of current stock. A shipment withdraws its sent quantity from the source immediately; the difference between sent and deliverable quantity is recorded as loss. On delivery, the deliverable amount enters formation stock. Every update is checked against the conservation identity.

Consumption is separated into sustained presence, locality movement, and patrol activity. A movement order cannot depart without its full movement requirement. No stock is allowed below zero.

Source capacity is attached to the full administrative catchment represented by
the source locality. This matters when an empirical adapter represents
historical districts as localities nested inside larger containers: sizing a
source to only the hub locality silently changes the units from
`units/resident-of-catchment` to `units/resident-of-hub` and can make the
formation supply system impossible by construction.

## Movement and deployment

Formation movement follows a shortest path over the existing locality graph. Each leg derives distance and duration from connectivity cost, terrain, infrastructure, and formation mobility. Orders include:

- origin and destination;
- complete route;
- command issue and execution times;
- travel duration and distance;
- movement supply cost;
- command reliability and latency;
- explicit pending, failed, blocked, moving, and arrived states.

Commanders select destinations from actor-specific locality beliefs. Model truth
is not used in allocation utility. A low-confidence control estimate is shrunk
toward the uninformative 0.5 prior before exploitation; uncertainty enters
separately as an exploration term. This prevents a low-confidence extreme
estimate from remaining an extreme strategic signal.

Every reallocation choice includes the formation's **current locality**. A
reallocation opportunity therefore does not force purposeless movement. The
one-day opportunity probability `reallocation_rate` is converted to command
interval \(\Delta t\) as

\[
p_{\Delta t}=1-(1-p_{day})^{\Delta t},
\]

so `intervals.command` is a numerical schedule rather than a hidden movement
rate.

State-aligned formations use perceived territorial insecurity

\[
N_j = 1-C^{own}_j(1-C^{opp}_j),
\]

which is high both in low-own-control gaps and in strongpoints believed to be
contested. Insurgent formations use the declared structural portfolio of
frontier opportunity, persistent represented armed footholds, stronghold
consolidation, and uncertainty-driven exploration. External sanctuary is then
mapped onto a **spatial sponsor-border access gradient** using sponsor
dependence, border permeability/monitoring/infrastructure/terrain, and travel
cost; it is neither an organization-wide teleport bonus nor an exact-border
binary switch.

For either side, believed opposing control on intermediate shortest-path
localities creates a corridor-risk penalty moderated by organizational risk
tolerance. Destination utility combines strategic value, normalized locality
importance, travel time, and that route risk. A destination whose movement
supply cost already exceeds the formation's known stock is excluded at order
issue; supply is revalidated again after command latency because intervening
demands can still make a previously feasible order fail.

While moving, a formation has zero locally available personnel, its patrol is
unavailable, and its formation-linked post loses formation-derived presence.

Movement orders record their operational purpose. Ordinary reallocation and
reinforcement require an effective deployable formation. A combat formation
that explicitly disengages may instead receive a `withdrawal` order toward a
belief-defined refuge; a damaged or temporarily ineffective unit with surviving
personnel can therefore break contact and move rather than being forced to
recover at the battle site.

## Command graph

Each organization begins with an HQ node linked to its formations. Every command edge carries reliability and latency. Command-path reliability is the product of edge reliabilities; latency is additive. Orders can fail before execution, and successful orders execute only after communications delay.

The initial graph is deliberately simple. It demonstrates coordination constraints without encoding doctrine.

## Readiness and recovery

Daily sustainment demand depends on assigned personnel and current availability. A shortfall reduces readiness and availability and increases fatigue. A fully supplied formation recovers, with faster recovery at an operational source locality than at a remote deployment.

This makes logistics constrain deployment and presence directly. It is not merely a combat modifier.

## Contact occurrence versus combat capability

The default contact model is `directional_pairwise`. `contact_rate` is a
**per-opposing-formation-pair, per-day hazard scale**, not a probability per
scheduler tick. Once a government/security formation and an active insurgent
formation occupy the same microzone, the two deliberate initiation rates and
the accidental co-presence rate are

\[
\lambda_{g\rightarrow i}
= \tfrac12 r_{contact}P(1-a)A_gC_gD_gS_g^*,
\]

\[
\lambda_{i\rightarrow g}
= \tfrac12 r_{contact}P(1-a)A_iC_iD_iS_i^*,
\qquad
\lambda_{acc}=r_{contact}Pa,
\]

and over an exposure interval \(\Delta t\)

\[
h(\Delta t)=1-\exp\left[-\Delta t
(\lambda_{g\rightarrow i}+\lambda_{i\rightarrow g}+\lambda_{acc})\right].
\]

Here \(D\) is the already-held actor-local presence-belief signal, \(A\) is
availability, \(C\) is command, \(a\) is `accidental_contact_fraction`, and
\(P\) is the pair-proximity factor (currently 1 after same-microzone
qualification). The factor \(1/2\) keeps two fully active deliberate sides from
silently doubling the nominal pair hazard. Explicit \(\Delta t\) conversion
makes cumulative calendar-time probability invariant to the contact-scan
cadence.

With the default `contact_supply_rule="no_gate"`, \(S_f^*=1\): supply is not a
direct contact-occurrence multiplier or symmetric target gate. The
`continuous` and `initiation_asymmetry` branches apply supply only to the
prospective initiator; `hard_gate` and `ammunition_floor` are retained
pair-level diagnostic gates. Readiness is likewise not multiplied again in the
directional initiation rate: readiness/search effectiveness belongs to the
information/detection process, while availability and command enter deliberate
initiation once. Supply and readiness still matter strongly for deployable
presence, detection history, combat capability, expenditure shortfall,
ineffectiveness, recovery, and subsequent control.

`legacy_symmetric` remains available only as a compatibility/forensic branch.
It uses the older symmetric effective-readiness formulation and should not be
described as the current default theory.

## Physical-control coupling

Current formation presence uses effective available strength. Formation-linked
post presence, current formation presence, and response capacity disappear while
the formation is moving and decline with readiness, availability, supply,
fatigue, or command degradation. Explicit patrols additionally create a
separate decaying memory stock from the deployed patrol fraction
(`response_fraction`) integrated over completed dwell time. Completed dwell is
accounted before scheduled state-changing events, so movement or logistics
updates cannot retroactively apply a new formation state to an earlier patrol
exposure window. Microzone physical control remains upstream of locality
physical control.

When those constraints change locality physical control, provenance is recorded as `logistics_constrained_physical_aggregation`.

## Control cost and sustainability

Government security-resource consumption is accumulated by locality. Diagnostics report total supply units per day, units per 1,000 residents per day, physical control, and an initial cost-adjusted sustainability measure:

\[
Sustainability_m = \frac{C_m^{physical}}{1 + Cost_{m,per\ 1000}}.
\]

This dashboard diagnostic is not a calibrated welfare function. Its purpose is to distinguish similar control levels maintained at sharply different continuing costs.

## Scope boundary

Logistics remains a distinct stock-and-flow subsystem. The bounded combat
resolver consumes its formation stocks and readiness, while territorial control
is still updated only by the physical refresh process.
