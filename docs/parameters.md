# Parameter registry: Phase 1 social structure

All values below are uncalibrated priors exposed through `SimulationConfig.social_network`. They define transparent starting behavior, not empirical findings.

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
