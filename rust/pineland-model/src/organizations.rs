//! Endogenous organization ecology over the fixed numeric organization table.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub(crate) fn local_embeddedness(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
) -> f64 {
    let threshold = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1e-12);
    let target_district = topology.locality_to_district[locality] as usize;
    let mut represented_local = 0.0;
    let mut home_local = 0.0;
    let mut home_district = 0.0;
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.locality[person] as usize != locality
            || particle.people.armed_fraction[person] <= 0.0
        {
            continue;
        }
        let represented =
            particle.people.represented_population[person] * particle.people.armed_fraction[person];
        if represented <= 0.0 {
            continue;
        }
        represented_local += represented;
        if particle.people.home[person] as usize == locality {
            home_local += represented;
        }
        if topology
            .locality_to_district
            .get(particle.people.home[person] as usize)
            .copied()
            .unwrap_or(u32::MAX) as usize
            == target_district
        {
            home_district += represented;
        }
    }
    let member_depth = (represented_local
        / config
            .organization_ecology
            .minimum_proto_represented_population
            .max(1e-12))
    .clamp(0.0, 1.0);
    let origin_depth = if represented_local > 0.0 {
        ((home_local / represented_local + home_district / represented_local) / 2.0).clamp(0.0, 1.0)
    } else {
        0.0
    };
    let member_channel = member_depth * (0.5 + 0.5 * origin_depth);

    let mut pooled = 0.0;
    let mut reserve = 0.0;
    for index in 0..particle.manpower.pool.len() {
        if particle.manpower.organization[index] as usize == organization
            && particle.manpower.locality[index] as usize == locality
        {
            pooled += particle.manpower.pool[index].max(0.0);
            reserve += particle.manpower.supply_reserve[index].max(0.0);
        }
    }
    let supply_per_fighter = (config.logistics.formation_supply_days
        * config.logistics.initial_supply_fraction)
        .max(1e-12);
    let pool_depth = (pooled.min(reserve / supply_per_fighter) / threshold).clamp(0.0, 1.0);
    let pool_channel = pool_depth
        * particle
            .organizations
            .local_knowledge
            .get(organization)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0);

    let formation_indices = (0..particle.formations.personnel.len())
        .filter(|&formation| {
            particle.formations.organization[formation] as usize == organization
                && particle.formations.locality[formation] as usize == locality
                && particle.formations.personnel[formation] > 0.0
                && particle.formations.moving[formation] == 0
                && particle.formations.outside_pineland[formation] == 0
                && particle.formations.operational_status[formation] == 1
        })
        .collect::<Vec<_>>();
    let fielded = formation_indices
        .iter()
        .map(|&formation| particle.formations.personnel[formation].max(0.0))
        .sum::<f64>();
    let formation_channel = if fielded > 0.0 {
        let weighted = formation_indices
            .iter()
            .map(|&formation| {
                particle.formations.personnel[formation].max(0.0)
                    * particle.formations.embeddedness[formation].clamp(0.0, 1.0)
            })
            .sum::<f64>();
        (fielded / threshold).clamp(0.0, 1.0) * weighted / fielded
    } else {
        0.0
    };
    let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
    let institutional_channel = if organization == crate::INSURGENT {
        ((particle.locality.insurgent_control[offset + 5]
            + particle.locality.insurgent_control[offset + 2]
            + particle.locality.insurgent_control[offset + 6])
            / 3.0)
            .clamp(0.0, 1.0)
    } else {
        0.0
    };
    let mut complement = 1.0;
    for value in [
        member_channel,
        pool_channel,
        formation_channel,
        institutional_channel,
    ] {
        complement *= 1.0 - value.clamp(0.0, 1.0);
    }
    (1.0 - complement).clamp(0.0, 1.0)
}

fn reference_cycle_probability(probability_per_cycle: f64, interval_days: f64) -> f64 {
    let probability = clamp01(probability_per_cycle);
    if probability <= 0.0 || interval_days <= 0.0 {
        0.0
    } else if probability >= 1.0 {
        1.0
    } else {
        1.0 - (1.0 - probability).powf(interval_days / 7.0)
    }
}

fn conditioned_active(config: &SimulationConfig, organization: usize, time: f64) -> bool {
    let organization_id = crate::organization_name(organization);
    config
        .organization_ecology
        .observed_active_intervals
        .get(organization_id)
        .map(|ranges| {
            ranges
                .iter()
                .any(|range| range[0] <= time && time <= range[1])
        })
        .unwrap_or(false)
}

fn survival_social_base(
    particle: &ParticleState,
    config: &SimulationConfig,
    organization: usize,
) -> f64 {
    let scale = config
        .organization_ecology
        .minimum_proto_represented_population
        .max(1e-9);
    let mut total = 0.0;
    let mut by_locality = std::collections::BTreeMap::<u32, f64>::new();
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.armed_fraction[person] <= 0.0
        {
            continue;
        }
        let represented =
            particle.people.represented_population[person] * particle.people.armed_fraction[person];
        total += represented;
        *by_locality
            .entry(particle.people.residence[person])
            .or_default() += represented;
    }
    let saturating = |quantity: f64| {
        if quantity > 0.0 {
            quantity / (quantity + scale)
        } else {
            0.0
        }
    };
    let represented_base = saturating(total);
    let local_depth = by_locality
        .values()
        .copied()
        .map(saturating)
        .fold(0.0, f64::max);
    clamp01(
        0.50 * represented_base
            + 0.25 * local_depth
            + 0.125 * particle.organizations.capital_social[organization]
            + 0.125 * particle.organizations.phenotype[organization * 8 + 6],
    )
}

fn adapt_organization(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    organization: usize,
    elapsed_days: f64,
) {
    // The Python ecology always applies the innovation draw, even when no
    // observable peer exists.  The single initial insurgent therefore still
    // consumes eight normalvariate calls around its own phenotype.
    let reference_learning = clamp01(
        particle.organizations.adaptation_rate[organization]
            * (0.4 + 0.6 * particle.organizations.institutional_quality[organization]),
    );
    let learning = reference_cycle_probability(reference_learning, elapsed_days);
    let perceived_sigma = if learning > 0.0 && reference_learning > 0.0 {
        let phi_reference = 1.0 - reference_learning;
        let phi_interval = 1.0 - learning;
        let reference_state_variance =
            (reference_learning * config.organization_ecology.mutation_sigma).powi(2);
        let denominator = (1.0 - phi_reference.powi(2)).max(1e-15);
        let interval_state_variance =
            reference_state_variance * (1.0 - phi_interval.powi(2)) / denominator;
        interval_state_variance.max(0.0).sqrt() / learning
    } else {
        0.0
    };
    let offset = organization * 8;
    for dimension in 0..8 {
        let value = particle.organizations.phenotype[offset + dimension];
        let perceived = value + rng.normalvariate(0.0, perceived_sigma);
        particle.organizations.phenotype[offset + dimension] =
            clamp01(value + learning * (perceived - value));
    }
    particle.organizations.discipline[organization] = particle.organizations.phenotype[offset + 5];
    particle.organizations.local_knowledge[organization] =
        particle.organizations.phenotype[offset + 6];
}

/// Advance the proto-formation clock before updating extant armed
/// organizations.  Native v1 does not yet materialize the Python proto
/// object graph, but the eligibility scan and its Bernoulli draw are part of
/// the process RNG contract.  Keeping this boundary explicit prevents a
/// latent proto attempt from shifting every subsequent ecology draw.
fn consume_proto_formation_draws(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    elapsed_days: f64,
) {
    let reference_days = 7.0;
    for community in 0..particle.communities.locality.len() {
        let start = particle.communities.member_offsets[community] as usize;
        let end = particle.communities.member_offsets[community + 1] as usize;
        let members = &particle.communities.member_indices[start..end];
        if members.is_empty() {
            continue;
        }
        let represented = python_sum(
            &members
                .iter()
                .map(|person| particle.people.represented_population[*person as usize])
                .collect::<Vec<_>>(),
        );
        let mobilized = members
            .iter()
            .copied()
            .map(|person| person as usize)
            .filter(|person| {
                particle.people.organization[*person] == u32::MAX
                    && (matches!(particle.people.public_behavior[*person], 1 | 2 | 6)
                        || particle.people.grievance[*person] > 0.55)
            })
            .collect::<Vec<_>>();
        let mobilized_weight = python_sum(
            &mobilized
                .iter()
                .map(|person| particle.people.represented_population[*person])
                .collect::<Vec<_>>(),
        );
        if mobilized_weight
            < config
                .organization_ecology
                .minimum_proto_represented_population
        {
            continue;
        }
        let grievance = python_sum(
            &members
                .iter()
                .map(|person| {
                    let person = *person as usize;
                    particle.people.represented_population[person]
                        * particle.people.grievance[person]
                })
                .collect::<Vec<_>>(),
        ) / represented.max(1.0e-9);
        let bridge_fraction = config.social_network.bridge_fraction.clamp(0.0, 1.0);
        let bridge_weight = represented * bridge_fraction;
        let reach = (bridge_weight / represented.max(1.0) * 5.0).min(1.0);
        let access = python_sum(
            &members
                .iter()
                .map(|person| {
                    let person = *person as usize;
                    particle.people.represented_population[person]
                        * particle.people.political_access[person]
                })
                .collect::<Vec<_>>(),
        ) / represented.max(1.0e-9);
        let score = clamp01(
            0.3 * grievance
                + 0.3 * particle.communities.cohesion[community]
                + 0.2 * particle.communities.insurgent_sympathy[community]
                + 0.2 * reach
                - config.political_order.peaceful_channel_strength * 0.25 * access,
        );
        let expected_repression = clamp01(
            python_sum(
                &mobilized
                    .iter()
                    .map(|person| {
                        let person = *person as usize;
                        particle.people.represented_population[person]
                            * (1.0 - particle.people.expected_control[person * 2])
                    })
                    .collect::<Vec<_>>(),
            ) / mobilized_weight.max(1.0e-9),
        );
        let hazard = 1.0
            - python_exp(
                -config.organization_ecology.proto_base_hazard
                    * python_exp(2.2 * score - 1.4 * expected_repression)
                    * elapsed_days
                    / reference_days,
            );
        // ``form_proto_organizations`` draws once for every eligible
        // community, including a failed founding attempt.
        let _ = (topology, rng.random() < hazard);
    }
}

/// Renew/decay the persistent locality foothold stock at the same event
/// boundaries as Python's `advance_local_footholds`.  This transition is
/// deterministic and must not consume an ecology/process RNG draw.
pub fn advance_footholds(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    if !config.organization_ecology.enabled {
        return;
    }
    let threshold = config
        .organization_ecology
        .local_foothold_viability_threshold
        .clamp(0.0, 1.0);
    let base_memory = config
        .organization_ecology
        .local_foothold_memory_days
        .max(1e-9);
    let locality_count = topology.locality_count();
    for organization in 0..particle.organizations.kind.len() {
        for locality in 0..locality_count {
            let index = organization * locality_count + locality;
            if index >= particle.footholds.strength.len() {
                continue;
            }
            if particle.footholds.active[index] == 0 {
                continue;
            }
            let elapsed = (time - particle.footholds.updated_at[index]).max(0.0);
            let memory_days = base_memory
                * (0.5
                    + particle
                        .organizations
                        .persistence
                        .get(organization)
                        .copied()
                        .unwrap_or(0.0)
                        .clamp(0.0, 1.0));
            let retention = python_exp(-elapsed / memory_days.max(1e-9));
            let previous = particle.footholds.strength[index].clamp(0.0, 1.0);
            let raw = local_embeddedness(particle, topology, config, organization, locality);
            if raw > 1e-12 {
                particle.footholds.renewal_count[index] =
                    particle.footholds.renewal_count[index].saturating_add(1);
            }
            if previous >= threshold {
                particle.footholds.cumulative_active_days[index] += elapsed;
            }
            let updated = (previous * retention).max(raw).clamp(0.0, 1.0);
            if previous < threshold && updated >= threshold {
                particle.footholds.viable_activation_count[index] =
                    particle.footholds.viable_activation_count[index].saturating_add(1);
                if particle.footholds.first_activated_at[index] < -1.0e8 {
                    particle.footholds.first_activated_at[index] = time;
                }
                particle.footholds.last_activated_at[index] = time;
            } else if updated >= threshold {
                particle.footholds.last_activated_at[index] = time;
            }
            particle.footholds.strength[index] = updated;
            particle.footholds.raw_signal[index] = raw;
            // The legacy native component named `embeddedness` is the
            // Python foothold strength projection used by the certificate.
            particle.footholds.embeddedness[index] = updated;
            particle.footholds.updated_at[index] = time;
        }
    }
}

/// Record a realized violent organized action as local organizational
/// renewal.  Python applies this after the action handler, before the second
/// same-boundary foothold advance; keeping the small mutation explicit lets
/// callers preserve that ordering without adding a stochastic draw.
pub(crate) fn record_foothold_action(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
) {
    if organization >= particle.organizations.kind.len() || locality >= topology.locality_count() {
        return;
    }
    let index = organization * topology.locality_count() + locality;
    if index >= particle.footholds.cumulative_actions.len() {
        return;
    }
    particle.footholds.active[index] = 1;
    particle.footholds.cumulative_actions[index] += 1.0;
    particle.footholds.renewal_count[index] =
        particle.footholds.renewal_count[index].saturating_add(1);
}

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    // The Python process engine treats the initialization-time ecology event
    // as a true no-op.  In particular, it must not consume the ecology RNG
    // stream or mutate organization/foothold state before a positive ecology
    // interval has elapsed.
    if !config.organization_ecology.enabled || elapsed_days <= 0.0 {
        return;
    }
    consume_proto_formation_draws(particle, topology, config, rng, elapsed_days);
    let organizations = (0..particle.organizations.active.len())
        .filter(|&organization| {
            particle.organizations.active[organization] != 0
                && particle.organizations.kind[organization] == 3
        })
        .collect::<Vec<_>>();
    for organization in organizations {
        let formation_values = (0..particle.formations.personnel.len())
            .filter(|&formation| {
                particle.formations.organization[formation] as usize == organization
            })
            .map(|formation| particle.formations.personnel[formation])
            .collect::<Vec<_>>();
        let loss_values = (0..particle.formations.personnel.len())
            .filter(|&formation| {
                particle.formations.organization[formation] as usize == organization
            })
            .map(|formation| particle.formations.cumulative_losses[formation])
            .collect::<Vec<_>>();
        let personnel_plus_losses = (0..particle.formations.personnel.len())
            .filter(|&formation| {
                particle.formations.organization[formation] as usize == organization
            })
            .map(|formation| {
                particle.formations.personnel[formation]
                    + particle.formations.cumulative_losses[formation]
            })
            .collect::<Vec<_>>();
        let losses = python_sum(&loss_values) / python_sum(&personnel_plus_losses).max(1.0);

        let mut represented_weight = 0.0;
        let mut identity_weighted = 0.0;
        for person in 0..particle.people.locality.len() {
            if particle.people.organization[person] as usize != organization
                || particle.people.armed_fraction[person] <= 0.0
            {
                continue;
            }
            let represented = particle.people.represented_population[person]
                * particle.people.armed_fraction[person];
            represented_weight += represented;
            identity_weighted += represented * particle.people.identities[person * 3 + 2];
        }
        let mean_identity = identity_weighted / represented_weight.max(1e-9);
        let mut identity_variance = 0.0;
        for person in 0..particle.people.locality.len() {
            if particle.people.organization[person] as usize != organization
                || particle.people.armed_fraction[person] <= 0.0
            {
                continue;
            }
            let represented = particle.people.represented_population[person]
                * particle.people.armed_fraction[person];
            identity_variance +=
                represented * (particle.people.identities[person * 3 + 2] - mean_identity).powi(2);
        }
        identity_variance /= represented_weight.max(1e-9);
        let cycle_scale = elapsed_days / 7.0;
        particle.organizations.cohesion[organization] = clamp01(
            particle.organizations.cohesion[organization]
                + cycle_scale
                    * (0.025 * particle.organizations.capital_social[organization]
                        - config.organization_ecology.cohesion_loss_memory * losses
                        - 0.02 * identity_variance),
        );
        particle.organizations.capital_material[organization] =
            clamp01(particle.organizations.capital[organization] / 150_000.0);

        adapt_organization(particle, config, rng, organization, elapsed_days);
        let phenotype = organization * 8;
        for formation in 0..particle.formations.personnel.len() {
            if particle.formations.organization[formation] as usize != organization {
                continue;
            }
            particle.formations.embeddedness[formation] =
                particle.organizations.phenotype[phenotype + 6];
            particle.formations.mobility[formation] =
                clamp01(0.35 + 0.5 * particle.organizations.phenotype[phenotype + 3]);
            for edge in 0..particle.command_edges.organization.len() {
                if particle.command_edges.organization[edge] as usize == organization
                    && particle.command_edges.formation[edge] as usize == formation
                {
                    let centralization =
                        particle.organizations.phenotype[phenotype].clamp(0.0, 1.0);
                    particle.command_edges.reliability[edge] = clamp01(
                        0.3 + 0.35 * centralization
                            + 0.25 * particle.organizations.institutional_quality[organization],
                    );
                    particle.command_edges.latency_hours[edge] =
                        10.0 * (1.0 - centralization) + 1.0;
                }
            }
        }

        let succession_probability = reference_cycle_probability(
            config.organization_ecology.succession_base_hazard
                * (1.4 - particle.organizations.cohesion[organization]),
            elapsed_days,
        );
        if rng.random() < succession_probability {
            particle.organizations.succession_count[organization] =
                particle.organizations.succession_count[organization].saturating_add(1);
        }

        let split_hazard = 1.0
            - python_exp(
                -config.organization_ecology.split_base_hazard
                    * python_exp(
                        2.0 * identity_variance + 3.0 * losses
                            - 2.0 * particle.organizations.cohesion[organization],
                    )
                    * elapsed_days
                    / 7.0,
            );
        let split_eligible = represented_weight
            >= config
                .organization_ecology
                .minimum_split_represented_population;
        let split_draw = if split_eligible {
            Some(rng.random())
        } else {
            None
        };
        let conditioned = conditioned_active(config, organization, time);
        let _split_realized = split_draw
            .map(|draw| draw < split_hazard && !conditioned)
            .unwrap_or(false);

        let social_base = survival_social_base(particle, config, organization);
        let collapse_hazard = 1.0
            - python_exp(
                -config.organization_ecology.collapse_base_hazard
                    * python_exp(
                        2.0 * (1.0 - particle.organizations.cohesion[organization]) + 2.0 * losses
                            - 3.0 * social_base
                            - 1.5 * particle.organizations.external_sanctuary[organization],
                    )
                    * elapsed_days
                    / 7.0,
            );
        let collapse_draw = rng.random();
        let _collapse_realized = !conditioned
            && (particle.organizations.capital[organization] <= 0.0
                || particle.organizations.cohesion[organization] < 0.12
                || represented_weight <= 1e-9
                || collapse_draw < collapse_hazard);
        let _ = (formation_values, _split_realized, _collapse_realized);
    }
}

pub fn onset_hazard(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    locality: usize,
) -> f64 {
    if locality >= topology.locality_count() {
        return 0.0;
    }
    let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
    config.organization_ecology.birth_base_hazard
        * (1.0 - particle.locality.government_control[offset + 5])
        * (1.0 + particle.locality.violence[locality])
}
