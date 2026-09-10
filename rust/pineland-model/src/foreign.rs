//! Foreign affairs, sanctuary/support, migration pressure, and withdrawal.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub(crate) const FOREIGN_KIND: u8 = 5;

pub(crate) fn append_relation(
    particle: &mut ParticleState,
    first: usize,
    second: usize,
    status: u8,
    hostility_memory: f64,
    cooperation_memory: f64,
    time: f64,
) {
    if let Some(index) = particle
        .relations
        .organization_a
        .iter()
        .zip(&particle.relations.organization_b)
        .position(|(left, right)| {
            (*left as usize == first && *right as usize == second)
                || (*left as usize == second && *right as usize == first)
        })
    {
        particle.relations.status[index] = status;
        particle.relations.hostility_memory[index] = hostility_memory;
        particle.relations.cooperation_memory[index] = cooperation_memory;
        particle.relations.updated_at[index] = time;
        return;
    }
    particle.relations.organization_a.push(first as u32);
    particle.relations.organization_b.push(second as u32);
    particle.relations.status.push(status);
    particle.relations.rivalry_memory.push(0.0);
    particle.relations.hostility_memory.push(hostility_memory);
    particle
        .relations
        .cooperation_memory
        .push(cooperation_memory);
    particle.relations.updated_at.push(time);
    particle.relations.last_interaction_at.push(0.0);
    particle.relations.has_last_interaction.push(0);
}

pub(crate) fn append_foothold_rows(
    particle: &mut ParticleState,
    locality_count: usize,
    organization: usize,
) {
    for locality in 0..locality_count {
        particle.footholds.organization.push(organization as u32);
        particle.footholds.locality.push(locality as u32);
        particle.footholds.strength.push(0.0);
        particle.footholds.raw_signal.push(0.0);
        particle.footholds.membership.push(0.0);
        particle.footholds.embeddedness.push(0.0);
        particle.footholds.access.push(0.0);
        particle.footholds.target_knowledge.push(0.0);
        particle.footholds.infrastructure.push(0.0);
        particle.footholds.sustainment.push(0.0);
        particle.footholds.updated_at.push(0.0);
        particle.footholds.first_activated_at.push(-1.0e9);
        particle.footholds.last_activated_at.push(-1.0e9);
        particle.footholds.cumulative_active_days.push(0.0);
        particle.footholds.cumulative_arrivals.push(0.0);
        particle.footholds.cumulative_recruits.push(0.0);
        particle.footholds.cumulative_actions.push(0.0);
        particle.footholds.viable_activation_count.push(0);
        particle.footholds.renewal_count.push(0);
        particle.footholds.active.push(0);
    }
}

fn foreign_border(particle: &ParticleState, state: usize) -> Option<usize> {
    (0..particle.foreign.border_foreign_state.len())
        .filter(|index| particle.foreign.border_foreign_state[*index] as usize == state)
        .max_by(|left, right| {
            let left_score = particle.foreign.border_social_permeability[*left]
                * particle.foreign.border_language_overlap[*left]
                / particle.foreign.border_terrain_friction[*left].max(0.2);
            let right_score = particle.foreign.border_social_permeability[*right]
                * particle.foreign.border_language_overlap[*right]
                / particle.foreign.border_terrain_friction[*right].max(0.2);
            left_score
                .total_cmp(&right_score)
                .then_with(|| right.cmp(left))
        })
}

fn best_border_zone(topology: &StaticTopology, locality: usize) -> usize {
    topology
        .zones_for_locality((locality as u32).into())
        .max_by(|left, right| {
            topology.zone_population_share[*left]
                .total_cmp(&topology.zone_population_share[*right])
                .then_with(|| right.cmp(left))
        })
        .unwrap_or_else(|| topology.locality_central_zone[locality] as usize)
}

fn ensure_foreign_relations(particle: &mut ParticleState, organization: usize, time: f64) {
    // The Python relation key is lexicographically sorted by the external
    // organization identifier.  For the fixed Native-v1 registry, only fdf
    // sorts before "foreign-*"; every other initial identifier sorts after it.
    let add = |particle: &mut ParticleState,
               other: usize,
               status: u8,
               hostility: f64,
               cooperation: f64| {
        let (first, second) = if other == crate::MILITARY {
            (other, organization)
        } else {
            (organization, other)
        };
        append_relation(
            particle,
            first,
            second,
            status,
            hostility,
            cooperation,
            time,
        );
    };
    add(particle, crate::GOVERNMENT, 0, 0.0, 1.0);
    add(particle, crate::MILITARY, 0, 0.0, 1.0);
    add(particle, crate::POLICE, 0, 0.0, 1.0);
    let active_insurgents = (0..organization)
        .filter(|candidate| {
            particle.organizations.kind[*candidate] == crate::INSURGENT as u8
                && particle.organizations.active[*candidate] != 0
        })
        .collect::<Vec<_>>();
    for insurgent in active_insurgents {
        add(particle, insurgent, 4, 1.0, 0.0);
    }
    // ensure_relation for all remaining organizations follows the Python
    // insertion order and leaves their default neutral status untouched.
    for other in 0..organization {
        if other == crate::GOVERNMENT || other == crate::MILITARY || other == crate::POLICE {
            continue;
        }
        let already_present = particle
            .relations
            .organization_a
            .iter()
            .zip(&particle.relations.organization_b)
            .any(|(left, right)| {
                (*left as usize == other && *right as usize == organization)
                    || (*left as usize == organization && *right as usize == other)
            });
        if !already_present {
            add(particle, other, 2, 0.0, 0.0);
        }
    }
}

pub(crate) fn shift_dynamic_observer_codes_after_foreign_intervention(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    state: usize,
) {
    let old_organizations = particle.organizations.kind.len();
    let old_formations = particle.formations.personnel.len();
    let old_posts = particle.security_posts.locality.len();
    let num_aux = crate::information::auxiliary_node_ids(particle, topology).len();

    let formation_start = old_organizations as u32;
    let post_start = (old_organizations + old_formations) as u32;
    let aux_start = (old_organizations + old_formations + old_posts) as u32;
    let command_start = aux_start + num_aux as u32;

    let old_cmds = crate::information::command_node_ids(particle);
    let new_org_name = format!("foreign-neighbor-{}", state + 1);
    let new_cmd = format!("CMD:{new_org_name}");
    let insert_pos = old_cmds.binary_search(&new_cmd).unwrap_or_else(|pos| pos);
    let cmd_split_code = command_start + insert_pos as u32;

    let total_command_codes = command_start + old_cmds.len() as u32;
    let shift_code = |code: &mut u32| {
        if *code != u32::MAX
            && *code < 0x2000_0000
            && *code >= formation_start
            && *code < total_command_codes
        {
            if *code < post_start {
                *code += 1;
            } else if *code < aux_start {
                *code += 2;
            } else if *code < command_start {
                *code += 3;
            } else if *code < cmd_split_code {
                *code += 3;
            } else {
                *code += 4;
            }
        }
    };

    for key in &mut particle.beliefs.keys {
        if key.kind == 3 {
            shift_code(&mut key.observer);
        }
    }
    for state in [
        &mut particle.presence_beliefs,
        &mut particle.node_presence_beliefs,
    ] {
        for key in &mut state.keys {
            shift_code(&mut key.observer);
        }
    }
    for observation in &mut particle.information_observations {
        shift_code(&mut observation.source);
        shift_code(&mut observation.observer_node);
        shift_code(&mut observation.source_identity);
    }
    for relay in &mut particle.information_relays {
        shift_code(&mut relay.source_node);
        shift_code(&mut relay.destination_node);
        for node in &mut relay.route {
            shift_code(node);
        }
    }
    for entry in &mut particle.information_history {
        shift_code(&mut entry.source_identity);
    }
}

fn create_foreign_intervention(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    state: usize,
    time: f64,
) {
    let Some(border) = foreign_border(particle, state) else {
        return;
    };
    let locality = particle.foreign.border_locality[border] as usize;
    let zone = best_border_zone(topology, locality);
    let organization = particle.organizations.kind.len();
    let formation = particle.formations.personnel.len();
    let resources = particle.foreign.resources[state] * 0.02;

    shift_dynamic_observer_codes_after_foreign_intervention(particle, topology, state);
    particle
        .locality
        .ensure_organization_capacity(organization + 1);
    particle
        .people
        .ensure_organization_capacity(organization + 1);
    particle.organizations.kind.push(FOREIGN_KIND);
    particle.organizations.active.push(1);
    particle.organizations.capital.push(resources);
    particle.organizations.cohesion.push(0.72);
    particle.organizations.discipline.push(0.75);
    particle.organizations.accountability.push(0.5);
    particle.organizations.local_knowledge.push(0.15);
    particle.organizations.persistence.push(0.65);
    particle.organizations.mobility.push(0.7);
    particle.organizations.institutional_quality.push(0.7);
    particle.organizations.external_support.push(0.0);
    particle.organizations.member_population.push(0.0);
    particle.organizations.founded_at.push(0.0);
    particle.organizations.succession_count.push(0);
    particle.organizations.capital_social.push(0.0);
    particle.organizations.capital_political.push(0.0);
    particle.organizations.capital_organizational.push(0.0);
    particle.organizations.capital_material.push(0.0);
    particle
        .organizations
        .phenotype
        .extend_from_slice(&[0.5; 8]);
    particle
        .organizations
        .ideology
        .extend_from_slice(&[0.5, 0.0]);
    particle.organizations.external_sanctuary.push(0.0);
    particle.organizations.adaptation_rate.push(0.12);
    particle.organizations.leader.push(u32::MAX);

    append_foothold_rows(particle, topology.locality_count(), organization);

    particle.formations.organization.push(organization as u32);
    particle.formations.locality.push(locality as u32);
    particle.formations.microzone.push(u32::MAX);
    particle.formations.personnel.push(900.0);
    particle.formations.quality.push(0.78);
    particle.formations.cohesion.push(0.76);
    particle.formations.readiness.push(0.82);
    particle.formations.sustainment.push(0.9);
    particle.formations.information.push(0.38);
    particle.formations.mobility.push(0.72);
    particle.formations.command.push(0.68);
    particle.formations.embeddedness.push(0.12);
    particle.formations.fatigue.push(0.0);
    particle.formations.availability.push(0.85);
    particle.formations.supply_stock.push(20_250.0);
    particle.formations.supply_capacity.push(27_000.0);
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
    particle.formations.external_state.push(state as u32);

    particle.patrols.formation.push(formation as u32);
    particle.patrols.active.push(1);
    particle.patrols.route_position.push(zone as u32);
    particle.patrols.route_target.push(zone as u32);
    particle.patrols.last_departure.push(-1.0e9);
    particle.patrols.next_available.push(time);
    particle.patrols.response_fraction.push(0.35);
    particle.patrols.presence_accounted_at.push(-1.0e300);
    particle.patrols.detections.push(0);

    particle
        .security_posts
        .organization
        .push(organization as u32);
    particle.security_posts.locality.push(locality as u32);
    particle.security_posts.microzone.push(zone as u32);
    particle.security_posts.personnel.push(135.0);
    particle.security_posts.presence.push(0.2);
    particle.security_posts.available_fraction.push(0.7);
    particle.security_posts.formation.push(formation as u32);
    particle
        .security_posts
        .detection_rate
        .push(config.information.fixed_post_report_rate);
    particle
        .security_posts
        .reliability
        .push(config.information.prior_confidence);
    particle.security_posts.updated_at.push(0.0);
    particle.security_posts.staffed.push(1);

    particle.logistics.organization.push(organization as u32);
    particle.logistics.locality.push(locality as u32);
    particle.logistics.source_stock.push(12_000.0);
    particle.logistics.source_capacity.push(18_000.0);
    particle.logistics.source_production.push(350.0);
    particle.logistics.cumulative_produced += 20_250.0 + 12_000.0;

    particle
        .command_edges
        .organization
        .push(organization as u32);
    particle.command_edges.formation.push(formation as u32);
    particle.command_edges.reliability.push(0.7);
    particle.command_edges.latency_hours.push(7.0);

    ensure_foreign_relations(particle, organization, time);
    particle.foreign_interventions.push(
        state as u32,
        crate::GOVERNMENT as u32,
        time,
        if particle.foreign.humanitarian_preference[state] > 0.5 {
            0
        } else {
            1
        },
        config.foreign_affairs.host_transfer_efficiency,
        config.foreign_affairs.host_crowding_out,
        formation as u32,
    );
}

fn apply_interventions(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    time: f64,
    elapsed_days: f64,
) {
    let cycle_scale = elapsed_days / 30.0;
    let local_institutions = particle
        .political
        .institution_level
        .iter()
        .enumerate()
        .filter(|(_, level)| matches!(**level, 1 | 2))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    for intervention in 0..particle.foreign_interventions.count() {
        let status = particle.foreign_interventions.status[intervention];
        if status == 1 {
            let formation = particle.foreign_interventions.force_formation[intervention] as usize;
            if formation >= particle.formations.personnel.len() {
                continue;
            }
            let contribution = particle.formations.effective_strength(formation) / 25.0;
            particle.foreign_interventions.provided_capacity[intervention] = contribution;
            particle.foreign_interventions.peak_provided_capacity[intervention] =
                particle.foreign_interventions.peak_provided_capacity[intervention]
                    .max(contribution);
            for institution in &local_institutions {
                let transfer_gain = 0.002
                    * particle.foreign_interventions.transfer_efficiency[intervention]
                    * contribution
                    / local_institutions.len().max(1) as f64
                    * cycle_scale;
                let crowding_loss = 0.002
                    * particle.foreign_interventions.crowding_out[intervention]
                    * contribution
                    / local_institutions.len().max(1) as f64
                    * cycle_scale;
                particle.political.institution_capacity[*institution] = clamp01(
                    particle.political.institution_capacity[*institution] + transfer_gain
                        - crowding_loss,
                );
                particle
                    .foreign_interventions
                    .cumulative_retained_host_capacity[intervention] += transfer_gain;
                particle.foreign_interventions.cumulative_crowding_out[intervention] +=
                    crowding_loss;
            }
            particle
                .foreign_interventions
                .cumulative_transferred_capacity[intervention] += contribution
                * particle.foreign_interventions.transfer_efficiency[intervention]
                * cycle_scale;

            let locality = particle.formations.locality[formation] as usize;
            if locality < particle.locality.population.len() {
                let benefit =
                    contribution / (particle.locality.population[locality] * 0.001).max(1.0);
                let harm = particle.formations.cumulative_losses[formation]
                    / particle.formations.personnel[formation].max(1.0);
                for person in 0..particle.people.residence.len() {
                    if particle.people.residence[person] as usize != locality {
                        continue;
                    }
                    let language_affinity = (0..4)
                        .map(|language| particle.people.languages[person * 4 + language])
                        .fold(0.0, f64::max);
                    let foreignness = (1.0 - particle.people.identities[person * 3 + 2])
                        * (1.0 - language_affinity);
                    particle.people.government_legitimacy[person] = clamp01(
                        particle.people.government_legitimacy[person]
                            + cycle_scale
                                * (0.006 * benefit * particle.people.trust[person]
                                    - 0.004 * foreignness
                                    - 0.008 * harm),
                    );
                }
            }
            let state = particle.foreign_interventions.foreign_state[intervention] as usize;
            if state < particle.foreign.cumulative_casualties.len() {
                particle.foreign.cumulative_casualties[state] = particle
                    .foreign_interventions
                    .force_formation
                    .iter()
                    .enumerate()
                    .filter(|(candidate, _)| {
                        particle.foreign_interventions.foreign_state[*candidate] as usize == state
                    })
                    .map(|(_, candidate)| {
                        particle
                            .formations
                            .cumulative_losses
                            .get(*candidate as usize)
                            .copied()
                            .unwrap_or(0.0)
                    })
                    .sum();
            }
            if state < particle.foreign.willingness.len()
                && particle.foreign.willingness[state] < config.foreign_affairs.withdrawal_threshold
            {
                particle.foreign_interventions.status[intervention] = 2;
                particle.foreign_interventions.withdrawal_rate[intervention] =
                    config.foreign_affairs.withdrawal_rate;
            }
        }
        // Withdrawal movement is handled by the ordinary force-movement
        // process once its explicit order is created.  The current 90-day
        // certification cases remain active, but preserving the status row
        // here makes the checkpoint boundary lossless.
        let _ = time;
    }
}

fn logistic(value: f64) -> f64 {
    if value >= 0.0 {
        1.0 / (1.0 + python_exp(-value))
    } else {
        let exponential = python_exp(value);
        exponential / (1.0 + exponential)
    }
}

fn reference_probability(probability: f64, elapsed_days: f64, reference_days: f64) -> f64 {
    let probability = clamp01(probability);
    if probability <= 0.0 || elapsed_days <= 0.0 {
        0.0
    } else if probability >= 1.0 {
        1.0
    } else {
        1.0 - python_exp(
            (elapsed_days / reference_days.max(f64::MIN_POSITIVE)) * (1.0 - probability).ln(),
        )
    }
}

fn expected_destination_control(
    particle: &ParticleState,
    person: usize,
    locality: usize,
    locality_count: usize,
) -> f64 {
    let scalar = particle.people.expected_control[person * 2];
    let mask_index = person * locality_count + locality;
    let value_index = mask_index * 2;
    if mask_index < particle.people.expected_destination_control_present.len()
        && particle.people.expected_destination_control_present[mask_index] & 1 != 0
        && value_index < particle.people.expected_destination_control.len()
    {
        particle.people.expected_destination_control[value_index]
    } else {
        scalar
    }
}

fn interpreter_channel_quality(
    particle: &ParticleState,
    foreign_state: usize,
    locality: usize,
    language_overlap: f64,
    social_permeability: f64,
    kinship_overlap: f64,
) -> f64 {
    let capacity = clamp01(
        language_overlap
            * (0.45 + 0.35 * clamp01(social_permeability) + 0.20 * clamp01(kinship_overlap)),
    );
    if capacity <= 0.0 || locality >= particle.locality.population.len() {
        return 0.0;
    }
    let demographic_quality =
        clamp01(0.35 + 0.35 * clamp01(social_permeability) + 0.30 * clamp01(kinship_overlap));
    let mut broker_quality: f64 = 0.0;
    for index in 0..particle.foreign.interpreter_person.len() {
        if particle.foreign.interpreter_foreign_state[index] as usize != foreign_state
            || particle.foreign.interpreter_locality[index] as usize != locality
        {
            continue;
        }
        broker_quality = broker_quality.max(
            particle.foreign.interpreter_foreign_language[index]
                * particle.foreign.interpreter_local_language[index]
                * particle.foreign.interpreter_foreign_trust[index]
                * particle.foreign.interpreter_local_trust[index]
                * particle.foreign.interpreter_cultural_knowledge[index],
        );
    }
    clamp01(capacity * demographic_quality.max(broker_quality))
}

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    // The reference process returns before touching state or consuming RNG
    // when the scheduler reports the initialization event with zero elapsed
    // time.
    if !config.foreign_affairs.enabled || elapsed_days <= 0.0 {
        return;
    }
    // Python evaluates the cross-border migration hazard for every
    // representative person before it updates diaspora links or foreign
    // beliefs.  External membership is explicit state: it changes the
    // return branch, but still consumes exactly one draw per person.
    let locality_count = topology.locality_count();
    for person in 0..particle.people.locality.len() {
        if particle.people.external_state[person] != u32::MAX {
            let state = particle.people.external_state[person] as usize;
            let perceived_home_security = expected_destination_control(
                particle,
                person,
                particle.people.home[person] as usize,
                locality_count,
            );
            let safety_gain =
                (1.0 - perceived_home_security) - (1.0 - particle.foreign.opportunity[state]) * 0.2;
            let reference_hazard = clamp01(
                config.foreign_affairs.return_rate
                    * logistic(-2.0 * safety_gain + particle.people.state_legitimacy[person]),
            );
            let hazard =
                reference_probability(reference_hazard, config.foreign_affairs.interval_days, 30.0);
            if rng.random() < hazard {
                particle.people.external_state[person] = u32::MAX;
                particle.people.migration_status[person] = 4;
                particle.people.origin_tie_strength[person] =
                    clamp01(particle.people.origin_tie_strength[person] + 0.15);
            } else {
                particle.people.origin_tie_strength[person] *=
                    python_exp(-0.02 * config.foreign_affairs.interval_days / 30.0);
                for link in 0..particle.foreign.diaspora_person.len() {
                    if particle.foreign.diaspora_person[link] as usize == person {
                        particle.foreign.diaspora_social_strength[link] =
                            particle.people.origin_tie_strength[person];
                    }
                }
            }
            continue;
        }

        let locality = particle.people.residence[person] as usize;
        let district = topology.locality_to_district[locality] as usize;
        let Some(border) = (0..particle.foreign.border_foreign_state.len())
            .filter(|index| particle.foreign.border_district[*index] as usize == district)
            .max_by(|left, right| {
                particle.foreign.border_social_permeability[*left]
                    .total_cmp(&particle.foreign.border_social_permeability[*right])
            })
        else {
            continue;
        };
        let state = particle.foreign.border_foreign_state[border] as usize;
        let pressure = particle.locality.violence[locality]
            + particle.people.fear[person]
            + 0.4 * (1.0 - particle.people.government_legitimacy[person]);
        let attraction = particle.foreign.opportunity[state]
            + particle.foreign.border_kinship_overlap[border]
            + particle.foreign.border_language_overlap[border]
            - particle.foreign.border_terrain_friction[border]
                * (1.0 - particle.foreign.border_legal_permeability[border]);
        let reference_hazard =
            clamp01(config.foreign_affairs.migration_rate * logistic(pressure + attraction - 1.6));
        let hazard =
            reference_probability(reference_hazard, config.foreign_affairs.interval_days, 30.0);
        if rng.random() < hazard {
            particle.people.external_state[person] = state as u32;
            particle.people.migration_status[person] =
                if particle.locality.violence[locality] > 0.25 {
                    1
                } else if particle.people.fear[person] > 0.55 {
                    2
                } else {
                    3
                };
            particle.people.origin_tie_strength[person] = 1.0;
            particle.foreign.diaspora_person.push(person as u32);
            particle.foreign.diaspora_foreign_state.push(state as u32);
            particle
                .foreign
                .diaspora_origin_locality
                .push(particle.people.home[person]);
            particle.foreign.diaspora_social_strength.push(1.0);
            particle
                .foreign
                .diaspora_financial_capacity
                .push(particle.people.resources[person] * 0.2);
            particle
                .foreign
                .diaspora_information_reliability
                .push(clamp01(
                    0.35 + 0.5 * particle.foreign.border_language_overlap[border],
                ));
            particle.foreign.diaspora_created_at.push(time);
        }
    }

    // Python snapshots the active insurgent recipients once, before the
    // neighbor-state loop.  Support recipient selection is therefore based
    // on the same live organization set for every foreign state in this
    // event, with prior support breaking ties by organization identity.
    let active_insurgents = (0..particle.organizations.kind.len())
        .filter(|&organization| {
            particle.organizations.kind[organization] == 3
                && particle.organizations.active.get(organization).copied() == Some(1)
        })
        .collect::<Vec<_>>();
    let active_foreign_states = particle
        .foreign_interventions
        .status
        .iter()
        .enumerate()
        .filter(|(_, status)| **status == 1)
        .map(|(index, _)| particle.foreign_interventions.foreign_state[index] as usize)
        .collect::<Vec<_>>();

    // Diaspora remittances are resource transfers from the foreign system to
    // the represented civilian cohort.  Message draws occur after every
    // active link's transfer, exactly as in the Python registry loop.
    let cycle_scale = config.foreign_affairs.interval_days / 30.0;
    for link in 0..particle.foreign.diaspora_person.len() {
        let person = particle.foreign.diaspora_person[link] as usize;
        if particle.people.external_state[person] == u32::MAX {
            continue;
        }
        let state = particle.foreign.diaspora_foreign_state[link] as usize;
        let amount = particle.foreign.resources[state].min(
            particle.foreign.diaspora_financial_capacity[link]
                * config.foreign_affairs.diaspora_remittance_rate
                * particle.foreign.diaspora_social_strength[link]
                * cycle_scale,
        );
        particle.foreign.resources[state] -= amount;
        let updated = particle.people.resources[person] + amount;
        let applied = updated.max(0.0) - particle.people.resources[person];
        particle.people.resources[person] += applied;
        let household = particle.people.household[person] as usize;
        if household < particle.households.resources.len() {
            particle.households.resources[household] += applied;
            if particle.households.resources[household].abs() <= 1e-9 {
                particle.households.resources[household] = 0.0;
            }
        }
        particle.foreign.cumulative_external_remittances += amount;
        let message_probability = reference_probability(
            clamp01(
                config.foreign_affairs.diaspora_information_rate
                    * particle.foreign.diaspora_information_reliability[link],
            ),
            config.foreign_affairs.interval_days,
            30.0,
        );
        let _message = rng.random() < message_probability;
    }

    for state in 0..particle.foreign.resources.len() {
        let mut border_indices = Vec::new();
        for border in 0..particle.foreign.border_foreign_state.len() {
            if particle.foreign.border_foreign_state[border] as usize == state {
                border_indices.push(border);
            }
        }
        for border in border_indices {
            let locality = particle.foreign.border_locality[border] as usize;
            let interpreter_quality = interpreter_channel_quality(
                particle,
                state,
                locality,
                particle.foreign.border_language_overlap[border],
                particle.foreign.border_social_permeability[border],
                particle.foreign.border_kinship_overlap[border],
            );
            // Foreign actors consume the government actor's reported belief,
            // not realized locality control.  This is the same
            // `belief_view("government").locality_control(..., "government")`
            // boundary used by Python.
            let host_estimate =
                crate::beliefs::control_estimate(particle, crate::GOVERNMENT, locality)[1];
            let noise = config.foreign_affairs.belief_noise
                * (1.0 - config.foreign_affairs.interpreter_effect * interpreter_quality);
            if let Some(belief) = (0..particle.foreign.belief_foreign_state.len()).find(|index| {
                particle.foreign.belief_foreign_state[*index] as usize == state
                    && particle.foreign.belief_locality[*index] as usize == locality
            }) {
                let government = clamp01(host_estimate + rng.normalvariate(0.0, noise));
                let insurgent = clamp01(1.0 - government + rng.normalvariate(0.0, noise));
                particle.foreign.belief_government_control[belief] = government;
                particle.foreign.belief_insurgent_presence[belief] = insurgent;
                particle.foreign.belief_confidence[belief] = clamp01(
                    0.2 + 0.45 * interpreter_quality
                        + 0.2 * particle.foreign.border_language_overlap[border],
                );
                particle.foreign.belief_updated_at[belief] = time;
                if crate::trace_env!("PINELAND_FOREIGN_TRACE") {
                    eprintln!(
                        "FOREIGN_BELIEF time={:.17} index={} state={} locality={} host={:.17} quality={:.17} noise={:.17} government={:.17} insurgent={:.17} confidence={:.17}",
                        time,
                        belief,
                        state,
                        locality,
                        host_estimate,
                        interpreter_quality,
                        noise,
                        government,
                        insurgent,
                        particle.foreign.belief_confidence[belief],
                    );
                }
            }
        }

        let belief_indices = (0..particle.foreign.belief_foreign_state.len())
            .filter(|index| particle.foreign.belief_foreign_state[*index] as usize == state)
            .collect::<Vec<_>>();
        let belief_values = belief_indices
            .iter()
            .map(|index| particle.foreign.belief_government_control[*index])
            .collect::<Vec<_>>();
        let perceived_progress = python_sum(&belief_values) / belief_indices.len().max(1) as f64;
        let cost_denominator =
            (particle.foreign.resources[state] + particle.foreign.cumulative_cost[state]).max(1.0);
        let cost_pressure = particle.foreign.cumulative_cost[state] / cost_denominator;
        let rival_presence = particle.foreign.rival_indices[particle.foreign.rival_offsets[state]
            as usize
            ..particle.foreign.rival_offsets[state + 1] as usize]
            .iter()
            .filter(|rival| active_foreign_states.contains(&(**rival as usize)))
            .count() as f64;
        let willingness = clamp01(logistic(
            1.2 * particle.foreign.stability_preference[state]
                + particle.foreign.regional_influence[state]
                + config.foreign_affairs.rival_reaction * rival_presence
                + perceived_progress
                - config.foreign_affairs.willingness_cost_weight * cost_pressure
                - config.foreign_affairs.willingness_casualty_weight
                    * particle.foreign.cumulative_casualties[state]
                    / 100.0
                - particle.foreign.domestic_opposition[state]
                - 1.0,
        ));
        particle.foreign.willingness[state] = willingness;

        // The Python process samples support and intervention decisions for
        // every neighbor, even when both probabilities are zero in a
        // particular realization.  Preserve those stream positions now.
        let support_probability = reference_probability(
            clamp01(willingness * 0.3),
            config.foreign_affairs.interval_days,
            30.0,
        );
        let support_draw = if config.foreign_affairs.support_budget_fraction > 0.0 {
            Some(rng.random())
        } else {
            None
        };
        let support_selected = support_draw.is_some_and(|draw| draw < support_probability);
        if support_selected {
            let recipient = if particle.foreign.government_alignment[state]
                >= particle.foreign.ideological_alignment[state]
                || active_insurgents.is_empty()
            {
                crate::GOVERNMENT
            } else {
                active_insurgents
                    .iter()
                    .copied()
                    .min_by(|left, right| {
                        let left_support = particle
                            .foreign
                            .support_foreign_state
                            .iter()
                            .zip(&particle.foreign.support_recipient)
                            .zip(&particle.foreign.support_total)
                            .filter(|((foreign, candidate), _)| {
                                **foreign as usize == state && **candidate as usize == *left
                            })
                            .map(|(_, total)| *total)
                            .sum::<f64>();
                        let right_support = particle
                            .foreign
                            .support_foreign_state
                            .iter()
                            .zip(&particle.foreign.support_recipient)
                            .zip(&particle.foreign.support_total)
                            .filter(|((foreign, candidate), _)| {
                                **foreign as usize == state && **candidate as usize == *right
                            })
                            .map(|(_, total)| *total)
                            .sum::<f64>();
                        right_support
                            .total_cmp(&left_support)
                            .then_with(|| left.cmp(right))
                    })
                    .unwrap_or(crate::GOVERNMENT)
            };
            let total = particle.foreign.resources[state].min(
                particle.foreign.resources[state]
                    * config.foreign_affairs.support_budget_fraction
                    * willingness,
            );
            if total > 0.0 {
                particle.foreign.resources[state] -= total;
                let financial = total * 0.22;
                let political = total * 0.08;
                let material = total * 0.19;
                let training = total * 0.14;
                let organizational = total * 0.10;
                let sanctuary = total * 0.12;
                let denominator = total.max(1.0);
                particle.organizations.capital[recipient] += financial;
                if recipient == crate::GOVERNMENT {
                    let learning = training + organizational;
                    let institution_count = particle.political.institution_capacity.len();
                    for capacity in &mut particle.political.institution_capacity {
                        *capacity = clamp01(
                            *capacity
                                + learning / denominator * 0.02 / institution_count.max(1) as f64,
                        );
                    }
                    for person in 0..particle.people.government_legitimacy.len() {
                        particle.people.government_legitimacy[person] = clamp01(
                            particle.people.government_legitimacy[person]
                                + political / denominator
                                    * 0.002
                                    * (particle.people.trust[person] - 0.35),
                        );
                    }
                } else if particle.organizations.kind[recipient] == 3 {
                    // Match deliver_support's insurgent-recipient effects.
                    // Financial support enters the ordinary organization
                    // resource account above; these additional channels alter
                    // local execution and sponsor dependence without creating
                    // personnel.
                    particle.organizations.external_sanctuary[recipient] =
                        clamp01(particle.organizations.external_sanctuary[recipient] + sanctuary / denominator);
                    let phenotype = recipient * 8 + 7;
                    if phenotype < particle.organizations.phenotype.len() {
                        particle.organizations.phenotype[phenotype] =
                            clamp01(particle.organizations.phenotype[phenotype] + 0.04);
                    }
                    particle.organizations.capital_organizational[recipient] = clamp01(
                        particle.organizations.capital_organizational[recipient]
                            + organizational / denominator * 0.08,
                    );
                    let formation_count = particle
                        .formations
                        .organization
                        .iter()
                        .filter(|owner| **owner as usize == recipient)
                        .count()
                        .max(1) as f64;
                    let material_per_formation = material / formation_count;
                    for formation in 0..particle.formations.organization.len() {
                        if particle.formations.organization[formation] as usize != recipient {
                            continue;
                        }
                        particle.formations.quality[formation] = clamp01(
                            particle.formations.quality[formation] + training / denominator * 0.025,
                        );
                        particle.formations.cohesion[formation] = clamp01(
                            particle.formations.cohesion[formation]
                                + training / denominator * 0.015,
                        );
                        let accepted = material_per_formation.min(
                            particle.formations.supply_capacity[formation]
                                - particle.formations.supply_stock[formation],
                        );
                        particle.formations.supply_stock[formation] += accepted;
                        particle.logistics.cumulative_produced += accepted;
                    }
                }
                particle.foreign.cumulative_cost[state] += total;
                particle.foreign.support_foreign_state.push(state as u32);
                particle.foreign.support_recipient.push(recipient as u32);
                particle.foreign.support_total.push(total);
            }
        }
        let intervention_probability = reference_probability(
            clamp01(config.foreign_affairs.intervention_base_hazard * willingness),
            config.foreign_affairs.interval_days,
            30.0,
        );
        let intervention_selected = if active_foreign_states.contains(&state) {
            false
        } else {
            rng.random() < intervention_probability
        };
        if intervention_selected {
            create_foreign_intervention(particle, topology, config, state, time);
        }
    }
    apply_interventions(particle, config, time, elapsed_days);
}

pub fn withdrawal_fraction(config: &SimulationConfig, willingness: f64) -> f64 {
    if willingness < config.foreign_affairs.withdrawal_threshold {
        config.foreign_affairs.withdrawal_rate
    } else {
        0.0
    }
}
