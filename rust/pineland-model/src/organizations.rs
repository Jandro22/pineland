//! Endogenous organization ecology over the fixed numeric organization table.

use pineland_core::config::SimulationConfig;
use pineland_core::ids::LocalityId;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

/// Current local organizational renewal potential before foothold memory is
/// applied.  This is public for theory diagnostics/coarse-graining assays;
/// callers must treat it as a pure read of the production transition, not as
/// a second implementation of the mechanism.
pub fn local_embeddedness(
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
    let personnel_values = formation_indices
        .iter()
        .map(|&formation| particle.formations.personnel[formation].max(0.0))
        .collect::<Vec<_>>();
    let fielded = python_sum(&personnel_values);
    let formation_channel = if fielded > 0.0 {
        let weighted_values = formation_indices
            .iter()
            .map(|&formation| {
                particle.formations.personnel[formation].max(0.0)
                    * particle.formations.embeddedness[formation].clamp(0.0, 1.0)
            })
            .collect::<Vec<_>>();
        let weighted = python_sum(&weighted_values);
        let mean_embeddedness = weighted / fielded;
        (fielded / threshold).clamp(0.0, 1.0) * mean_embeddedness
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
    } else if organization >= 7 && organization < particle.organizations.kind.len() {
        let organization_count = particle.organizations.kind.len();
        let organization_offset = pineland_core::state::LocalityState::organization_control_offset(
            locality,
            organization,
            organization_count,
        );
        ((particle.locality.organization_control[organization_offset + 5]
            + particle.locality.organization_control[organization_offset + 2]
            + particle.locality.organization_control[organization_offset + 6])
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

/// Return the persistent local organizational stock used by Python's
/// action-choice contract.  A foothold is available to decision rules only
/// after at least one renewal boundary; the initial embeddedness projection
/// alone is not a post-movement memory stock.
pub(crate) fn local_foothold_strength(
    particle: &ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
) -> f64 {
    if organization != crate::INSURGENT || locality >= topology.locality_count() {
        return 0.0;
    }
    let index = organization * topology.locality_count() + locality;
    if particle
        .footholds
        .renewal_count
        .get(index)
        .copied()
        .unwrap_or(0)
        == 0
    {
        return 0.0;
    }
    particle
        .footholds
        .strength
        .get(index)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0)
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

fn conditioned_active(
    particle: &ParticleState,
    config: &SimulationConfig,
    organization: usize,
    time: f64,
) -> bool {
    let organization_id = crate::organization_name_for_particle(particle, organization);
    config
        .organization_ecology
        .observed_active_intervals
        .get(&organization_id)
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
    let trace = crate::trace_env!("PINELAND_ORG_TRACE");
    if trace {
        eprintln!(
            "ORG_ADAPT_START org={} elapsed={:.17} sigma={:.17} rng_index={} phenotype={:?}",
            organization,
            elapsed_days,
            perceived_sigma,
            rng.state().index,
            &particle.organizations.phenotype[offset..offset + 8]
        );
    }
    for dimension in 0..8 {
        let value = particle.organizations.phenotype[offset + dimension];
        let perceived = value + rng.normalvariate(0.0, perceived_sigma);
        particle.organizations.phenotype[offset + dimension] =
            clamp01(value + learning * (perceived - value));
        if trace {
            eprintln!(
                "ORG_ADAPT_DRAW org={} dim={} value={:.17} perceived={:.17} output={:.17} rng_index={}",
                organization,
                dimension,
                value,
                perceived,
                particle.organizations.phenotype[offset + dimension],
                rng.state().index
            );
        }
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
    particle: &mut ParticleState,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    elapsed_days: f64,
) {
    let reference_days = 7.0;
    let trace = crate::trace_env!("PINELAND_ORG_TRACE");
    for community in 0..particle.communities.locality.len() {
        if particle
            .protos
            .community
            .iter()
            .zip(&particle.protos.status)
            .any(|(candidate, status)| *candidate as usize == community && *status == 1)
        {
            continue;
        }
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
        let draw = rng.random();
        if trace {
            eprintln!(
                "ORG_PROTO community={} members={} mobilized={} represented={:.17} mobilized_weight={:.17} score={:.17} expected_repression={:.17} hazard={:.17} draw={:.17} rng_index={}",
                community,
                members.len(),
                mobilized.len(),
                represented,
                mobilized_weight,
                score,
                expected_repression,
                hazard,
                draw,
                rng.state().index
            );
        }
        if draw < hazard {
            let target_weight = config
                .organization_ecology
                .minimum_proto_represented_population
                .max(mobilized_weight * 0.5);
            let founder_fraction = clamp01(target_weight / mobilized_weight.max(1.0e-9));
            let selected_weight = python_sum(
                &mobilized
                    .iter()
                    .map(|person| {
                        particle.people.represented_population[*person] * founder_fraction
                    })
                    .collect::<Vec<_>>(),
            );
            let material_intensity = python_sum(
                &mobilized
                    .iter()
                    .map(|person| particle.people.resources[*person] * founder_fraction)
                    .collect::<Vec<_>>(),
            ) / selected_weight.max(1.0e-9);
            let leadership = python_sum(
                &mobilized
                    .iter()
                    .map(|person| {
                        particle.people.represented_population[*person]
                            * founder_fraction
                            * particle.people.efficacy[*person]
                    })
                    .collect::<Vec<_>>(),
            ) / selected_weight.max(1.0e-9);
            let members = mobilized
                .iter()
                .map(|person| *person as u32)
                .collect::<Vec<_>>();
            particle.protos.push(
                community as u32,
                particle.communities.locality[community],
                &members,
                [
                    particle.communities.cohesion[community],
                    score,
                    clamp01(0.12 + 0.25 * particle.communities.cohesion[community]),
                    clamp01(material_intensity / 3.0),
                ],
                selected_weight,
                [clamp01(0.4 + score / 2.0), clamp01(0.15 + 0.3 * score)],
                clamp01(leadership),
                0.0,
            );
        }
    }
}

fn reference_cycle_survival_factor(loss_per_cycle: f64, elapsed_days: f64) -> f64 {
    (1.0 - clamp01(loss_per_cycle)).powf(elapsed_days / 7.0)
}

fn dynamic_organization_number(particle: &ParticleState) -> usize {
    particle.organizations.kind[crate::INSURGENT + 1..]
        .iter()
        .filter(|kind| **kind == 3)
        .count()
        + 1
}

fn materialize_proto_birth(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    proto: usize,
    members: &[u32],
    founder_scale: f64,
    personnel: f64,
    time: f64,
) {
    let old_organizations = particle.organizations.kind.len();
    let organization = old_organizations;
    let dynamic_number = dynamic_organization_number(particle);
    let old_command_ids = crate::information::command_node_ids(particle);
    let new_command_id = format!("CMD:armed-{dynamic_number:03}");
    let command_insert_position = old_command_ids
        .binary_search(&new_command_id)
        .unwrap_or_else(|position| position);

    // Python's mature_proto converts the founder slice's resources before it
    // creates any of the new registry rows. Preserve that per-person update
    // order so resource and floating-point continuation state agree.
    let mut contributed = 0.0;
    for person in members.iter().map(|person| *person as usize) {
        let contribution = particle.people.resources[person]
            * config.organization_ecology.onset_resource_fraction
            * founder_scale;
        contributed += contribution;
        particle.people.resources[person] -= contribution;
        let household = particle.people.household[person] as usize;
        if household < particle.households.resources.len() {
            particle.households.resources[household] -= contribution;
            if particle.households.resources[household].abs() <= 1e-9 {
                particle.households.resources[household] = 0.0;
            }
        }
    }

    // Adding an organization inserts a new numeric slot before the dynamic
    // formation/post/command ranges. Existing observers therefore need the
    // same canonical reindexing that Python obtains by rebuilding node IDs.
    crate::recruitment::shift_dynamic_observer_codes_after_organization(
        particle,
        old_organizations,
    );
    particle
        .locality
        .ensure_organization_capacity(organization + 1);
    particle
        .people
        .ensure_organization_capacity(organization + 1);

    let organizational_capital = particle.protos.capital_organizational[proto];
    let social_capital = particle.protos.capital_social[proto];
    let political_capital = particle.protos.capital_political[proto];
    let material_capital = particle.protos.capital_material[proto];
    let cohesion = clamp01(0.35 + 0.4 * organizational_capital);

    particle.organizations.kind.push(3);
    particle.organizations.active.push(1);
    particle.organizations.capital.push(contributed);
    particle.organizations.cohesion.push(cohesion);
    particle.organizations.discipline.push(0.5);
    particle.organizations.accountability.push(0.2);
    particle.organizations.local_knowledge.push(social_capital);
    particle.organizations.persistence.push(0.65);
    particle.organizations.mobility.push(0.55);
    particle.organizations.institutional_quality.push(0.45);
    particle.organizations.external_support.push(0.0);
    particle.organizations.member_population.push(python_sum(
        &members
            .iter()
            .map(|person| {
                particle.people.represented_population[*person as usize] * founder_scale
            })
            .collect::<Vec<_>>(),
    ));
    particle.organizations.founded_at.push(time);
    particle.organizations.succession_count.push(0);
    particle.organizations.capital_social.push(social_capital);
    particle.organizations.capital_political.push(political_capital);
    particle
        .organizations
        .capital_organizational
        .push(organizational_capital);
    particle.organizations.capital_material.push(material_capital);

    // The phenotype dictionary insertion order is part of the Python RNG
    // contract, so keep these four draws ahead of leader construction.
    let centralization = rng.uniform(0.3, 0.7);
    let governance_investment = rng.uniform(0.2, 0.6);
    let dispersion = rng.uniform(0.4, 0.8);
    let risk_tolerance = rng.uniform(0.3, 0.75);
    particle.organizations.phenotype.extend_from_slice(&[
        centralization,
        political_capital,
        governance_investment,
        dispersion,
        risk_tolerance,
        0.5,
        social_capital,
        0.1,
    ]);
    particle
        .organizations
        .ideology
        .extend_from_slice(&[
            particle.protos.ideology_reform[proto],
            particle.protos.ideology_separatism[proto],
        ]);
    particle.organizations.external_sanctuary.push(0.0);
    particle
        .organizations
        .adaptation_rate
        .push(config.organization_ecology.adaptation_rate);

    // This is the native equivalent of _set_armed_membership: an armed
    // founder exposes only the newly created franchise affinity.
    for person in members.iter().map(|person| *person as usize) {
        let row = &mut particle.people.insurgent_affinity
            [person * (organization + 1)..(person + 1) * (organization + 1)];
        row.fill(0.0);
        row[organization] = founder_scale.max(1.0e-12);
        particle.people.organization[person] = organization as u32;
        particle.people.armed_fraction[person] = founder_scale;
        particle.people.rebel_sympathy[person] = founder_scale;
        particle.people.public_behavior[person] = if founder_scale >= 0.5 { 2 } else { 1 };
    }

    // Python creates the new local control row with this explicit default,
    // while the aggregate insurgent row remains independently maintained.
    for locality in 0..topology.locality_count() {
        let offset = pineland_core::state::LocalityState::organization_control_offset(
            locality,
            organization,
            organization + 1,
        );
        particle.locality.organization_control[offset..offset + CONTROL_DIMENSIONS]
            .copy_from_slice(&[0.0, 0.005, 0.0, 0.005, 0.005, 0.015, 0.03]);
    }
    for other in 0..organization {
        let (status, hostility, cooperation) = if matches!(
            particle.organizations.kind[other],
            0 | 1 | 2
        ) {
            (4, 1.0, 0.0)
        } else {
            (2, 0.0, 0.0)
        };
        crate::foreign::append_relation(
            particle,
            organization,
            other,
            status,
            hostility,
            cooperation,
            time,
        );
    }

    // The Python registry materializes one foothold key per organization and
    // locality at the end of the ecology event. The post-event foothold pass
    // will fill its raw/strength projection; active=1 represents key
    // existence, not current operational activity.
    crate::foreign::append_foothold_rows(particle, topology.locality_count(), organization);
    let foothold_start = organization * topology.locality_count();
    for index in foothold_start..foothold_start + topology.locality_count() {
        particle.footholds.active[index] = 1;
        particle.footholds.updated_at[index] = time;
    }

    // _create_leader consumes six uniforms followed by six normalvariate
    // calls, after the four phenotype uniforms above.
    let leader = particle.leaders.organization.len();
    let mut base = [0.0; 6];
    for value in &mut base {
        *value = rng.uniform(0.3, 0.8);
    }
    let values = (0..6)
        .map(|index| clamp01(base[index] + rng.normalvariate(0.0, 0.04)))
        .collect::<Vec<_>>();
    particle.leaders.organization.push(organization as u32);
    particle.leaders.competence.push(values[0]);
    particle.leaders.charisma.push(values[1]);
    particle.leaders.risk_tolerance.push(values[2]);
    particle.leaders.ideological_rigidity.push(values[3]);
    particle.leaders.political_skill.push(values[4]);
    particle.leaders.organizational_skill.push(values[5]);
    particle.leaders.active.push(1);
    particle.organizations.leader.push(leader as u32);

    let old_formations = particle.formations.personnel.len();
    crate::recruitment::shift_dynamic_observer_codes(particle, old_formations);
    let command_start = particle.organizations.kind.len()
        + old_formations
        + 1
        + particle.security_posts.organization.len()
        + crate::information::auxiliary_node_count(particle, topology);
    crate::recruitment::shift_dynamic_observer_codes_after_command_insertion(
        particle,
        command_start as u32,
        old_command_ids.len(),
        command_insert_position,
    );
    let locality = particle.protos.locality[proto] as usize;
    let formation = old_formations;
    let zone = topology
        .zones_for_locality(LocalityId(locality as u32))
        .max_by(|left, right| {
            topology.zone_population_share[*left]
                .total_cmp(&topology.zone_population_share[*right])
                .then_with(|| right.cmp(left))
        })
        .unwrap_or(topology.locality_post_zone[locality] as usize);
    let capacity = personnel * config.logistics.formation_supply_days;
    let stock = (capacity * 0.25).min(contributed).max(0.0);
    particle.organizations.capital[organization] -= stock;

    particle.formations.organization.push(organization as u32);
    particle.formations.locality.push(locality as u32);
    particle.formations.microzone.push(zone as u32);
    particle.formations.personnel.push(personnel);
    particle.formations.quality.push(0.35);
    particle.formations.experience.push(0.12);
    particle.formations.cohesion.push(cohesion);
    particle.formations.readiness.push(0.55);
    particle.formations.sustainment.push(if capacity > 0.0 {
        stock / capacity
    } else {
        0.0
    });
    particle.formations.information.push(0.45);
    particle.formations.mobility.push(0.55);
    particle.formations.command.push(0.45);
    particle.formations.embeddedness.push(social_capital);
    particle.formations.fatigue.push(0.0);
    particle.formations.availability.push(0.65);
    particle.formations.supply_stock.push(stock);
    particle.formations.supply_capacity.push(capacity);
    particle.formations.home_locality.push(u32::MAX);
    particle.formations.active.push(1);
    particle.formations.moving.push(0);
    particle.formations.operational_status.push(1);
    particle.formations.cumulative_losses.push(0.0);
    particle.formations.outside_pineland.push(0);
    particle.formations.operational_posture.push(0);
    particle.formations.movement_destination.push(u32::MAX);
    particle.formations.movement_origin.push(u32::MAX);
    particle.formations.movement_execute_at.push(0.0);
    particle.formations.movement_arrives_at.push(-1.0);
    particle.formations.movement_travel_hours.push(0.0);
    particle.formations.movement_distance_km.push(0.0);
    particle.formations.movement_supply_cost.push(0.0);
    particle.formations.movement_order_sequence.push(0);
    particle.formations.movement_status.push(0);
    particle.formations.movement_purpose.push(0);
    particle.formations.external_state.push(u32::MAX);

    // Formation registries are rectangular in native state; this inactive
    // patrol slot is the compact equivalent of Python's no-patrol birth.
    particle.patrols.formation.push(formation as u32);
    particle.patrols.active.push(0);
    particle.patrols.route_position.push(0);
    particle.patrols.route_target.push(0);
    particle.patrols.last_departure.push(-1.0e9);
    particle.patrols.next_available.push(0.0);
    particle.patrols.response_fraction.push(0.3);
    particle.patrols.presence_accounted_at.push(-1.0e300);
    particle.patrols.detections.push(0);

    particle.command_edges.organization.push(organization as u32);
    particle.command_edges.formation.push(formation as u32);
    particle.command_edges.reliability.push(0.45);
    particle.command_edges.latency_hours.push(8.0);

    particle.protos.status[proto] = 2;

    if crate::trace_env!("PINELAND_ORG_TRACE") {
        eprintln!(
            "ORG_BIRTH organization=armed-{dynamic_number:03} proto={} locality={} personnel={:.17} contributed={:.17} stock={:.17} rng_index={}",
            proto,
            locality,
            personnel,
            contributed,
            stock,
            rng.state().index,
        );
    }
}

/// Advance every mobilizing proto after new proto rows have been formed.
fn advance_protos(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    elapsed_days: f64,
    time: f64,
) {
    for proto in 0..particle.protos.count() {
        if particle.protos.status[proto] != 1 {
            continue;
        }
        let members = particle.protos.members(proto).to_vec();
        let total_weight = python_sum(
            &members
                .iter()
                .map(|person| particle.people.represented_population[*person as usize])
                .collect::<Vec<_>>(),
        );
        let founder_scale =
            clamp01(particle.protos.represented_membership[proto] / total_weight.max(1.0e-9));
        let expected_repression = python_sum(
            &members
                .iter()
                .map(|person| {
                    let person = *person as usize;
                    particle.people.represented_population[person]
                        * founder_scale
                        * (1.0 - particle.people.expected_control[person * 2])
                })
                .collect::<Vec<_>>(),
        ) / (total_weight * founder_scale).max(1.0e-9);
        let capital = python_sum(&[
            particle.protos.capital_social[proto],
            particle.protos.capital_political[proto],
            particle.protos.capital_organizational[proto],
            particle.protos.capital_material[proto],
        ]) / 4.0;
        let hazard = 1.0
            - python_exp(
                -config.organization_ecology.birth_base_hazard
                    * python_exp(
                        2.4 * capital + particle.protos.leadership_potential[proto]
                            - 1.6 * expected_repression,
                    )
                    * elapsed_days
                    / 7.0,
            );
        let draw = rng.random();
        if draw >= hazard {
            let survival = reference_cycle_survival_factor(
                config.organization_ecology.proto_decay_rate,
                elapsed_days,
            );
            particle.protos.capital_social[proto] =
                clamp01(particle.protos.capital_social[proto] * survival);
            particle.protos.capital_political[proto] =
                clamp01(particle.protos.capital_political[proto] * survival);
            particle.protos.capital_organizational[proto] =
                clamp01(particle.protos.capital_organizational[proto] * survival);
            particle.protos.capital_material[proto] =
                clamp01(particle.protos.capital_material[proto] * survival);
            let mean = python_sum(&[
                particle.protos.capital_social[proto],
                particle.protos.capital_political[proto],
                particle.protos.capital_organizational[proto],
                particle.protos.capital_material[proto],
            ]) / 4.0;
            if mean < 0.08 {
                particle.protos.status[proto] = 3;
            }
        } else {
            let personnel = (total_weight * founder_scale)
                * config.organization_ecology.fighter_conversion_fraction;
            if personnel < config.organization_ecology.minimum_formation_personnel {
                particle.protos.status[proto] = 3;
            } else {
                materialize_proto_birth(
                    particle,
                    topology,
                    config,
                    rng,
                    proto,
                    &members,
                    founder_scale,
                    personnel,
                    time,
                );
            }
        }
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

/// Record the organizational renewal caused by a formation physically
/// arriving in a locality.  Python applies this mutation immediately after
/// movement and before the second same-boundary foothold advance.
pub(crate) fn record_foothold_arrival(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
) {
    if formation >= particle.formations.personnel.len()
        || particle.formations.organization[formation] as usize != crate::INSURGENT
    {
        return;
    }
    let locality = particle.formations.locality[formation] as usize;
    if locality >= topology.locality_count() {
        return;
    }
    let index = crate::INSURGENT * topology.locality_count() + locality;
    if index >= particle.footholds.strength.len() {
        return;
    }
    particle.footholds.active[index] = 1;
    particle.footholds.cumulative_arrivals[index] += 1.0;
    particle.footholds.renewal_count[index] =
        particle.footholds.renewal_count[index].saturating_add(1);
    let minimum = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1.0e-9);
    let arrival_signal = (particle.formations.personnel[formation].max(0.0) / minimum)
        .clamp(0.0, 1.0)
        * particle.formations.embeddedness[formation].clamp(0.0, 1.0);
    particle.footholds.strength[index] = particle.footholds.strength[index]
        .max(arrival_signal)
        .clamp(0.0, 1.0);
    particle.footholds.embeddedness[index] = particle.footholds.strength[index];
    particle.footholds.raw_signal[index] = particle.footholds.raw_signal[index].max(arrival_signal);
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
    particle.footholds.embeddedness[index] = particle.footholds.strength[index];
}

/// Collapse an insurgent organization at the same boundary as Python's
/// ``collapse_organization``.  The native state uses an active bit and fixed
/// numeric organization table where Python uses a status string and mutable
/// object registries.  Keeping the historical row/formation slots in place
/// preserves canonical indices while clearing the live membership, pooled
/// manpower, and operational capacity that can affect later decisions.
fn collapse_organization(particle: &mut ParticleState, organization: usize) {
    let organization_count = particle.organizations.kind.len();
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization {
            continue;
        }
        let prior_fraction = particle.people.armed_fraction[person];
        particle.people.organization[person] = u32::MAX;
        particle.people.armed_fraction[person] = 0.0;
        // Python retains the former franchise as latent affinity on exit.
        if prior_fraction > 0.0 && organization < organization_count {
            particle.people.rebel_sympathy[person] =
                particle.people.rebel_sympathy[person].max(prior_fraction);
            let offset = person * organization_count + organization;
            if offset < particle.people.insurgent_affinity.len() {
                particle.people.insurgent_affinity[offset] =
                    particle.people.insurgent_affinity[offset].max(prior_fraction);
            }
        }
        if particle.people.public_behavior[person] == 2 {
            particle.people.public_behavior[person] = 1;
        }
    }
    particle.organizations.active[organization] = 0;
    particle.organizations.member_population[organization] = 0.0;

    // Python removes both the unfielded manpower and its paired material
    // reserve when a franchise collapses.  Remove rows backwards so the
    // remaining fixed-width parallel vectors stay aligned.
    for index in (0..particle.manpower.pool.len()).rev() {
        if particle.manpower.organization[index] as usize != organization {
            continue;
        }
        particle.manpower.organization.remove(index);
        particle.manpower.locality.remove(index);
        particle.manpower.pool.remove(index);
        particle.manpower.supply_reserve.remove(index);
    }

    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.organization[formation] as usize != organization {
            continue;
        }
        particle.formations.operational_status[formation] = 0;
        particle.formations.availability[formation] = 0.0;
    }
}

pub fn update(
    particle: &mut ParticleState,
    _topology: &StaticTopology,
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
    consume_proto_formation_draws(particle, config, rng, elapsed_days);
    advance_protos(particle, _topology, config, rng, elapsed_days, time);
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

        let mut represented_values = Vec::new();
        let mut identity_weighted_values = Vec::new();
        for person in 0..particle.people.locality.len() {
            if particle.people.organization[person] as usize != organization
                || particle.people.armed_fraction[person] <= 0.0
            {
                continue;
            }
            let represented = particle.people.represented_population[person]
                * particle.people.armed_fraction[person];
            represented_values.push(represented);
            identity_weighted_values.push(
                represented * particle.people.identities[person * 3 + 2],
            );
        }
        let represented_weight = python_sum(&represented_values);
        let identity_weighted = python_sum(&identity_weighted_values);
        let mean_identity = identity_weighted / represented_weight.max(1e-9);
        let mut identity_variance_values = Vec::new();
        for person in 0..particle.people.locality.len() {
            if particle.people.organization[person] as usize != organization
                || particle.people.armed_fraction[person] <= 0.0
            {
                continue;
            }
            let represented = particle.people.represented_population[person]
                * particle.people.armed_fraction[person];
            identity_variance_values.push(
                represented * (particle.people.identities[person * 3 + 2] - mean_identity).powi(2),
            );
        }
        let identity_variance =
            python_sum(&identity_variance_values) / represented_weight.max(1e-9);
        let cycle_scale = elapsed_days / 7.0;
        let prior_cohesion = particle.organizations.cohesion[organization];
        let updated_cohesion = clamp01(
            prior_cohesion
                + cycle_scale
                    * (0.025 * particle.organizations.capital_social[organization]
                        - config.organization_ecology.cohesion_loss_memory * losses
                        - 0.02 * identity_variance),
        );
        if crate::trace_env!("PINELAND_ORG_TRACE") {
            eprintln!(
                "ORG_COHESION_TRACE time={:.17} org={} elapsed={:.17} prior={:.17} losses={:.17} represented={:.17} mean_identity={:.17} identity_variance={:.17} cycle_scale={:.17} capital_social={:.17} updated={:.17} rng_index={}",
                time,
                organization,
                elapsed_days,
                prior_cohesion,
                losses,
                represented_weight,
                mean_identity,
                identity_variance,
                cycle_scale,
                particle.organizations.capital_social[organization],
                updated_cohesion,
                rng.state().index,
            );
        }
        particle.organizations.cohesion[organization] = updated_cohesion;
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
        let conditioned = conditioned_active(particle, config, organization, time);
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
        let collapse_realized = !conditioned
            && (particle.organizations.capital[organization] <= 0.0
                || particle.organizations.cohesion[organization] < 0.12
                || represented_weight <= 1e-9
                || collapse_draw < collapse_hazard);
        if collapse_realized {
            collapse_organization(particle, organization);
        }
        let _ = (formation_values, _split_realized);
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
