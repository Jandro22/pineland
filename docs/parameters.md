# Parameter registry

All values below are uncalibrated priors exposed through the corresponding
`SimulationConfig` sections. They define transparent starting behavior, not
empirical findings.

| Name | Meaning | Units / bounds | Default | Calibration status |
|---|---|---:|---:|---|
| `target_community_size` | Preferred number of synthetic people per social community | agents, positive | 100 | Prior; compare with community-scale literature |
| `minimum_community_size` | Lower packing target when a locality contains enough agents | agents, positive | 50 | Prior |
| `maximum_community_size` | Upper household-packing target | agents, positive | 150 | Prior |
| `mean_social_degree` | Target mean regular ties before household and bridge effects | ties/person | 8.0 | Prior; benchmark against sampled degree data |
| `maximum_social_degree` | Cap used while adding ordinary community ties | ties/person | 24 | Computational prior |
| `bridge_fraction` | Share of community members considered as cross-community brokers | [0, 1] | 0.03 | Prior; sensitivity required |
| `behavior_update_rate` | Daily probability that an individual revises public behavior | [0, 1]/day | 0.12 | Prior; sensitivity required |
| `household_tie_strength` | Pre-language baseline household edge weight | [0, 1] | 0.95 | Prior |
| `community_tie_strength` | Pre-language baseline ordinary community edge weight | [0, 1] | 0.65 | Prior |
| `bridge_tie_strength` | Pre-language baseline cross-community edge weight | [0, 1] | 0.45 | Prior |
| `behavior_exposure_weight` | Contribution of normalized network exposure to public-behavior utility | nonnegative utility coefficient | 0.35 | Prior; sensitivity required |
| `recruitment_exposure_weight` | Contribution of normalized exposure to recruitment utility | nonnegative utility coefficient | 0.25 | Prior; sensitivity required |
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
| `patrol_presence_gain` | Scale converting formation presence into zone memory | [0, 1] | 0.35 | Prior |
| `fixed_post_presence_gain` | Scale converting fixed-post capacity into local presence | [0, 1] | 0.25 | Prior |
| `zone_observation_noise` | Maximum initial/noise amplitude for zone-control observations | [0, 1] | 0.12 | Prior |
| `patrol_route_randomness` | Bounded route-choice utility perturbation | [0, 1] | 0.15 | Prior |
| `intervals.physical_refresh` | Time between decay, response, and aggregation updates | days, positive | 0.25 | Numerical schedule |

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
| `resupply_trigger_fraction` | Stock fraction below which a formation requests shipment | [0, 1] | 0.45 | Policy prior |
| `resupply_target_fraction` | Requested post-delivery stock target | [0, 1] | 0.85 | Policy prior |
| `shipment_loss_per_travel_hour` | Exponential shipment attrition rate | nonnegative/hour | 0.002 | Prior |
| `convoy_speed_factor` | Supply movement speed relative to formation mobility | positive multiplier | 0.75 | Prior |
| `readiness_degradation_rate` | Readiness loss from unmet daily sustainment demand | [0, 1]/day | 0.08 | Prior |
| `readiness_recovery_near_source` | Supplied readiness recovery at a source locality | [0, 1]/day | 0.025 | Prior |
| `readiness_recovery_remote` | Supplied readiness recovery away from a source | [0, 1]/day | 0.006 | Prior |
| `availability_recovery_rate` | Supplied availability recovery | [0, 1]/day | 0.03 | Prior |
| `reallocation_rate` | Daily probability that an idle formation receives a new allocation decision | [0, 1]/day | 0.04 | Scenario prior |
| `intervals.command` | Command decision interval | days | 1.0 | Numerical schedule |
| `intervals.force_movement` | Pending/deployed movement-order update interval | days | 0.25 | Numerical schedule |
| `intervals.logistics` | Production, consumption, shipment, and recovery interval | days | 1.0 | Numerical schedule |

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
| `intervals.information` | Collection, fusion, aging, and relay-delivery interval | days | 0.25 |

`source_trust`, `source_coverage`, and `source_latency_hours` are maps keyed by
source type (`patrol`, `fixed_post`, `civilian`, `social_network`,
`administrative`, `organization_member`, `political_elite`, `interpreter`, and
`contact`). Observation weight multiplies intrinsic confidence, source quality,
trust, language comprehension, age decay, and recent corroboration.
