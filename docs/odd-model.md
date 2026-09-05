# ODD model description: current live implementation

This document is the implementation-synchronized ODD-style description of
Pineland COIN-SIM. It describes the **current live working-tree model**, not an
older phase narrative. Subsystem documents provide equation-level detail:

- [social-network semantics](social-network-semantics.md)
- [logistics and force projection](logistics-model.md)
- [information and detection](information-model.md)
- [combat](combat-model.md)
- [organization ecology](organization-ecology.md)
- [parameter roles and defaults](parameters.md)

## 1. Purpose

Pineland COIN-SIM is a partially observed agent-based model for studying
insurgency/counterinsurgency mechanisms across population behavior, social
networks, physical presence/control, logistics, information, organized action,
armed contact,
organization ecology, political order, foreign involvement, and peace
processes.

The model's scientific purpose is mechanism testing and falsification under
explicit uncertainty. Default numeric values are not policy recommendations
and are not automatically empirical estimates.

## 2. Scientific layers

The implementation keeps the following categories distinct:

| Category | Definition | Examples |
|---|---|---|
| **Structural assumption** | Fixed causal form or model architecture. | Persistent organization -> belief-based action -> execution -> observation; armed contact as one channel; no direct combat-to-control write; truth/belief/record separation; weighted representatives. |
| **Engineering prior** | Numerical/scaling choice used to instantiate a tractable synthetic model. | Community represented-size scale; target formation size absent case evidence; synthetic graph construction; sustainment reserve. |
| **Case input** | Exogenous description of the historical or experimental case. | Locality population/coordinates/adjacency/covariates; initial insurgent origins; observed actor-existence intervals. |
| **Calibrated parameter** | A parameter estimated on a declared training target with provenance and then evaluated unchanged on holdout/validation data. | None of the baseline defaults earns this label merely by being present in config. |
| **Latent state** | Realized simulator truth. | True formation personnel/location, supply, control, organization status, engagements. |
| **Actor belief** | Noisy/stale actor-facing estimate derived from evidence. | Presence beliefs, control beliefs, expected control, perceived opponent personnel. |
| **Recorded observable** | Researcher-visible measurement after the recording operator. | Recorded synthetic event, noisy severity, geocoding error. |

Actor-facing `Observation` objects belong to the evidence/belief pipeline, not
the final historical-record layer. Analyst-only diagnostics may expose latent
state or compare truth and belief without making that information actor-known.

## 3. Entities, state variables, and scales

The principal entities are districts/administrative containers, localities,
microzones, weighted persons, households, social communities and edges,
organizations/leaders, armed formations, patrols/fixed posts, command edges,
supply sources/shipments, observations/relays/beliefs, engagements, political
actors/institutions, external states, and peace-process objects.

A `Person.weight` is represented population. Fractional armed participation is
stored in `armed_fraction`, so represented mobilized membership is
\(w_p a_p\). Substantive population/manpower aggregation uses represented
weights; raw node counts are reserved for graph/data-structure operations where
they do not define a substantive threshold.

For armed formation \(f\):

\[
N_f^{deployable}=N_f A_f
\]

unless the formation is moving, outside Pineland, or explicitly ineffective,
in which case deployable personnel is zero. Stored readiness is converted to
fatigue-adjusted readiness and then

\[
R_f^{effective}
=\operatorname{clamp}\left[
R_f^{fatigue}(0.2+0.8S_f)C_f
\right].
\]

Available personnel is \(N_f^{deployable}R_f^{effective}\). This decomposition
prevents readiness, supply, command, and availability from being silently
reintroduced as interchangeable multipliers at every downstream stage.

## 4. Process overview and scheduling

The asynchronous priority scheduler advances distinct processes including
patrol, physical refresh, information collection/fusion, social influence,
mobility, command/reallocation, logistics, contact scanning, recruitment,
organization ecology, governance/economy, political order, foreign affairs,
peace, and checkpoints.

Most process interval settings are numerical schedules. A scientific rate is not
automatically a per-tick probability. Where the live model represents a
continuous-time hazard, including contact and existing-organization
recruitment/exit, the elapsed interval is explicit so scheduler cadence does not
change cumulative calendar-time probability under a fixed latent state.
`intervals.patrol` is partly operational rather than a pure discretization
because it controls opportunities to observe and choose a new patrol route;
however, for a fixed matched patrol dwell history, memory accumulation itself is
integrated by elapsed time and is invariant to how that dwell is numerically
sliced.

### Formation reallocation

`reallocation_rate` is a one-day probability of an idle deployable formation
receiving an allocation opportunity. The command scheduler converts it to its
actual interval with `1-(1-p_day)^dt`; changing only `intervals.command`
therefore does not change the fixed-state calendar-time opportunity
probability. The current locality is included in the random-utility choice, so
an opportunity need not create a movement order.

Allocation reads actor beliefs, organizational phenotype, represented local
armed footholds, known topology/travel cost, known own supply, and public case
geography. It does not read realized territorial control. Confidence shrinks
control estimates toward the uninformative prior before exploitation, while
uncertainty is a separate exploration component. State-aligned formations
respond to perceived territorial insecurity, covering both weak gaps and
believed-threatened strongpoints. Insurgent formations mix frontier expansion,
persistent local armed footholds, stronghold consolidation, and uncertainty;
sponsor-linked external sanctuary contributes through a travel-decaying border
access gradient rather than an organization-wide or exact-border switch.

Shortest-path intermediate localities contribute a perceived opposing-control
corridor penalty moderated by risk tolerance. A destination known to require
more movement supply than the formation currently holds is infeasible at order
issue; stock is checked again after command latency. Transit remains an atomic
deployment abstraction: the route determines travel time, movement cost, and
actor-perceived corridor risk, but the live model does not instantiate separate
en-route combat at every intermediate locality.

### Organized-action path

The v0.13 default separates organizational capacity, action choice, execution,
and observation. Each active insurgent organization/locality with unfielded or
fielded fighter-equivalent capacity receives one common opportunity per
`intervals.contact` exposure. The actor then chooses `wait`, armed
confrontation, a nonfielded human-target attack, asset violence, or nonviolent
coercion from beliefs plus known own capacity. Only execution reads actual
target existence. One selected channel per opportunity supplies a shared
personnel/time budget, and non-battle violent channels consume local material.

Armed confrontation requires an actual reachable opposing formation. A fixed
security post or political institution can support other channels without an
opposing formation. State-based human violence, asset violence, and coercion
remain distinct empirical marks. Recording occurs after a latent outcome.

### Legacy armed-contact path

The default causal path is:

```text
same-locality + same-microzone opposing effective formations
-> one opportunity per opposing formation pair per contact scan
-> existing actor-local presence belief supplies directional detection signal
-> competing government-initiation / insurgent-initiation / accidental rates
-> interval hazard draw
-> realized engagement
-> capability, casualties, expenditure, disengagement/ineffectiveness
-> later physical refresh changes presence/control consequences
-> independent recording operator determines researcher-visible event
```

Under `combat.organized_action_architecture="legacy_contact_only"`,
`contact_rate` is a per-pair, per-day hazard scale. With
`directional_pairwise`:

\[
\lambda_{g\rightarrow i}
=\tfrac12 rP(1-a)A_gC_gD_gS_g^*,
\]

\[
\lambda_{i\rightarrow g}
=\tfrac12 rP(1-a)A_iC_iD_iS_i^*,
\qquad
\lambda_{acc}=rPa,
\]

\[
h(\Delta t)=1-\exp[-\Delta t(
\lambda_{g\rightarrow i}+\lambda_{i\rightarrow g}+\lambda_{acc})].
\]

The scheduler already requires same microzone, so \(P=1\) in current production
events. \(D\) is the freshest usable local presence-belief signal. Availability
and command enter deliberate initiation. Readiness is not multiplied again
after detection. With the default `contact_supply_rule="no_gate"`, supply is
not a direct contact-occurrence factor; optional forensic branches can make
initiator supply continuous/asymmetric or apply an explicit pair-level gate.

Target readiness, availability, supply, and command do not directly suppress
the other side's detection or initiation. A target cannot become harder to
encounter merely by being unready or poorly supplied.

## 5. Design concepts

### Emergence and interaction

Control, recruitment, organization growth/fragmentation, displacement,
political support, and recorded conflict patterns emerge from interacting
population, organizational, physical, logistical, informational, and political
processes. Territorial control is not assigned as a primitive combat winner.

### Adaptation

People revise behavior from private state, beliefs, and normalized social
exposure. Organizations adapt phenotype from observed peer success, can change
leadership, and can split/merge/collapse. Formations recover or degrade through
logistics and combat.

### Sensing and partial observability

Environment/source operators may read latent truth to generate evidence.
Actors receive observations and beliefs, not privileged truth. Detection
probability is conditioned on observer search pressure, observer
fatigue-adjusted readiness, target exposure/embeddedness, language,
observability, terrain, and insurgent concealment.

Target exposure is

\[
E_t=\operatorname{clamp}(0.35+0.45O-0.25B_t).
\]

Observer search pressure uses deployable fraction, quality, cohesion, and
information capacity; it does not reapply supply/command through effective
readiness.

### Stochasticity

Generation, transitions, sensing, contact, combat, and recording use
deterministic named RNG streams. Process-event streams and recording-event
streams are separate:

```text
process:<event_type>
recording:<event_type>
```

Changing output retention or the recording model must not advance latent
transition streams.

### Observation

The model exposes both forensic latent diagnostics and a biased synthetic
historical record. Empirical event targets should normally be compared against
the recorded synthetic layer when the historical source is itself an
incomplete/noisy recording process.

## 6. Initialization and force decomposition

In synthetic mode, the generator constructs the default Pineland district and
locality system, weighted population, households, social network, organizations,
formations, logistics, physical microzones, information state, and later
subsystems from seeded streams.

Initial force structure defaults to `manpower_decomposition`. Government
formation count is derived from represented government manpower and the target
government formation size; insurgent count is derived from represented
insurgent manpower and the target insurgent formation size. Both are bounded by
`maximum_initial_formations_per_side`. This mapping is outcome-independent.

Recruitment-created fighter manpower remains local. It fills local effective
formations toward target size, then accumulates in an organization/locality
manpower pool and creates additional formations once the minimum fieldable
threshold is met.

## 7. Empirical geography input contract

`_replace_with_empirical_geography` changes **case inputs only**. It does not
change model equations or add case-specific bonuses. Three schema versions are
accepted:

| Schema | Administrative/container representation |
|---|---|
| `1.0.0` | `containers` plus `localities`. |
| `2.0.0` | `districts` plus named `regions` and `zones`; each district stores region/zone hierarchy IDs. |
| `3.0.0` | `districts` plus generic `geographic_containers`; containers have unique `container_id` and optional validated `parent_id`, while districts can carry a `container_ids` hierarchy map. |

All schemas require nonempty localities and administrative containers and
require `config.locality_count` to equal the empirical locality count. Each
locality requires identity/name, population, and \(x/y\) coordinates; optional
case covariates include infrastructure, administrative capacity, terrain
friction, observability, economic output, kind, and administrative role.

District/container population must equal the exact sum of its runtime
localities. The supplied `adjacency` mapping defines **which** locality pairs
are connected; the runtime edge cost is then recomputed from coordinate
distance and terrain. Empty adjacency or isolated localities is rejected.

Empirical population sampling preserves every locality: `agent_count` must be
at least the locality count, one representative is guaranteed per locality,
and remaining representatives are apportioned by population so each locality's
represented population is exact.

`initial_insurgent_locality_ids` is an optional case input. Supplied origins
are retained and additional initial insurgent formation tokens spread outward
through the exogenous geography graph. Without supplied origins, placement
uses administrative capacity plus a force-generation stream that is separate
from civilian population-generation randomness.

## 8. Recruitment access and organization persistence

Existing-organization recruitment uses frozen access channels at the start of
each recruitment interval. With `recruitment_requires_access=true`, a
representative is eligible only if the organization has a physically available
local formation (effective, positive-personnel, not moving, and not outside
Pineland), an already armed member locally, or the representative has positive
stored network exposure. A formation in transit therefore neither supplies
local formation access nor absorbs newly recruited local fighter manpower.
Persistent local armed membership and network exposure remain distinct
clandestine/recruitment footholds after fielded formations depart; they do not
directly write physical control.

Weighted recruitment/exit is bounded through
`recruitment_subcohorts`. Each eligible subcohort receives an interval
probability obtained from the continuous daily hazard,
\(p=1-\exp(-\lambda\Delta t)\), so multiple subcohorts may transition in a
long interval without changing the fixed-state calendar-time hazard simply
because the numerical recruitment schedule is subdivided. The represented
membership delta is \(w_p\Delta a_p\). Only
`fighter_conversion_fraction` becomes fielded formation manpower.

For empirical designs, `observed_active_intervals` conditions **actor identity
persistence**. During an observed-active window, the ecology suppresses split,
collapse, and merger involving that named actor. It does not freeze
recruitment, combat, casualties, movement, command, resources, cohesion,
adaptation, or succession. The field is therefore a case-existence constraint,
not a success bonus or calibrated lifecycle parameter.

## 9. Truth, belief, and record firewall

The runtime exposes explicit read-only views:

- `WorldTruthView`: privileged environment/analyst access to realized state.
- `ActorBeliefView`: actor-facing estimates with no realized-control shortcut.
- `EmpiricalRecordView`: immutable researcher-facing recorded events only.

Actor-controlled decisions should consume beliefs, direct experience, or public
state. Environment evolution and observation operators may legitimately read
truth. Analyst diagnostics may compare truth and beliefs. Synthetic recording
occurs after latent transition and uses its own RNG namespace; false records
never enter latent event truth or the causal ledger.

## 10. Submodel boundaries that must remain explicit

- Logistics governs supply, readiness/recovery, availability, movement, and
  command connectivity.
- Information governs source sampling, detection, belief fusion, aging, and
  relay.
- Contact opportunity governs encounter occurrence and directional initiation.
- Combat governs capability, losses, expenditure, disengagement, and
  ineffectiveness after a contact realizes.
- Physical refresh governs the territorial-control consequences of changed
  presence and response capacity.
- The recording operator governs what a researcher would observe.

These boundaries are scientific bookkeeping, not merely software modularity:
they prevent readiness, supply, information, and command from being counted
multiple times and prevent observed data from feeding back into actor decisions
as hidden truth.
