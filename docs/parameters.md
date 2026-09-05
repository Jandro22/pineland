# Parameter registry and scientific-role vocabulary

The live configuration contains several kinds of quantities that must not be
collapsed into the word "parameter." This document uses the following roles:

| Role | Meaning in the live model |
|---|---|
| **Structural assumption** | Equation form, causal ordering, state partition, gate/branch, or topology rule fixed as part of the model theory. |
| **Engineering prior** | Scaling, resolution, numerical, or synthetic-construction choice needed to instantiate the model but not inferred from conflict outcomes. |
| **Case input** | Exogenous historical/case description such as empirical geography, population, adjacency, initial actor origin, or an observed actor-existence interval. |
| **Calibrated parameter** | A scalar actually estimated against a declared training target with provenance and then carried unchanged into validation/holdout use. A plausible trajectory is not calibration. |
| **Latent state** | Realized simulator truth such as formation personnel, supply, true presence/control, or a latent engagement. It evolves; it is not a parameter. |
| **Actor belief** | An actor/person estimate derived from observations, such as control or presence belief. Decisions may read it; analysts must not treat it as truth. |
| **Recorded observable** | A researcher-visible value that passed the synthetic recording/measurement operator. It is distinct from both latent truth and actor evidence. |

Most numeric defaults below are uncalibrated scientific or engineering priors.
Numerical schedules are fixed implementation contracts unless deliberately
studied. Case inputs are documented separately and should not be fitted as if
they were generic mechanism coefficients. The machine-readable
`parameter-registry` is the exported scalar catalog; where this audit marks
an exposed field inactive/reserved, actual live code usage takes precedence
over generic registry classification.

An `Observation` in the information subsystem is **actor evidence**, not the
same object as a recorded historical observable. `SyntheticRecord.recorded`
defines the latter layer.

## Core rates and schedules

| Name | Meaning | Units / bounds | Default | Scientific role |
|---|---|---:|---:|---|
| `contact_rate` | Common organized-action opportunity rate scale in `multichannel_v5`; legacy opposing-pair contact scale in `legacy_contact_only` | rate/day, nonnegative | 0.08 | Experimental treatment; uncalibrated; not fit from Nepal/Afghanistan |
| `intervals.contact` | Organized-action/contact scan interval; hazard conversion uses explicit elapsed time | days, positive | 1.0 | Numerical schedule, not an action probability |
| `combat.organized_action_architecture` | Belief-based multichannel generation or exact legacy contact scheduling | enum | `multichannel_v5` | Structural theory switch; `legacy_contact_only` is provenance replay |
| `recruitment_rate` | Continuous-time existing-organization recruitment hazard scale | rate/day, nonnegative | 0.001 | Experimental treatment; uncalibrated |
| `membership_exit_rate` | Continuous-time armed-membership exit/desertion hazard scale | rate/day, nonnegative | 0.001 | Experimental treatment; uncalibrated; baseline equals the former shared hazard for numerical continuity |
| `intervals.recruitment` | Recruitment/retention update interval | days, positive | 7.0 | Numerical schedule |
| `organization_ecology.exit_sympathy_retention` | Conditional probability that a full armed-membership exit retains an insurgent-sympathetic public signal | [0, 1] | 1.0 | Experimental treatment; legacy structural assumption made explicit, not empirically tuned |
| `organization_ecology.local_rootedness_weight` | Effect of constituency/franchise local rootedness on recruitment utility among locally salient civilians | logit utility coefficient, [0, 3] | 0.75 | General-theory prior; uncalibrated; synthetic monotonicity and zero-salience recovery required |

`contact_rate` and the state-dependent recruitment/exit hazards are converted
through \(1-\exp(-\lambda\Delta t)\). In v0.13 `contact_rate` supplies a
common opportunity scale rather than a new attack-specific fitted coefficient;
action choice is a separate belief-based distribution. Holding state and
intensity fixed, cadence changes must not alter cumulative calendar-time probability.

Recruitment and membership exit deliberately have separate hazard scales.
Joining and retention/desertion are distinct organizational processes; forcing
them to share one rate made any change in mobilization capacity mechanically
change membership loss at the same time. Legacy serialized configurations that
lack `membership_exit_rate` inherit their stored `recruitment_rate`, preserving
the pre-split numerical model when old experiments are reloaded.

| Name | Meaning | Units / bounds | Default | Calibration status |
|---|---|---:|---:|---|
| `community_size_unit_population` | Represented residents per legacy community-size unit; makes community partition semantics independent of simulated-agent resolution | represented people/unit, positive | 120 | Scaling anchor; vary in robustness checks |
| `target_community_size` | Preferred represented social-community size in `community_size_unit_population` units | units, positive | 100 (≈12,000 people) | Engineering/scaling prior |
| `minimum_community_size` | Lower represented-population packing target | units, positive | 50 (≈6,000 people) | Engineering/scaling prior |
| `maximum_community_size` | Upper represented-population packing target | units, positive | 150 (≈18,000 people) | Engineering/scaling prior |
| `mean_social_degree` | Target mean regular ties before household and bridge effects | ties/person | 8.0 | Prior; benchmark against sampled degree data |
| `maximum_social_degree` | Cap used while adding ordinary community ties | ties/person | 24 | Computational prior |
| `bridge_fraction` | Share of community members considered as cross-community brokers | [0, 1] | 0.03 | Prior; sensitivity required |
| `behavior_update_rate` | Daily probability that an individual revises public behavior | [0, 1]/day | 0.12 | Prior; sensitivity required |
| `household_tie_strength` | Pre-language baseline household edge weight | [0, 1] | 0.95 | Prior |
| `community_tie_strength` | Pre-language baseline ordinary community edge weight | [0, 1] | 0.65 | Prior |
| `bridge_tie_strength` | Pre-language baseline cross-community edge weight | [0, 1] | 0.45 | Prior |
| `behavior_exposure_weight` | Contribution of normalized network exposure to public-behavior utility | nonnegative utility coefficient | 0.35 | Prior; sensitivity required |
| `recruitment_exposure_weight` | Reserved legacy field; the live `recruit_and_retain` equation does not read this coefficient | nonnegative | 0.25 | Inactive/reserved; do not calibrate as an active mechanism |
| `intervals.social_influence` | Time between network exposure/behavior events | days, positive | 1.0 | Numerical schedule |

Effective edge weight is currently `base_strength * (0.35 + 0.65 * language_compatibility)`, where language compatibility is the highest shared proficiency across the four languages. This preserves cross-language interaction while making comprehension consequential.

Social-control changes use the represented population share whose observable behavior changed, scaled by `0.01` per influence event. This constant should move into the formal parameter registry in the next parameter-centralization pass.

## Phase 2 physical occupation

| Name | Meaning | Units / bounds | Default | Calibration status |
|---|---|---:|---:|---|
| `village_microzones` | Internal zones per village cluster | count | 3 | Resolution prior |
| `town_microzones` | Internal zones per town | count | 5 | Resolution prior |
| `city_microzones` | Internal zones per city locality | count | 8 | Resolution prior |
| `extra_edge_probability` | Probability of a non-backbone internal road connection | [0, 1] | 0.22 | Synthetic topology prior |
| `presence_memory_days` | Exponential memory time constant for recent patrol presence | days, positive | 2.0 | Prior; sensitivity required |
| `response_decay_hours` | Time constant mapping response time into response capability | hours, positive | 0.75 | Prior; sensitivity required |
| `formation_presence_gain` | Scale converting current effective formation strength into instantaneous microzone presence | [0, 1] | 0.35 | Prior |
| `patrol_memory_gain` | Scale converting explicitly deployed patrol strength into the target amplitude of decaying patrol memory | [0, 1] | 0.35 | Prior |
| `fixed_post_presence_gain` | Scale converting fixed-post capacity into local presence | [0, 1] | 0.25 | Prior |
| `zone_observation_noise` | Maximum initial/noise amplitude for zone-control observations | [0, 1] | 0.12 | Prior |
| `patrol_route_randomness` | Bounded route-choice utility perturbation | [0, 1] | 0.15 | Prior |
| `intervals.physical_refresh` | Time between decay, response, and aggregation updates | days, positive | 0.25 | Numerical schedule |
| `intervals.patrol` | Patrol observation/routing opportunity cadence | days, positive | 0.25 | Operational schedule; changing it can change patrol paths, but not the memory generated by a fixed matched dwell history |

Legacy configuration files containing `patrol_presence_gain` remain loadable:
the loader maps that old scalar to both `formation_presence_gain` and
`patrol_memory_gain`. New configurations expose the two mechanisms
independently so current occupation cannot be mistaken for residual patrol
memory.

## Phase 3 logistics and force projection

Supply is measured in abstract person-sustainment units. Distances are synthetic kilometers and travel durations are hours. These units make conservation and comparative costs explicit while remaining uncalibrated.

| Name | Meaning | Units / bounds | Default | Calibration status |
|---|---|---:|---:|---|
| `formation_supply_days` | Maximum formation supply capacity at nominal personnel | person-days | 30.0 | Prior |
| `initial_supply_fraction` | Initial fraction of formation capacity filled | [0, 1] | 0.8 | Scenario prior |
| `presence_consumption_per_person_day` | Supply consumed by one assigned-and-available person during sustained deployment | units/person-day | 0.75 | Prior; sensitivity required |
| `movement_consumption_per_person_km` | One-time deployment movement cost | units/person-km | 0.02 | Prior |
| `patrol_consumption_per_person_hour` | Additional supply cost of patrol activity | units/person-hour | 0.002 | Prior |
| `source_capacity_per_resident` | District support-source capacity relative to population | units/resident | 0.05 | Synthetic prior |
| `source_daily_production_fraction` | Daily source replenishment as a capacity fraction | [0, 1]/day | 0.03 | Prior |
| `source_capacity_model` | Supply-source sizing rule: organization manpower demand or population catchment | enum | `organization_manpower` | Structural branch; default chosen to prevent population-proxy supply imbalance |
| `organization_sustainment_coverage` | Ex-ante source production reserve above stationary organization demand | positive multiplier | 1.20 | Engineering prior; not an event-outcome calibration target |
| `resupply_trigger_fraction` | Stock fraction below which a formation requests shipment | [0, 1] | 0.45 | Policy prior |
| `resupply_target_fraction` | Requested post-delivery stock target | [0, 1] | 0.85 | Policy prior |
| `shipment_loss_per_travel_hour` | Exponential shipment attrition rate | nonnegative/hour | 0.002 | Prior |
| `convoy_speed_factor` | Supply movement speed relative to formation mobility | positive multiplier | 0.75 | Prior |
| `readiness_degradation_rate` | Readiness loss from unmet daily sustainment demand | [0, 1]/day | 0.08 | Prior |
| `readiness_recovery_near_source` | Supplied readiness recovery at a source locality | [0, 1]/day | 0.025 | Prior |
| `readiness_recovery_remote` | Supplied readiness recovery away from a source | [0, 1]/day | 0.006 | Prior |
| `availability_recovery_rate` | Supplied availability recovery | [0, 1]/day | 0.03 | Prior |
| `reallocation_rate` | One-day probability that an idle formation receives a reallocation opportunity; converted to the actual command interval by `1-(1-p)^dt` | [0, 1]/day | 0.04 | Scenario prior; cadence-invariant |
| `insurgent_frontier_weight` | Share of insurgent strategic allocation value assigned to expansion where own establishment and perceived government reach are weak | [0, 1] | 0.50 | Structural theory prior; synthetic falsification required |
| `insurgent_foothold_weight` | Share assigned to persistent represented armed-member footholds independent of current formation occupancy | [0, 1] | 0.25 | Structural theory prior; synthetic falsification required |
| `insurgent_stronghold_weight` | Share assigned to consolidation of believed own control | [0, 1] | 0.15 | Structural theory prior; synthetic falsification required |
| `reallocation_exploration_weight` | Explicit uncertainty-driven exploration share; uncertainty is separate from the confidence-shrunk exploitation estimate | [0, 1] | 0.10 | Structural theory prior; synthetic falsification required |
| `reallocation_strategic_weight` | Log-utility scale on strategic destination value | nonnegative | 2.0 | Policy prior; sensitivity required |
| `reallocation_importance_weight` | Log-utility scale on normalized locality population importance | nonnegative | 0.5 | Policy prior; sensitivity required |
| `reallocation_travel_time_weight` | Log-utility penalty per travel hour; also supplies the distance decay scale for sponsor-border sanctuary access | nonnegative/hour | 0.03 | Mobility-policy prior; sensitivity required |
| `intervals.command` | Command decision interval | days | 1.0 | Numerical schedule |
| `intervals.force_movement` | Pending/deployed movement-order update interval | days | 0.25 | Numerical schedule |
| `intervals.logistics` | Production, consumption, shipment, and recovery interval | days | 1.0 | Numerical schedule |

### Force-token decomposition

`SimulationConfig.force_structure` maps represented side manpower to
formation tokens before outcomes occur. It is a scaling/representation layer,
not a combat-result fit.

| Name | Meaning | Default | Scientific role |
|---|---|---:|---|
| `mode` | Initial force-token construction | `manpower_decomposition` | Structural assumption; `legacy` retained for comparison |
| `government_target_personnel` | Target represented personnel per government formation | 3,500 | Engineering/force-structure prior unless case-sourced |
| `insurgent_target_personnel` | Target represented personnel per insurgent formation | 1,000 | Engineering/force-structure prior unless case-sourced |
| `maximum_initial_formations_per_side` | Safety cap on initial force tokens | 64 | Engineering safeguard |

The generated formation count is based on total represented side manpower and
these target sizes. Recruitment-created fighter manpower subsequently remains
local: it fills local formations toward the insurgent target size and then
accumulates in organization/locality manpower pools until a new formation can
materialize.

## Phase 4 observation and intelligence

Information parameters are exposed through `SimulationConfig.information`.
They are uncalibrated priors intended for sensitivity and identifiability
work, not empirical estimates.

| Name | Meaning | Units / bounds | Default |
|---|---|---:|---:|
| `prior_confidence` | Initial precision of an actor's information prior | [0, 1] | 0.28 |
| `default_decay_rate` | Confidence decay for general/control information | /day, nonnegative | 0.08 |
| `mobile_decay_rate` | Confidence decay for mobile or activity reports | /day, nonnegative | 0.55 |
| `static_decay_rate` | Confidence decay for administrative/static reports | /day, nonnegative | 0.025 |
| `road_decay_rate` | Confidence decay for road/infrastructure reports | /day, nonnegative | 0.045 |
| `formation_decay_rate` | Confidence decay for formation-presence information | /day, nonnegative | 0.65 |
| `true_positive_rate` | Baseline formation detection probability before conditions | [0, 1] | 0.72 |
| `false_positive_rate` | Baseline false-alarm probability when no target is present | [0, 1] | 0.035 |
| `attribution_error_rate` | Probability that a positive detection is attributed to the wrong organization | [0, 1] | 0.08 |
| `contact_true_positive_rate` | Baseline detection probability for a candidate contact | [0, 1] | 0.82 |
| `contact_false_positive_rate` | Contact false-alarm probability | [0, 1] | 0.02 |
| `detection_pressure_bonus` | Coefficient on observer deployable search pressure | nonnegative logit coefficient | 0.65 |
| `detection_exposure_bonus` | Coefficient on target exposure derived from observability and embeddedness | nonnegative logit coefficient | 0.70 |
| `detection_language_bonus` | Coefficient on language comprehension | nonnegative logit coefficient | 0.50 |
| `detection_observability_bonus` | Direct zone/locality observability coefficient | nonnegative logit coefficient | 0.70 |
| `detection_readiness_bonus` | Coefficient on observer fatigue-adjusted readiness | nonnegative logit coefficient | 0.55 |
| `detection_terrain_penalty` | Locality terrain-friction penalty | nonnegative logit coefficient | 0.55 |
| `insurgent_concealment` | Base concealment term, modulated by insurgent dispersion phenotype | [0, 1] | 0.25 |
| `civilian_report_rate` | Availability rate for civilian reporting | [0, 1] | 0.18 |
| `social_report_rate` | Availability rate for network-mediated reporting | [0, 1] | 0.22 |
| `administrative_report_rate` | Availability rate for government administrative reports | [0, 1] | 0.28 |
| `elite_report_rate` | Availability rate for political/local elite reports | [0, 1] | 0.16 |
| `member_report_rate` | Availability rate for organization-member reports | [0, 1] | 0.35 |
| `fixed_post_report_rate` | Availability rate for fixed security-post reports | [0, 1] | 0.72 |
| `patrol_report_rate` | Patrol report availability multiplier | [0, 1] | 1.0 |
| `relay_base_reliability` | Fallback command-network reliability for unmodeled source nodes | [0, 1] | 0.86 |
| `relay_max_hops` | Maximum command-network relay path length | positive count | 8 |
| `contradiction_penalty` | Confidence penalty for disagreement across evidence | [0, 1] | 0.45 |
| `corroboration_bonus` | Weight bonus for independent recent reports | [0, 1] | 0.12 |
| `observation_retention_days` | Optional bounded evidence-archive retention; zero keeps full history | days, nonnegative | 0.0 |
| `intervals.information` | Collection, fusion, aging, and relay-delivery interval | days | 0.25 |

`source_trust`, `source_coverage`, `source_latency_hours`, and
`source_correlation` are maps keyed by
source type (`patrol`, `fixed_post`, `civilian`, `social_network`,
`administrative`, `organization_member`, `political_elite`, `interpreter`, and
`contact`). Observation fusion accounts for intrinsic confidence, source
quality/trust, language comprehension, age decay, source dependence, and
corroboration.

The detection equation uses **observer** fatigue-adjusted readiness and
deployable search pressure. It does not contain target readiness, target
availability, target supply, or target command as direct detection suppressors.

## Phase 5 combat parameters

| Parameter | Meaning | Default |
|---|---|---:|
| `interval_hours` | Duration represented by one engagement resolution | 2.0 |
| `base_attrition_rate` | Baseline fractional attrition hazard | 0.012 |
| `stochastic_sigma` | Lognormal tactical outcome dispersion | 0.42 |
| `max_loss_fraction` | Per-interval personnel-loss ceiling | 0.12 |
| `cohesion_loss_multiplier` | Converts exposure/loss into cohesion damage | 1.8 |
| `readiness_cost_multiplier` | Converts engagement intensity into readiness loss | 1.1 |
| `supply_per_person_hour` | Engagement supply demand | 0.035 |
| `ineffective_cohesion` | Cohesion ineffectiveness threshold | 0.22 |
| `ineffective_readiness` | Effective-readiness ineffectiveness threshold | 0.18 |
| `disengagement_base` | Baseline opportunity to disengage | 0.16 |
| `surprise_initiative` | First-interval initiative from asymmetric detection | 0.28 |
| `civilian_exposure_rate` | Population-at-risk harm scaling | 0.00008 |
| `momentum_learning_rate` | Expected-control response to perceived performance | 0.12 |
| `reinforcement_threshold` | Fractional loss prompting an assistance request | 0.06 |
| `contact_supply_rule` | Contact/logistics policy (`no_gate` default; diagnostic `hard_gate`, `continuous`, `ammunition_floor`, `initiation_asymmetry`) | `no_gate` |
| `contact_ammunition_floor` | Minimum supply ratio for the diagnostic ammunition-floor branch | 0.05 |
| `accidental_contact_fraction` | Fraction of nominal pair rate assigned to accidental co-presence rather than deliberate initiation | 0.05 |
| `contact_opportunity_model` | Contact theory branch | `directional_pairwise` |

Under `directional_pairwise`, availability and command enter the prospective
initiator's deliberate hazard, existing actor-local detection belief supplies
the detection signal, and readiness is not multiplied again after detection.
`legacy_symmetric` is a compatibility/forensic branch, not the default model.

## Phase 6 organization-ecology parameters

| Parameter | Meaning | Default |
|---|---|---:|
| `interval_days` | Organizational lifecycle scheduler interval; reference-cycle probabilities/decay compose to elapsed time | 7.0 days |
| `proto_base_hazard` | Baseline mobilized-cluster incubation hazard intensity per 7-day reference cycle | 0.004 |
| `birth_base_hazard` | Baseline proto-to-armed-organization hazard intensity per 7-day reference cycle | 0.003 |
| `proto_decay_rate` | Fractional proto-capital loss per 7-day reference cycle | 0.08 |
| `split_base_hazard` | Baseline fragmentation hazard intensity per 7-day reference cycle | 0.002 |
| `merger_base_hazard` | Baseline compatible-organization merger probability scale per 7-day reference cycle | 0.015 |
| `collapse_base_hazard` | Baseline organizational collapse hazard intensity per 7-day reference cycle | 0.004 |
| `succession_base_hazard` | Baseline leadership succession probability scale per 7-day reference cycle | 0.006 |
| `adaptation_rate` | Phenotype imitation rate | 0.12 |
| `mutation_sigma` | Trait interpretation/mutation dispersion | 0.035 |
| `minimum_proto_members` | Backward-compatible raw-agent field; not used as a substantive onset threshold | 3 |
| `minimum_proto_represented_population` | Minimum represented population in an incubating cluster | 1,000 |
| `minimum_split_represented_population` | Minimum mobilized represented population eligible for organizational split | 1,500 |
| `minimum_formation_personnel` | Minimum represented strength at armed onset | 75 |
| `fighter_conversion_fraction` | Fraction of mobilized represented membership converted to fielded formation personnel | 0.08 |
| `recruitment_subcohorts` | Equal subcohorts used to bound weighted-agent recruitment and exit steps | 20 |
| `recruitment_requires_access` | Require local formation/member presence or social-network exposure for recruitment into an existing armed organization | `true` |
| `local_rootedness_weight` | Recruitment-utility coefficient on locally salient constituency/franchise congruence | 0.75 |
| `exit_sympathy_retention` | Probability a full armed exit retains franchise-linked insurgent sympathy | 1.0 |
| `onset_resource_fraction` | Member-resource contribution at organization birth | 0.18 |
| `recruitment_diversity_penalty` | Cohesion cost of heterogeneous intake | 0.12 |
| `cohesion_loss_memory` | Organizational cohesion sensitivity to military losses | 0.20 |

`observed_active_intervals` is intentionally not listed as a calibrated
hazard parameter. It is a **case input** mapping organization IDs to empirically
observed existence windows. Inside those windows the ecology suppresses split,
collapse, and merger involving that actor while leaving operations and internal
state evolution endogenous.

## Synthetic recording / measurement parameters

Recording parameters govern the researcher-visible observation layer after a
latent process event. They are empirical-estimand candidates when a real
reporting process can support calibration; they do not belong to the latent
transition equations.

| Name | Meaning | Default | Scientific role |
|---|---|---:|---|
| `recording.enabled` | Enable synthetic event recording | `true` | Structural measurement switch |
| `base_logit` | Baseline log-odds that a latent event is recorded | -1.5 | Recording-model estimand; uncalibrated |
| `severity_weight` | Recording sensitivity to latent severity | 1.8 | Recording-model estimand; uncalibrated |
| `access_weight` | Recording sensitivity to locality observability/access | 1.2 | Recording-model estimand; uncalibrated |
| `remoteness_penalty` | Recording penalty from terrain/remoteness | 0.9 | Recording-model estimand; uncalibrated |
| `severity_noise` | Multiplicative recorded-severity error width | 0.12 | Measurement prior |
| `geocoding_error_rate` | Probability a recorded event receives location error | 0.12 | Measurement prior/estimand |
| `geocoding_scale_km` | Scale of geocoding displacement | 2.0 km | Measurement prior/estimand |
| `false_event_rate` | Per-latent-event chance of an additional false recorded event | 0.0 | Measurement-model estimand |

`source_channels` can override these values by evidence/event source. All
recording draws use the deterministic `recording:<event_type>` namespace,
separate from `process:<event_type>`; changing recording settings must not
advance latent transition streams.

## Phase 7 political-order parameters

| Parameter | Meaning | Default |
|---|---|---:|
| `interval_days` | Policy and implementation cycle | 30 days |
| `election_interval_days` | Constitutional national election interval | 1,460 days |
| `federal_policy_budget` | Maximum budget allocated per political cycle | 120,000 |
| `public_budget_share` | Intended public-provision share | 0.68 |
| `patronage_share` | Intended coalition-patronage share | 0.22 |
| `private_diversion_share` | Initial private-diversion share | 0.10 |
| `capacity_learning_rate` | Slow institutional learning rate | 0.012 |
| `capacity_decay_rate` | Capacity loss under poor implementation | 0.008 |
| `patronage_capacity_damage` | Integrity/capacity damage from patronage | 0.018 |
| `elite_broker_share` | Patronage routed through aligned local elites | 0.35 |
| `peaceful_channel_strength` | Political-access displacement of armed mobilization | 0.50 |
| `election_turnout_sensitivity` | Reserved turnout calibration coefficient | 1.40 |

## Phase 8 foreign-affairs parameters

| Parameter | Meaning | Default |
|---|---|---:|
| `interval_days` | Foreign-policy and cross-border update clock | 30 days |
| `neighbor_count` | External states bordering Pineland | 5 |
| `migration_rate` / `return_rate` | Cross-border departure and return rates | 0.002 / 0.015 |
| `diaspora_remittance_rate` | External income transferred through diaspora links | 0.025 |
| `diaspora_information_rate` | Diaspora political-message rate | 0.08 |
| `support_budget_fraction` | Foreign resources considered per support cycle | 0.002 |
| `intervention_base_hazard` | Baseline direct-intervention hazard | 0.015 |
| `rival_reaction` | Strategic response to rival presence | 0.35 |
| `interpreter_effect` | Interpreter reduction of foreign epistemic disadvantage | 0.40 |
| `belief_noise` | Baseline foreign observation noise | 0.18 |
| `host_transfer_efficiency` | Default host capacity-learning coefficient | 0.35 |
| `host_crowding_out` | Default foreign substitution coefficient | 0.25 |
| `willingness_cost_weight` | Domestic willingness sensitivity to cost | 0.35 |
| `willingness_casualty_weight` | Domestic willingness sensitivity to casualties | 0.45 |
| `withdrawal_threshold` / `withdrawal_rate` | Endogenous withdrawal trigger and speed | 0.28 / 0.20 |
