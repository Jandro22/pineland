//! Endogenous government-capacity regeneration for the post-parity theory core.
//!
//! The parity-era model represented government outputs well but treated much
//! of the state itself as inherited stock.  This module closes that causal
//! loop without inventing a symmetric insurgent-style branching process.  It
//! models a hierarchical state as four linked mechanisms:
//!
//! 1. population -> recruitment pipeline -> trained reserve -> police/military;
//! 2. treasury + absorptive capacity -> administrative rebuilding;
//! 3. police + cooperation + administration -> intelligence penetration;
//! 4. intelligence penetration -> disruption of rooted insurgent membership.
//!
//! The process is deterministic conditional on the particle state.  Stochastic
//! variation enters through the social, political, combat, economic, and
//! insurgent processes that generate its inputs.  This keeps the state-side
//! theory auditable and avoids adding an arbitrary RNG channel solely for
//! regeneration.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

const NO_ORGANIZATION: u32 = u32::MAX;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct StateRegenerationSummary {
    pub recruited: f64,
    pub graduated: f64,
    pub deployed_police: f64,
    pub deployed_military: f64,
    pub administrative_rebuild: f64,
    pub underground_disrupted: f64,
}

fn local_people_means(particle: &ParticleState, locality: usize) -> (f64, f64, f64) {
    let mut weights = Vec::new();
    let mut state = Vec::new();
    let mut government = Vec::new();
    let mut access = Vec::new();
    for person in 0..particle.people.residence.len() {
        if particle.people.residence[person] as usize != locality {
            continue;
        }
        let weight = particle.people.represented_population[person].max(0.0);
        if weight <= 0.0 {
            continue;
        }
        weights.push(weight);
        state.push(weight * clamp01(particle.people.state_legitimacy[person]));
        government.push(weight * clamp01(particle.people.government_legitimacy[person]));
        access.push(weight * clamp01(particle.people.political_access[person]));
    }
    let total = python_sum(&weights);
    if total <= 1.0e-12 {
        return (0.5, 0.5, 0.5);
    }
    (
        clamp01(python_sum(&state) / total),
        clamp01(python_sum(&government) / total),
        clamp01(python_sum(&access) / total),
    )
}

fn local_public_cooperation(particle: &ParticleState, locality: usize) -> f64 {
    let mut weighted = Vec::new();
    let mut total = 0.0;
    for community in 0..particle.communities.locality.len() {
        if particle.communities.locality[community] as usize != locality {
            continue;
        }
        let start = particle
            .communities
            .member_offsets
            .get(community)
            .copied()
            .unwrap_or(0) as usize;
        let end = particle
            .communities
            .member_offsets
            .get(community + 1)
            .copied()
            .unwrap_or(start as u32) as usize;
        let mut represented = 0.0;
        for offset in start..end.min(particle.communities.member_indices.len()) {
            let person = particle.communities.member_indices[offset] as usize;
            represented += particle
                .people
                .represented_population
                .get(person)
                .copied()
                .unwrap_or(0.0)
                .max(0.0);
        }
        if represented > 0.0 {
            total += represented;
            weighted.push(
                represented
                    * particle
                        .communities
                        .government_cooperation
                        .get(community)
                        .copied()
                        .unwrap_or(0.0),
            );
        }
    }
    if total <= 1.0e-12 {
        0.0
    } else {
        clamp01(python_sum(&weighted) / total)
    }
}

fn government_formation_count(particle: &ParticleState) -> usize {
    particle
        .formations
        .organization
        .iter()
        .filter(|organization| **organization as usize == crate::MILITARY)
        .count()
}

fn military_target_per_formation(particle: &ParticleState, config: &SimulationConfig) -> f64 {
    let count = government_formation_count(particle).max(1) as f64;
    config.force_structure.government_target_personnel
        * config.state_regeneration.military_target_multiplier
        / count
}

fn police_target(particle: &ParticleState, config: &SimulationConfig, locality: usize) -> f64 {
    (particle.locality.population[locality]
        * config.state_regeneration.police_target_population_fraction)
        .clamp(15.0, 300.0)
}

fn professional_standard(particle: &ParticleState, organization: usize) -> f64 {
    if organization >= particle.organizations.kind.len() {
        return 0.5;
    }
    clamp01(
        0.40 * particle.organizations.institutional_quality[organization]
            + 0.30 * particle.organizations.discipline[organization]
            + 0.30 * particle.organizations.accountability[organization],
    )
}

fn local_police_professionalism(particle: &ParticleState, locality: usize) -> f64 {
    let mut weighted = Vec::new();
    let mut total = 0.0;
    for post in 0..particle.security_posts.personnel.len() {
        if particle.security_posts.organization[post] as usize != crate::POLICE
            || particle.security_posts.locality[post] as usize != locality
            || particle.security_posts.staffed[post] == 0
        {
            continue;
        }
        let personnel = particle.security_posts.personnel[post].max(0.0);
        if personnel <= 0.0 {
            continue;
        }
        total += personnel;
        weighted.push(personnel * clamp01(particle.security_posts.professionalism[post]));
    }
    if total <= 1.0e-12 {
        0.0
    } else {
        clamp01(python_sum(&weighted) / total)
    }
}

fn local_force_status(
    particle: &ParticleState,
    config: &SimulationConfig,
    locality: usize,
) -> (f64, f64, f64, f64) {
    let police_target = police_target(particle, config, locality);
    let police_current = particle
        .security_posts
        .organization
        .iter()
        .enumerate()
        .filter(|(post, organization)| {
            **organization as usize == crate::POLICE
                && particle.security_posts.locality[*post] as usize == locality
                && particle.security_posts.staffed[*post] != 0
        })
        .map(|(post, _)| particle.security_posts.personnel[post].max(0.0))
        .sum::<f64>();

    let target_per_formation = military_target_per_formation(particle, config);
    let mut military_target = 0.0;
    let mut military_current = 0.0;
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.organization[formation] as usize != crate::MILITARY
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.locality[formation] as usize != locality
        {
            continue;
        }
        military_target += target_per_formation;
        military_current += particle.formations.personnel[formation].max(0.0);
    }
    (
        police_current,
        police_target,
        military_current,
        military_target,
    )
}

fn local_security_score(
    particle: &ParticleState,
    config: &SimulationConfig,
    locality: usize,
) -> f64 {
    let (police, police_target, military, military_target) =
        local_force_status(particle, config, locality);
    let police_fraction = clamp01(police / police_target.max(1.0));
    let police_professionalism = local_police_professionalism(particle, locality);
    // Headcount and professionalism are deliberately non-substitutable at
    // the extremes: an unstaffed professional unit has no local effect, while
    // a fully staffed but poorly institutionalized constabulary retains only
    // basic coercive/presence value.
    let effective_police = police_fraction * (0.35 + 0.65 * police_professionalism);
    let military_fraction = if military_target > 0.0 {
        clamp01(military / military_target)
    } else {
        0.0
    };
    // Police receives greater weight because it is continuously local and is
    // the main producer of the intelligence stock in this theory core.
    clamp01(0.65 * effective_police + 0.35 * military_fraction)
}

fn locality_institution_index(
    particle: &ParticleState,
    topology: &StaticTopology,
    locality: usize,
) -> Option<usize> {
    let expected = 6usize
        .saturating_add(topology.district_count())
        .saturating_add(locality);
    if expected < particle.political.institution_capacity.len()
        && particle
            .political
            .institution_locality
            .get(expected)
            .copied()
            == Some(locality as u32)
    {
        Some(expected)
    } else {
        particle
            .political
            .institution_locality
            .iter()
            .position(|candidate| *candidate == locality as u32)
    }
}

fn deploy_police(particle: &mut ParticleState, locality: usize, amount: f64) -> f64 {
    let mut remaining = amount.max(0.0);
    let mut deployed = 0.0;
    for post in 0..particle.security_posts.personnel.len() {
        if remaining <= 1.0e-12 {
            break;
        }
        if particle.security_posts.organization[post] as usize != crate::POLICE
            || particle.security_posts.locality[post] as usize != locality
        {
            continue;
        }
        let old_personnel = particle.security_posts.personnel[post].max(0.0);
        let old_professionalism = clamp01(particle.security_posts.professionalism[post]);
        let recruit_standard = professional_standard(particle, crate::POLICE);
        particle.security_posts.personnel[post] += remaining;
        let new_personnel = particle.security_posts.personnel[post].max(1.0e-12);
        particle.security_posts.professionalism[post] = clamp01(
            (old_personnel * old_professionalism + remaining * recruit_standard) / new_personnel,
        );
        particle.security_posts.presence[post] =
            clamp01(particle.security_posts.personnel[post] / 250.0);
        particle.security_posts.staffed[post] =
            u8::from(particle.security_posts.personnel[post] > 0.0);
        particle.security_posts.updated_at[post] = particle.time;
        deployed += remaining;
        remaining = 0.0;
    }
    deployed
}

fn deploy_military(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    locality: usize,
    amount: f64,
) -> f64 {
    let target = military_target_per_formation(particle, config);
    let mut candidates = Vec::new();
    let mut total_deficit = 0.0;
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.organization[formation] as usize != crate::MILITARY
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.locality[formation] as usize != locality
        {
            continue;
        }
        let deficit = (target - particle.formations.personnel[formation]).max(0.0);
        if deficit > 0.0 {
            candidates.push((formation, deficit));
            total_deficit += deficit;
        }
    }
    if total_deficit <= 1.0e-12 {
        return 0.0;
    }

    let deployable = amount.max(0.0).min(total_deficit);
    let mut deployed = 0.0;
    for (index, (formation, deficit)) in candidates.iter().copied().enumerate() {
        let share = if index + 1 == candidates.len() {
            (deployable - deployed).max(0.0)
        } else {
            deployable * deficit / total_deficit
        }
        .min(deficit);
        if share <= 0.0 {
            continue;
        }
        let old_personnel = particle.formations.personnel[formation].max(0.0);
        let old_experience = clamp01(particle.formations.experience[formation]);
        particle.formations.personnel[formation] += share;
        let new_personnel = particle.formations.personnel[formation].max(1.0e-12);
        // Graduates are trained but not veterans.  Replacement therefore
        // dilutes experience in proportion to turnover instead of magically
        // inheriting the unit's combat history.
        particle.formations.experience[formation] =
            clamp01((old_personnel * old_experience + share * 0.10) / new_personnel);
        particle.formations.active[formation] = 1;
        particle.formations.operational_status[formation] = 1;
        let added_capacity = share * config.logistics.formation_supply_days;
        particle.formations.supply_capacity[formation] += added_capacity;
        particle.formations.supply_stock[formation] +=
            added_capacity * config.logistics.initial_supply_fraction;
        deployed += share;

        // Keep the formation-linked fixed post consistent with the formation
        // source it represents.
        for post in 0..particle.security_posts.formation.len() {
            if particle.security_posts.formation[post] as usize == formation {
                particle.security_posts.personnel[post] = particle.formations.personnel[formation];
                particle.security_posts.presence[post] =
                    clamp01(particle.formations.personnel[formation] / 2_000.0);
                particle.security_posts.staffed[post] = 1;
                particle.security_posts.updated_at[post] = particle.time;
            }
        }
    }
    deployed
}

fn remove_unfielded_manpower(
    particle: &mut ParticleState,
    organization: usize,
    locality: usize,
    requested: f64,
) -> f64 {
    let mut remaining = requested.max(0.0);
    let mut removed = 0.0;
    for row in 0..particle.manpower.pool.len() {
        if remaining <= 1.0e-12 {
            break;
        }
        if particle.manpower.organization[row] as usize != organization
            || particle.manpower.locality[row] as usize != locality
        {
            continue;
        }
        let take = particle.manpower.pool[row].min(remaining);
        let ratio = if particle.manpower.pool[row] > 1.0e-12 {
            take / particle.manpower.pool[row]
        } else {
            0.0
        };
        particle.manpower.pool[row] -= take;
        particle.manpower.supply_reserve[row] *= 1.0 - ratio;
        removed += take;
        remaining -= take;
    }
    removed
}

fn disrupt_underground(
    particle: &mut ParticleState,
    config: &SimulationConfig,
    locality: usize,
    intelligence: f64,
    security: f64,
    elapsed_days: f64,
) -> f64 {
    if intelligence <= 0.0 || elapsed_days <= 0.0 {
        return 0.0;
    }
    let administrative = clamp01(particle.locality.administrative_capacity[locality]);
    let hazard = config.state_regeneration.underground_disruption_rate
        * intelligence
        * (0.35 + 0.65 * security)
        * (0.45 + 0.55 * administrative);
    let fraction_disrupted = clamp01(1.0 - python_exp(-hazard * elapsed_days));
    if fraction_disrupted <= 0.0 {
        return 0.0;
    }

    let organization_count = particle.organizations.kind.len();
    let mut total_removed = 0.0;
    let mut by_organization = vec![0.0; organization_count];
    for person in 0..particle.people.residence.len() {
        if particle.people.residence[person] as usize != locality {
            continue;
        }
        let organization = particle.people.organization[person] as usize;
        if organization >= organization_count
            || particle.organizations.kind[organization] != 3
            || particle.people.armed_fraction[person] <= 0.0
        {
            continue;
        }
        let prior = particle.people.armed_fraction[person];
        let removed_fraction = prior * fraction_disrupted;
        let remaining = (prior - removed_fraction).max(0.0);
        let represented_removed = particle.people.represented_population[person] * removed_fraction;
        total_removed += represented_removed;
        by_organization[organization] += represented_removed;

        particle.people.armed_fraction[person] = remaining;
        let retained_sympathy = prior * config.state_regeneration.disrupted_sympathy_retention;
        particle.people.rebel_sympathy[person] =
            particle.people.rebel_sympathy[person].max(retained_sympathy);
        let affinity_index = person * organization_count + organization;
        if affinity_index < particle.people.insurgent_affinity.len() {
            particle.people.insurgent_affinity[affinity_index] =
                particle.people.insurgent_affinity[affinity_index].max(retained_sympathy);
        }
        if remaining <= 1.0e-12 {
            particle.people.organization[person] = NO_ORGANIZATION;
            if particle.people.public_behavior[person] == 2 {
                particle.people.public_behavior[person] = 1;
            }
        }
    }

    for (organization, removed) in by_organization.into_iter().enumerate() {
        if removed <= 0.0 {
            continue;
        }
        particle.organizations.member_population[organization] =
            (particle.organizations.member_population[organization] - removed).max(0.0);
        // Intelligence-led disruption first removes the unfielded armed pool.
        // Already-fielded formations are deliberately left intact: this is the
        // theory's explicit separation between destroying the reproductive
        // underground (M) and destroying coercive capacity (F).
        let fighter_equivalent = removed * config.organization_ecology.fighter_conversion_fraction;
        let _ = remove_unfielded_manpower(particle, organization, locality, fighter_equivalent);
    }
    total_removed
}

/// Advance the endogenous state-capacity system by one scheduled interval.
pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
    elapsed_days: f64,
) -> StateRegenerationSummary {
    let mut summary = StateRegenerationSummary::default();
    if !config.state_regeneration.enabled || elapsed_days <= 0.0 {
        return summary;
    }
    particle.time = time;
    let government = crate::GOVERNMENT;
    let locality_count = topology.locality_count();

    for locality in 0..locality_count {
        let population = particle.locality.population[locality].max(1.0);
        let (state_legitimacy, government_legitimacy, political_access) =
            local_people_means(particle, locality);
        let legitimacy = clamp01(0.55 * state_legitimacy + 0.45 * government_legitimacy);

        // ---------- Police professionalism / institutional learning ----------
        // Professionalism is a local persistent stock, not a synonym for
        // headcount.  Posts converge toward their parent organization's
        // institutional standard at the same timescale as the security
        // training system; weak institutions can therefore sustain a large
        // but poorly professional force.
        for post in 0..particle.security_posts.personnel.len() {
            if particle.security_posts.locality[post] as usize != locality {
                continue;
            }
            let organization = particle.security_posts.organization[post] as usize;
            if !matches!(organization, crate::POLICE | crate::MILITARY) {
                continue;
            }
            let current = clamp01(particle.security_posts.professionalism[post]);
            let institutional = professional_standard(particle, organization);
            let target = clamp01(
                0.70 * institutional
                    + 0.15 * legitimacy
                    + 0.15 * particle.locality.administrative_capacity[locality],
            );
            let adjustment =
                1.0 - python_exp(-config.state_regeneration.security_training_rate * elapsed_days);
            particle.security_posts.professionalism[post] =
                clamp01(current + adjustment * (target - current));
        }

        // ---------- Security personnel reproduction ----------
        let (police_current, police_target, military_current, military_target) =
            local_force_status(particle, config, locality);
        let target_total = police_target + military_target;
        let police_deficit = (police_target - police_current).max(0.0);
        let military_deficit = (military_target - military_current).max(0.0);
        let pipeline = particle.locality.government_security_recruit_pipeline[locality];
        let reserve = particle.locality.government_security_reserve[locality];
        // Maintain a modest endogenous reserve in addition to filling current
        // vacancies so losses are not replaced instantaneously at the front.
        // Deficits remain role-specific here: a surplus army formation must
        // not erase demand for missing police (or vice versa).
        let desired_reserve = target_total * 0.10;
        let personnel_gap =
            (police_deficit + military_deficit + desired_reserve - pipeline - reserve).max(0.0);
        let recruit_gate = clamp01(0.20 + 0.50 * legitimacy + 0.30 * political_access);
        let desired_recruits = (population
            * config.state_regeneration.security_recruitment_rate
            * recruit_gate
            * elapsed_days)
            .min(personnel_gap);
        let affordable_recruits = if config.state_regeneration.training_cost_per_person > 0.0 {
            particle.organizations.capital[government]
                / config.state_regeneration.training_cost_per_person
        } else {
            desired_recruits
        };
        let recruits = desired_recruits.min(affordable_recruits.max(0.0));
        if recruits > 0.0 {
            particle.organizations.capital[government] = (particle.organizations.capital
                [government]
                - recruits * config.state_regeneration.training_cost_per_person)
                .max(0.0);
            particle.locality.government_security_recruit_pipeline[locality] += recruits;
            particle.locality.government_cumulative_security_recruits[locality] += recruits;
            summary.recruited += recruits;
        }

        let graduation_fraction = clamp01(
            1.0 - python_exp(-config.state_regeneration.security_training_rate * elapsed_days),
        );
        let graduated =
            particle.locality.government_security_recruit_pipeline[locality] * graduation_fraction;
        particle.locality.government_security_recruit_pipeline[locality] -= graduated;
        particle.locality.government_security_reserve[locality] += graduated;
        summary.graduated += graduated;

        let reserve_survival =
            python_exp(-config.state_regeneration.reserve_attrition_rate.max(0.0) * elapsed_days);
        particle.locality.government_security_reserve[locality] *= reserve_survival;

        let (police_current, police_target, military_current, military_target) =
            local_force_status(particle, config, locality);
        let police_deficit = (police_target - police_current).max(0.0);
        let military_deficit = (military_target - military_current).max(0.0);
        let reserve_available = particle.locality.government_security_reserve[locality];
        let affordable_deployment = if config.state_regeneration.deployment_cost_per_person > 0.0 {
            particle.organizations.capital[government]
                / config.state_regeneration.deployment_cost_per_person
        } else {
            reserve_available
        };
        let deployable = reserve_available
            .min(affordable_deployment.max(0.0))
            .min(police_deficit + military_deficit);
        if deployable > 0.0 {
            let police_weight = police_deficit * config.state_regeneration.police_allocation_share;
            let military_weight =
                military_deficit * (1.0 - config.state_regeneration.police_allocation_share);
            let weight_total = police_weight + military_weight;
            let mut police_budget = if weight_total > 1.0e-12 {
                deployable * police_weight / weight_total
            } else {
                0.0
            }
            .min(police_deficit);
            let mut military_budget = (deployable - police_budget).min(military_deficit);
            let mut leftover = deployable - police_budget - military_budget;
            if leftover > 1.0e-12 && police_budget < police_deficit {
                let extra = leftover.min(police_deficit - police_budget);
                police_budget += extra;
                leftover -= extra;
            }
            if leftover > 1.0e-12 && military_budget < military_deficit {
                let extra = leftover.min(military_deficit - military_budget);
                military_budget += extra;
            }

            let deployed_police = deploy_police(particle, locality, police_budget);
            let deployed_military = deploy_military(particle, config, locality, military_budget);
            let deployed = deployed_police + deployed_military;
            particle.locality.government_security_reserve[locality] =
                (particle.locality.government_security_reserve[locality] - deployed).max(0.0);
            particle.organizations.capital[government] = (particle.organizations.capital
                [government]
                - deployed * config.state_regeneration.deployment_cost_per_person)
                .max(0.0);
            particle.locality.government_cumulative_security_deployments[locality] += deployed;
            summary.deployed_police += deployed_police;
            summary.deployed_military += deployed_military;
        }

        // ---------- Administrative reproduction / rebuilding ----------
        let security = local_security_score(particle, config, locality);
        let institution = locality_institution_index(particle, topology, locality);
        let integrity = institution
            .and_then(|index| particle.political.institution_integrity.get(index).copied())
            .map(clamp01)
            .unwrap_or(0.5);
        let absorptive = clamp01(
            config.state_regeneration.rebuild_security_weight * security
                + config.state_regeneration.rebuild_integrity_weight * integrity
                + config.state_regeneration.rebuild_legitimacy_weight * legitimacy,
        );
        let ceiling = topology
            .locality_administrative_capacity
            .get(locality)
            .copied()
            .unwrap_or(1.0)
            .clamp(0.0, 1.0);
        let current_admin = clamp01(particle.locality.administrative_capacity[locality]);
        let insurgent_pressure = particle.locality.effective_control(locality, 1);
        let desired_gain = (ceiling - current_admin).max(0.0)
            * (1.0
                - python_exp(
                    -config.state_regeneration.administrative_rebuild_rate
                        * absorptive
                        * (1.0 - 0.65 * insurgent_pressure)
                        * elapsed_days,
                ));
        let unit_cost = population * config.state_regeneration.administrative_rebuild_cost;
        let affordable_gain = if unit_cost > 0.0 {
            particle.organizations.capital[government] / unit_cost
        } else {
            desired_gain
        };
        let gain = desired_gain.min(affordable_gain.max(0.0));
        let decay = current_admin
            * (1.0
                - python_exp(
                    -config.state_regeneration.administrative_decay_rate
                        * insurgent_pressure
                        * elapsed_days,
                ));
        if gain > 0.0 {
            particle.organizations.capital[government] =
                (particle.organizations.capital[government] - gain * unit_cost).max(0.0);
        }
        particle.locality.administrative_capacity[locality] =
            (current_admin + gain - decay).clamp(0.0, ceiling.max(current_admin));
        particle.locality.government_cumulative_admin_rebuild[locality] += gain;
        summary.administrative_rebuild += gain;
        if let Some(index) = institution {
            let institutional_gain = gain * integrity;
            let institutional_decay = decay * 0.5;
            particle.political.institution_capacity[index] = clamp01(
                particle.political.institution_capacity[index] + institutional_gain
                    - institutional_decay,
            );
        }

        // ---------- Intelligence penetration ----------
        let cooperation = local_public_cooperation(particle, locality);
        let admin = clamp01(particle.locality.administrative_capacity[locality]);
        let intelligence_target = clamp01(
            config.state_regeneration.intelligence_police_weight * security
                + config.state_regeneration.intelligence_cooperation_weight * cooperation
                + config.state_regeneration.intelligence_administration_weight * admin,
        );
        let current_intelligence =
            clamp01(particle.locality.government_intelligence_penetration[locality]);
        let gain_rate = config.state_regeneration.intelligence_gain_rate * intelligence_target;
        let decay_rate =
            config.state_regeneration.intelligence_decay_rate * (0.35 + 0.65 * insurgent_pressure);
        let total_rate = gain_rate + decay_rate;
        let next_intelligence = if total_rate > 0.0 {
            let equilibrium = gain_rate / total_rate;
            clamp01(
                equilibrium
                    + (current_intelligence - equilibrium) * python_exp(-total_rate * elapsed_days),
            )
        } else {
            current_intelligence
        };
        particle.locality.government_intelligence_penetration[locality] = next_intelligence;

        let disrupted = disrupt_underground(
            particle,
            config,
            locality,
            next_intelligence,
            security,
            elapsed_days,
        );
        particle
            .locality
            .government_cumulative_underground_disruption[locality] += disrupted;
        summary.underground_disrupted += disrupted;

        // Feed the persistent intelligence institution back into the existing
        // security-post information architecture rather than maintaining two
        // unrelated detection systems.
        for post in 0..particle.security_posts.locality.len() {
            if particle.security_posts.locality[post] as usize != locality
                || !matches!(
                    particle.security_posts.organization[post] as usize,
                    crate::POLICE | crate::MILITARY
                )
            {
                continue;
            }
            let existing = clamp01(particle.security_posts.reliability[post]);
            let professionalism = clamp01(particle.security_posts.professionalism[post]);
            particle.security_posts.reliability[post] =
                clamp01(existing + 0.10 * next_intelligence * professionalism * (1.0 - existing));
        }

        // The state-side mechanism acts through existing downstream control
        // processes.  We deliberately do not grant control directly here.
        // Security regeneration changes physical presence; administration
        // changes governance production; intelligence attacks M.  Those
        // pathways subsequently change the seven-dimensional control vector.
    }

    summary
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{SimulationEngine, INSURGENT, MILITARY, POLICE};
    use pineland_core::rng::PyRandomCompat;

    fn small_config() -> SimulationConfig {
        let mut config = SimulationConfig::default();
        config.seed = 2026091019;
        config.initialization_seed = Some(2026091019);
        config.agent_count = 300;
        config.locality_count = 17;
        config.horizon_days = 60.0;
        config.output_mode = "ensemble".to_string();
        config
    }

    #[test]
    fn disabled_process_is_exact_noop() {
        let config = small_config();
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        let before = engine.particle.clone();
        let summary = update(&mut engine.particle, &engine.topology, &config, 14.0, 14.0);
        assert_eq!(summary, StateRegenerationSummary::default());
        assert_eq!(engine.particle, before);
    }

    #[test]
    fn security_recruitment_flows_through_training_before_replacement() {
        let mut config = small_config();
        config.state_regeneration.enabled = true;
        config.state_regeneration.security_recruitment_rate = 5.0e-5;
        config.state_regeneration.security_training_rate = 1.0;
        config.state_regeneration.reserve_attrition_rate = 0.0;
        config.state_regeneration.training_cost_per_person = 0.0;
        config.state_regeneration.deployment_cost_per_person = 0.0;
        config.state_regeneration.military_target_multiplier = 0.0;
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        engine.particle.organizations.capital[crate::GOVERNMENT] = 1.0e9;
        let locality = 0usize;
        let post = engine
            .particle
            .security_posts
            .organization
            .iter()
            .enumerate()
            .find(|(post, org)| {
                **org as usize == POLICE
                    && engine.particle.security_posts.locality[*post] as usize == locality
            })
            .map(|(post, _)| post)
            .expect("police post");
        engine.particle.security_posts.personnel[post] = 0.0;
        engine.particle.security_posts.presence[post] = 0.0;

        let summary = update(&mut engine.particle, &engine.topology, &config, 14.0, 14.0);
        assert!(summary.recruited > 0.0);
        assert!(summary.graduated > 0.0);
        assert!(summary.deployed_police > 0.0);
        assert!(engine.particle.security_posts.personnel[post] > 0.0);
        assert!(
            engine
                .particle
                .locality
                .government_cumulative_security_recruits[locality]
                > 0.0
        );
        assert!(
            engine
                .particle
                .locality
                .government_cumulative_security_deployments[locality]
                > 0.0
        );
    }

    #[test]
    fn administrative_capacity_rebuilds_toward_static_ceiling() {
        let mut config = small_config();
        config.state_regeneration.enabled = true;
        config.state_regeneration.security_recruitment_rate = 0.0;
        config.state_regeneration.administrative_rebuild_rate = 0.25;
        config.state_regeneration.administrative_decay_rate = 0.0;
        config.state_regeneration.administrative_rebuild_cost = 0.0;
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        engine.particle.organizations.capital[crate::GOVERNMENT] = 1.0e9;
        let locality = 0usize;
        let ceiling = engine.topology.locality_administrative_capacity[locality];
        assert!(ceiling > 0.0);
        engine.particle.locality.administrative_capacity[locality] = 0.0;

        let summary = update(&mut engine.particle, &engine.topology, &config, 30.0, 30.0);
        let rebuilt = engine.particle.locality.administrative_capacity[locality];
        assert!(summary.administrative_rebuild > 0.0);
        assert!(rebuilt > 0.0);
        assert!(rebuilt <= ceiling + 1.0e-12);
    }

    #[test]
    fn intelligence_disrupts_rooted_membership_without_erasing_fielded_force() {
        let mut config = small_config();
        config.state_regeneration.enabled = true;
        config.state_regeneration.security_recruitment_rate = 0.0;
        config.state_regeneration.intelligence_gain_rate = 1.0;
        config.state_regeneration.intelligence_decay_rate = 0.0;
        config.state_regeneration.underground_disruption_rate = 1.0;
        config.state_regeneration.administrative_rebuild_rate = 0.0;
        config.state_regeneration.administrative_decay_rate = 0.0;
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        let locality = 0usize;
        let person = engine
            .particle
            .people
            .residence
            .iter()
            .position(|residence| *residence as usize == locality)
            .expect("resident");
        engine.particle.people.organization[person] = INSURGENT as u32;
        engine.particle.people.armed_fraction[person] = 1.0;
        let represented = engine.particle.people.represented_population[person];
        engine.particle.organizations.member_population[INSURGENT] += represented;
        let affinity = person * engine.particle.organizations.kind.len() + INSURGENT;
        engine.particle.people.insurgent_affinity[affinity] = 1.0;
        engine.particle.locality.government_intelligence_penetration[locality] = 1.0;
        let fielded_before = engine
            .particle
            .formations
            .organization
            .iter()
            .enumerate()
            .filter(|(_, organization)| **organization as usize == INSURGENT)
            .map(|(formation, _)| engine.particle.formations.personnel[formation])
            .sum::<f64>();

        let summary = update(&mut engine.particle, &engine.topology, &config, 14.0, 14.0);
        let fielded_after = engine
            .particle
            .formations
            .organization
            .iter()
            .enumerate()
            .filter(|(_, organization)| **organization as usize == INSURGENT)
            .map(|(formation, _)| engine.particle.formations.personnel[formation])
            .sum::<f64>();
        assert!(summary.underground_disrupted > 0.0);
        assert!(engine.particle.people.armed_fraction[person] < 1.0);
        assert_eq!(fielded_before.to_bits(), fielded_after.to_bits());
    }

    #[test]
    fn police_professionalism_changes_effective_security_at_equal_headcount() {
        let mut config = small_config();
        config.state_regeneration.enabled = true;
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        let post = engine
            .particle
            .security_posts
            .organization
            .iter()
            .enumerate()
            .find(|(_, organization)| **organization as usize == POLICE)
            .map(|(index, _)| index)
            .expect("police post");
        let locality = engine.particle.security_posts.locality[post] as usize;
        engine.particle.security_posts.professionalism[post] = 0.05;
        let low = local_security_score(&engine.particle, &config, locality);
        engine.particle.security_posts.professionalism[post] = 0.95;
        let high = local_security_score(&engine.particle, &config, locality);
        assert!(
            high > low,
            "professionalism must matter independently of headcount"
        );
    }

    #[test]
    fn inexperienced_replacements_dilute_military_veterancy() {
        let mut config = small_config();
        config.state_regeneration.enabled = true;
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        let formation = engine
            .particle
            .formations
            .organization
            .iter()
            .enumerate()
            .find(|(_, organization)| **organization as usize == MILITARY)
            .map(|(index, _)| index)
            .expect("military formation");
        let locality = engine.particle.formations.locality[formation] as usize;
        let target = military_target_per_formation(&engine.particle, &config);
        engine.particle.formations.personnel[formation] = (target - 100.0).max(1.0);
        engine.particle.formations.experience[formation] = 0.90;
        let before = engine.particle.formations.experience[formation];
        let deployed = deploy_military(&mut engine.particle, &config, locality, 100.0);
        assert!(deployed > 0.0);
        let after = engine.particle.formations.experience[formation];
        assert!(after < before);
        assert!(after > 0.10);
    }

    #[test]
    fn combat_builds_experience_for_both_sides() {
        let mut config = small_config();
        config.state_regeneration.enabled = true;
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        let first = engine
            .particle
            .formations
            .organization
            .iter()
            .position(|organization| *organization as usize == MILITARY)
            .expect("military formation");
        let second = engine
            .particle
            .formations
            .organization
            .iter()
            .position(|organization| *organization as usize == INSURGENT)
            .expect("insurgent formation");
        engine.particle.formations.locality[second] = engine.particle.formations.locality[first];
        engine.particle.formations.microzone[second] = engine.particle.formations.microzone[first];
        engine.particle.formations.personnel[first] = 300.0;
        engine.particle.formations.personnel[second] = 300.0;
        engine.particle.formations.supply_capacity[first] = 10_000.0;
        engine.particle.formations.supply_capacity[second] = 10_000.0;
        engine.particle.formations.supply_stock[first] = 10_000.0;
        engine.particle.formations.supply_stock[second] = 10_000.0;
        engine.particle.formations.experience[first] = 0.20;
        engine.particle.formations.experience[second] = 0.20;
        let mut rng = PyRandomCompat::from_seed(20260910);
        crate::combat::resolve_organized_engagement(
            &mut engine.particle,
            &engine.topology,
            &config,
            &mut rng,
            1.0,
            first,
            second,
            MILITARY,
            true,
        );
        assert!(engine.particle.formations.experience[first] > 0.20);
        assert!(engine.particle.formations.experience[second] > 0.20);
    }

    #[test]
    fn insurgent_recruit_inflow_dilutes_veterancy_too() {
        let mut config = small_config();
        config.state_regeneration.enabled = true;
        let mut engine = SimulationEngine::new(config.clone()).expect("engine");
        let formation = engine
            .particle
            .formations
            .organization
            .iter()
            .position(|organization| *organization as usize == INSURGENT)
            .expect("insurgent formation");
        let locality = engine.particle.formations.locality[formation] as usize;
        engine.particle.formations.experience[formation] = 0.90;
        engine.particle.organizations.capital[INSURGENT] = 1.0e9;
        let before = engine.particle.formations.experience[formation];
        let (added, _) = crate::recruitment::apply_local_fighter_change(
            &mut engine.particle,
            &engine.topology,
            &config,
            INSURGENT,
            locality,
            100.0,
        );
        assert!(added > 0.0);
        let after = engine.particle.formations.experience[formation];
        assert!(after < before);
        assert!(after > 0.10);
    }
}
