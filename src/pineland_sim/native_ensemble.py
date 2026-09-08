"""Authoritative packed execution islands for Pineland particle ensembles.

The reference simulation engine remains the scientific oracle. This module owns
the mutable structure-of-arrays representation used by the ensemble engine. It
never calls Simulation.run or SimulationParticle.advance_to: non-migrated
processes are explicit sparse boundaries instead of hidden fallbacks.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from math import exp, expm1, inf
from typing import Any, Callable, Sequence, TYPE_CHECKING

from .entities import OrganizationKind, clamp

if TYPE_CHECKING:
    from .ensemble import ParticleBatchState, StaticWorldTopology


UINT32_MISSING = (1 << 32) - 1
GOVERNMENT_SIDE = 1
INSURGENT_SIDE = 2
OTHER_SIDE = 0

HOT_CLOCKS = (
    "physical_refresh",
    "action_opportunity",
    "information",
    "force_movement",
    "logistics",
)


def _particle_world(particle: Any) -> Any:
    world = getattr(particle, "world", None)
    if world is not None:
        return world
    state = getattr(particle, "state", None)
    world = getattr(state, "world", None)
    if world is not None:
        return world
    raise TypeError("particle must expose .world or .state.world")


def _particle_simulation(particle: Any) -> Any | None:
    simulation = getattr(particle, "simulation", None)
    if simulation is not None:
        return simulation
    state = getattr(particle, "state", None)
    return getattr(state, "simulation", None)


def _gather_blocks(values: array, block: int, parents: Sequence[int]) -> array:
    result = array(values.typecode)
    for parent in parents:
        start = int(parent) * int(block)
        result.extend(values[start:start + int(block)])
    return result


def _kind_code(kind: OrganizationKind) -> int:
    if kind is OrganizationKind.INSURGENT:
        return INSURGENT_SIDE
    if kind in {
        OrganizationKind.GOVERNMENT,
        OrganizationKind.MILITARY,
        OrganizationKind.POLICE,
        OrganizationKind.FOREIGN,
    }:
        return GOVERNMENT_SIDE
    return OTHER_SIDE


def _first_pending_clock(simulation: Any | None, event_type: str) -> float | None:
    if simulation is None or not getattr(simulation, "_initialized", False):
        return None
    pending = getattr(getattr(simulation, "scheduler", None), "pending_events", None)
    if not callable(pending):
        return None
    values = [
        float(event.time) for event in pending()
        if event.event_type == event_type
    ]
    return min(values) if values else None


@dataclass(slots=True)
class PackedHotState:
    """Particle-leading mutable hot state."""

    particle_count: int
    formation_ids: tuple[str, ...]
    organization_ids: tuple[str, ...]
    patrol_ids: tuple[str, ...]
    post_ids: tuple[str, ...]
    supply_source_ids: tuple[str, ...]
    formation_index: dict[str, int]
    organization_index: dict[str, int]
    patrol_index: dict[str, int]
    post_index: dict[str, int]
    supply_source_index: dict[str, int]
    locality_ids: tuple[str, ...]
    microzone_ids: tuple[str, ...]

    organization_present: array
    organization_active: array
    organization_kind: array
    organization_government_side: array
    organization_action_eligible: array
    formation_present: array
    formation_organization: array
    formation_locality: array
    formation_microzone: array
    formation_values: array
    formation_flags: array
    manpower_pool: array
    manpower_supply_reserve: array
    supply_source_present: array
    supply_source_organization: array
    supply_source_locality: array
    supply_source_stock: array
    post_present: array
    post_values: array
    post_indices: array
    patrol_present: array
    patrol_values: array
    patrol_indices: array
    zone_presence_memory: array
    zone_presence_updated_at: array
    zone_physical_control: array
    zone_insurgent_side_raw: array
    zone_org_presence_memory: array
    zone_org_presence_updated_at: array
    zone_org_physical_control: array
    locality_population: array
    zone_population_share: array
    config_values: array
    next_clocks: dict[str, array]
    clock_intervals: dict[str, array]
    rng_states: dict[str, tuple[tuple[Any, ...] | None, ...]] = field(
        default_factory=dict
    )
    dirty_lanes: set[int] = field(default_factory=set, repr=False)

    F_PERSONNEL = 0
    F_QUALITY = 1
    F_COHESION = 2
    F_READINESS = 3
    F_SUSTAINMENT = 4
    F_INFORMATION = 5
    F_COMMAND = 6
    F_FATIGUE = 7
    F_AVAILABILITY = 8
    F_SUPPLY_STOCK = 9
    F_SUPPLY_CAPACITY = 10
    F_STRIDE = 11

    FF_MOVING = 0
    FF_OUTSIDE = 1
    FF_EFFECTIVE = 2
    FF_STRIDE = 3

    POST_FIXED = 0
    POST_AVAILABLE = 1
    POST_STRIDE = 2
    POST_ORG = 0
    POST_LOCALITY = 1
    POST_ZONE = 2
    POST_FORMATION = 3
    POST_INDEX_STRIDE = 4

    PATROL_AVAILABLE_AT = 0
    PATROL_RESPONSE = 1
    PATROL_ACCOUNTED_AT = 2
    PATROL_STRIDE = 3
    PATROL_FORMATION = 0
    PATROL_ORG = 1
    PATROL_LOCALITY = 2
    PATROL_ZONE = 3
    PATROL_INDEX_STRIDE = 4

    C_ACTION_RATE = 0
    C_MIN_FORMATION = 1
    C_SUPPLY_PER_FIGHTER = 2
    C_PRESENCE_TAU = 3
    C_PATROL_GAIN = 4
    C_FORMATION_GAIN = 5
    C_POST_GAIN = 6
    C_RESPONSE_DECAY = 7
    C_STRIDE = 8

    @property
    def formation_count(self) -> int:
        return len(self.formation_ids)

    @property
    def organization_count(self) -> int:
        return len(self.organization_ids)

    @property
    def locality_count(self) -> int:
        return len(self.locality_ids)

    @property
    def microzone_count(self) -> int:
        return len(self.microzone_ids)

    def _fo(self, lane: int, formation: int) -> int:
        return lane * self.formation_count + formation

    def _oo(self, lane: int, organization: int) -> int:
        return lane * self.organization_count + organization

    def _fv(self, lane: int, formation: int, field_index: int) -> int:
        return self._fo(lane, formation) * self.F_STRIDE + field_index

    def _ff(self, lane: int, formation: int, field_index: int) -> int:
        return self._fo(lane, formation) * self.FF_STRIDE + field_index

    def _ol(self, lane: int, organization: int, locality: int) -> int:
        return (
            (lane * self.organization_count + organization) * self.locality_count
            + locality
        )

    def _zs(self, lane: int, zone: int, side_slot: int) -> int:
        return (lane * self.microzone_count + zone) * 2 + side_slot

    def _zo(self, lane: int, zone: int, organization: int) -> int:
        return (
            (lane * self.microzone_count + zone) * self.organization_count
            + organization
        )

    def _cfg(self, lane: int, field_index: int) -> float:
        return float(self.config_values[lane * self.C_STRIDE + field_index])

    def _lp(self, lane: int, locality: int) -> float:
        return float(
            self.locality_population[
                lane * self.locality_count + locality
            ]
        )

    @classmethod
    def from_particles(
        cls, particles: Sequence[Any], topology: "StaticWorldTopology"
    ) -> "PackedHotState":
        worlds = [_particle_world(item) for item in particles]
        if not worlds:
            raise ValueError("PackedHotState needs at least one particle")
        p = len(worlds)
        formation_ids = tuple(sorted({
            key for world in worlds for key in world.formations
        }))
        organization_ids = tuple(sorted({
            key for world in worlds for key in world.organizations
        }))
        patrol_ids = tuple(sorted({
            key for world in worlds for key in world.patrols
        }))
        post_ids = tuple(sorted({
            key for world in worlds for key in world.security_posts
        }))
        source_ids = tuple(sorted({
            key for world in worlds for key in world.supply_sources
        }))
        f, o = len(formation_ids), len(organization_ids)
        l, z = len(topology.locality_ids), len(topology.microzone_ids)
        k, r, s = len(patrol_ids), len(post_ids), len(source_ids)
        result = cls(
            particle_count=p,
            formation_ids=formation_ids,
            organization_ids=organization_ids,
            patrol_ids=patrol_ids,
            post_ids=post_ids,
            supply_source_ids=source_ids,
            formation_index={key: i for i, key in enumerate(formation_ids)},
            organization_index={key: i for i, key in enumerate(organization_ids)},
            patrol_index={key: i for i, key in enumerate(patrol_ids)},
            post_index={key: i for i, key in enumerate(post_ids)},
            supply_source_index={key: i for i, key in enumerate(source_ids)},
            locality_ids=tuple(topology.locality_ids),
            microzone_ids=tuple(topology.microzone_ids),
            organization_present=array("B", [0]) * (p * o),
            organization_active=array("B", [0]) * (p * o),
            organization_kind=array("B", [0]) * (p * o),
            organization_government_side=array("B", [0]) * (p * o),
            organization_action_eligible=array("B", [0]) * (p * o),
            formation_present=array("B", [0]) * (p * f),
            formation_organization=array("I", [UINT32_MISSING]) * (p * f),
            formation_locality=array("I", [UINT32_MISSING]) * (p * f),
            formation_microzone=array("I", [UINT32_MISSING]) * (p * f),
            formation_values=array("d", [0.0]) * (p * f * cls.F_STRIDE),
            formation_flags=array("B", [0]) * (p * f * cls.FF_STRIDE),
            manpower_pool=array("d", [0.0]) * (p * o * l),
            manpower_supply_reserve=array("d", [0.0]) * (p * o * l),
            supply_source_present=array("B", [0]) * (p * s),
            supply_source_organization=array("I", [UINT32_MISSING]) * (p * s),
            supply_source_locality=array("I", [UINT32_MISSING]) * (p * s),
            supply_source_stock=array("d", [0.0]) * (p * s),
            post_present=array("B", [0]) * (p * r),
            post_values=array("d", [0.0]) * (p * r * cls.POST_STRIDE),
            post_indices=array("I", [UINT32_MISSING]) * (
                p * r * cls.POST_INDEX_STRIDE
            ),
            patrol_present=array("B", [0]) * (p * k),
            patrol_values=array("d", [0.0]) * (p * k * cls.PATROL_STRIDE),
            patrol_indices=array("I", [UINT32_MISSING]) * (
                p * k * cls.PATROL_INDEX_STRIDE
            ),
            zone_presence_memory=array("d", [0.0]) * (p * z * 2),
            zone_presence_updated_at=array("d", [0.0]) * (p * z * 2),
            zone_physical_control=array("d", [0.0]) * (p * z * 2),
            zone_insurgent_side_raw=array("d", [0.0]) * (p * z),
            zone_org_presence_memory=array("d", [0.0]) * (p * z * o),
            zone_org_presence_updated_at=array("d", [0.0]) * (p * z * o),
            zone_org_physical_control=array("d", [0.0]) * (p * z * o),
            locality_population=array(
                "d",
                (
                    float(world.localities[key].population)
                    for world in worlds
                    for key in topology.locality_ids
                ),
            ),
            zone_population_share=array(
                "d",
                (float(worlds[0].microzones[key].population_share)
                 for key in topology.microzone_ids),
            ),
            config_values=array("d", [0.0]) * (p * cls.C_STRIDE),
            next_clocks={name: array("d", [inf]) * p for name in HOT_CLOCKS},
            clock_intervals={name: array("d", [inf]) * p for name in HOT_CLOCKS},
        )
        for lane, (particle, world) in enumerate(zip(particles, worlds)):
            result.import_lane(lane, world, topology)
            result._import_clocks_and_rng(lane, particle, world)
        return result

    def _import_clocks_and_rng(self, lane: int, particle: Any, world: Any) -> None:
        simulation = _particle_simulation(particle)
        intervals = world.config.intervals
        mapping = {
            "physical_refresh": float(intervals.physical_refresh),
            "action_opportunity": float(intervals.contact),
            "information": float(intervals.information),
            "force_movement": float(intervals.force_movement),
            "logistics": float(intervals.logistics),
        }
        for name, interval in mapping.items():
            self.clock_intervals[name][lane] = interval
            event_name = "contact_scan" if name == "action_opportunity" else name
            pending = _first_pending_clock(simulation, event_name)
            self.next_clocks[name][lane] = (
                float(world.time) if pending is None else float(pending)
            )
        process_engine = getattr(simulation, "processes", None)
        process_rngs = getattr(process_engine, "_process_rngs", {}) or {}
        for name in ("information", "organized_action"):
            states = list(self.rng_states.get(name, (None,) * self.particle_count))
            rng = process_rngs.get(name)
            states[lane] = rng.getstate() if rng is not None else None
            self.rng_states[name] = tuple(states)

    def import_lane(
        self, lane: int, world: Any, topology: "StaticWorldTopology"
    ) -> None:
        """Refresh only migrated state from one Python view."""
        from .physical import _actor_matches_organization

        for organization_id, oi in self.organization_index.items():
            offset = self._oo(lane, oi)
            organization = world.organizations.get(organization_id)
            if organization is None:
                self.organization_present[offset] = 0
                self.organization_active[offset] = 0
                continue
            self.organization_present[offset] = 1
            self.organization_active[offset] = int(organization.status == "active")
            self.organization_kind[offset] = _kind_code(organization.kind)
            self.organization_government_side[offset] = int(
                _actor_matches_organization(world, organization_id, "government")
            )
            self.organization_action_eligible[offset] = int(
                organization.kind in {
                    OrganizationKind.INSURGENT,
                    OrganizationKind.MILITARY,
                    OrganizationKind.POLICE,
                    OrganizationKind.FOREIGN,
                }
            )
        for formation_id, fi in self.formation_index.items():
            offset = self._fo(lane, fi)
            formation = world.formations.get(formation_id)
            if formation is None:
                self.formation_present[offset] = 0
                continue
            self.formation_present[offset] = 1
            self.formation_organization[offset] = self.organization_index.get(
                formation.organization_id, UINT32_MISSING
            )
            self.formation_locality[offset] = topology.locality_index.get(
                formation.locality_id, UINT32_MISSING
            )
            self.formation_microzone[offset] = topology.microzone_index.get(
                formation.current_microzone_id, UINT32_MISSING
            )
            values = (
                formation.personnel, formation.quality, formation.cohesion,
                formation.readiness, formation.sustainment, formation.information,
                formation.command, formation.fatigue, formation.availability,
                formation.supply_stock, formation.supply_capacity,
            )
            for field_index, value in enumerate(values):
                self.formation_values[self._fv(lane, fi, field_index)] = float(value)
            self.formation_flags[self._ff(lane, fi, self.FF_MOVING)] = int(
                formation.moving
            )
            self.formation_flags[self._ff(lane, fi, self.FF_OUTSIDE)] = int(
                formation.outside_pineland
            )
            self.formation_flags[self._ff(lane, fi, self.FF_EFFECTIVE)] = int(
                formation.operational_status == "effective"
            )
        for organization_id, oi in self.organization_index.items():
            for locality_id, li in topology.locality_index.items():
                key = (organization_id, locality_id)
                offset = self._ol(lane, oi, li)
                self.manpower_pool[offset] = max(
                    0.0, float(world.organization_manpower_pools.get(key, 0.0))
                )
                self.manpower_supply_reserve[offset] = max(
                    0.0,
                    float(world.organization_manpower_supply_reserves.get(key, 0.0)),
                )
        for locality_id, li in topology.locality_index.items():
            self.locality_population[
                lane * self.locality_count + li
            ] = float(world.localities[locality_id].population)
        self._import_supply_posts_patrols(lane, world, topology)
        self._import_zone_state(lane, world, topology)
        cfg = world.config
        config = (
            cfg.organized_action_rate,
            cfg.organization_ecology.minimum_formation_personnel,
            cfg.logistics.formation_supply_days * cfg.logistics.initial_supply_fraction,
            cfg.physical.presence_memory_days,
            cfg.physical.patrol_memory_gain,
            cfg.physical.formation_presence_gain,
            cfg.physical.fixed_post_presence_gain,
            cfg.physical.response_decay_hours,
        )
        for field_index, value in enumerate(config):
            self.config_values[lane * self.C_STRIDE + field_index] = max(
                1e-12 if field_index in {1, 2, 3, 7} else 0.0,
                float(value),
            )
        self.dirty_lanes.discard(lane)

    def _import_supply_posts_patrols(
        self, lane: int, world: Any, topology: "StaticWorldTopology"
    ) -> None:
        for source_id, si in self.supply_source_index.items():
            base = lane * len(self.supply_source_ids) + si
            source = world.supply_sources.get(source_id)
            if source is None:
                self.supply_source_present[base] = 0
                continue
            self.supply_source_present[base] = 1
            self.supply_source_organization[base] = self.organization_index.get(
                source.organization_id, UINT32_MISSING
            )
            self.supply_source_locality[base] = topology.locality_index.get(
                source.locality_id, UINT32_MISSING
            )
            self.supply_source_stock[base] = float(source.stock)

        for post_id, pi in self.post_index.items():
            base = lane * len(self.post_ids) + pi
            post = world.security_posts.get(post_id)
            if post is None:
                self.post_present[base] = 0
                continue
            self.post_present[base] = 1
            vbase = base * self.POST_STRIDE
            ibase = base * self.POST_INDEX_STRIDE
            self.post_values[vbase + self.POST_FIXED] = float(post.fixed_presence)
            self.post_values[vbase + self.POST_AVAILABLE] = float(
                post.available_fraction
            )
            self.post_indices[ibase + self.POST_ORG] = self.organization_index.get(
                post.organization_id, UINT32_MISSING
            )
            self.post_indices[ibase + self.POST_LOCALITY] = topology.locality_index.get(
                post.locality_id, UINT32_MISSING
            )
            self.post_indices[ibase + self.POST_ZONE] = topology.microzone_index.get(
                post.microzone_id, UINT32_MISSING
            )
            self.post_indices[ibase + self.POST_FORMATION] = self.formation_index.get(
                post.formation_id, UINT32_MISSING
            )

        for patrol_id, pi in self.patrol_index.items():
            base = lane * len(self.patrol_ids) + pi
            patrol = world.patrols.get(patrol_id)
            if patrol is None:
                self.patrol_present[base] = 0
                continue
            self.patrol_present[base] = 1
            vbase = base * self.PATROL_STRIDE
            ibase = base * self.PATROL_INDEX_STRIDE
            self.patrol_values[vbase + self.PATROL_AVAILABLE_AT] = float(
                patrol.available_at
            )
            self.patrol_values[vbase + self.PATROL_RESPONSE] = float(
                patrol.response_fraction
            )
            self.patrol_values[vbase + self.PATROL_ACCOUNTED_AT] = (
                float(patrol.presence_accounted_at)
                if patrol.presence_accounted_at is not None else -1e300
            )
            self.patrol_indices[ibase + self.PATROL_FORMATION] = self.formation_index.get(
                patrol.formation_id, UINT32_MISSING
            )
            self.patrol_indices[ibase + self.PATROL_ORG] = self.organization_index.get(
                patrol.organization_id, UINT32_MISSING
            )
            self.patrol_indices[ibase + self.PATROL_LOCALITY] = topology.locality_index.get(
                patrol.locality_id, UINT32_MISSING
            )
            self.patrol_indices[ibase + self.PATROL_ZONE] = topology.microzone_index.get(
                patrol.current_microzone_id, UINT32_MISSING
            )

    def _import_zone_state(
        self, lane: int, world: Any, topology: "StaticWorldTopology"
    ) -> None:
        for zone_id, zi in topology.microzone_index.items():
            zone = world.microzones[zone_id]
            go = self._zs(lane, zi, 0)
            io = self._zs(lane, zi, 1)
            self.zone_presence_memory[go] = float(
                zone.presence_memory.get("government", 0.0)
            )
            self.zone_presence_updated_at[go] = float(
                zone.presence_updated_at.get("government", world.time)
            )
            self.zone_physical_control[go] = float(
                zone.physical_control.get("government", 0.0)
            )
            # Preserve the literal side memory exactly. The current reference
            # patrol writer records insurgent exposure under this key, while
            # aggregate response separately consumes concrete franchise
            # memories below.
            self.zone_presence_memory[io] = float(
                zone.presence_memory.get("insurgent", 0.0)
            )
            self.zone_presence_updated_at[io] = float(
                zone.presence_updated_at.get("insurgent", world.time)
            )
            self.zone_physical_control[io] = float(
                zone.physical_control.get("insurgent", 0.0)
            )
            self.zone_insurgent_side_raw[
                lane * self.microzone_count + zi
            ] = float(
                zone.physical_control.get(
                    "__insurgent_side__",
                    zone.physical_control.get("insurgent", 0.0),
                )
            )
            for organization_id, oi in self.organization_index.items():
                offset = self._zo(lane, zi, oi)
                self.zone_org_presence_memory[offset] = float(
                    zone.presence_memory.get(organization_id, 0.0)
                )
                self.zone_org_presence_updated_at[offset] = float(
                    zone.presence_updated_at.get(organization_id, world.time)
                )
                self.zone_org_physical_control[offset] = float(
                    zone.physical_control.get(organization_id, 0.0)
                )

    def gather(self, parents: Sequence[int]) -> None:
        """Gather every mutable packed component, including clocks and RNG."""
        parents = tuple(int(item) for item in parents)
        if len(parents) != self.particle_count:
            raise ValueError("one parent index is required per particle")
        if any(item < 0 or item >= self.particle_count for item in parents):
            raise IndexError("parent particle out of range")
        blocks = {
            "organization_present": self.organization_count,
            "organization_active": self.organization_count,
            "organization_kind": self.organization_count,
            "organization_government_side": self.organization_count,
            "organization_action_eligible": self.organization_count,
            "formation_present": self.formation_count,
            "formation_organization": self.formation_count,
            "formation_locality": self.formation_count,
            "formation_microzone": self.formation_count,
            "formation_values": self.formation_count * self.F_STRIDE,
            "formation_flags": self.formation_count * self.FF_STRIDE,
            "manpower_pool": self.organization_count * self.locality_count,
            "manpower_supply_reserve": self.organization_count * self.locality_count,
            "supply_source_present": len(self.supply_source_ids),
            "supply_source_organization": len(self.supply_source_ids),
            "supply_source_locality": len(self.supply_source_ids),
            "supply_source_stock": len(self.supply_source_ids),
            "post_present": len(self.post_ids),
            "post_values": len(self.post_ids) * self.POST_STRIDE,
            "post_indices": len(self.post_ids) * self.POST_INDEX_STRIDE,
            "patrol_present": len(self.patrol_ids),
            "patrol_values": len(self.patrol_ids) * self.PATROL_STRIDE,
            "patrol_indices": len(self.patrol_ids) * self.PATROL_INDEX_STRIDE,
            "zone_presence_memory": self.microzone_count * 2,
            "zone_presence_updated_at": self.microzone_count * 2,
            "zone_physical_control": self.microzone_count * 2,
            "zone_insurgent_side_raw": self.microzone_count,
            "zone_org_presence_memory": (
                self.microzone_count * self.organization_count
            ),
            "zone_org_presence_updated_at": (
                self.microzone_count * self.organization_count
            ),
            "zone_org_physical_control": (
                self.microzone_count * self.organization_count
            ),
            "locality_population": self.locality_count,
            "config_values": self.C_STRIDE,
        }
        for name, block in blocks.items():
            setattr(self, name, _gather_blocks(getattr(self, name), block, parents))
        for name in HOT_CLOCKS:
            self.next_clocks[name] = _gather_blocks(
                self.next_clocks[name], 1, parents
            )
            self.clock_intervals[name] = _gather_blocks(
                self.clock_intervals[name], 1, parents
            )
        for name, states in tuple(self.rng_states.items()):
            self.rng_states[name] = tuple(states[parent] for parent in parents)
        prior_dirty = set(self.dirty_lanes)
        self.dirty_lanes = {
            lane for lane, parent in enumerate(parents) if parent in prior_dirty
        }

    def formation_effective_readiness(self, lane: int, formation: int) -> float:
        if not self.formation_present[self._fo(lane, formation)]:
            return 0.0
        stock = self.formation_values[
            self._fv(lane, formation, self.F_SUPPLY_STOCK)
        ]
        capacity = self.formation_values[
            self._fv(lane, formation, self.F_SUPPLY_CAPACITY)
        ]
        sustainment = self.formation_values[
            self._fv(lane, formation, self.F_SUSTAINMENT)
        ]
        supply_fraction = (
            clamp(stock / capacity) if capacity > 0 else clamp(sustainment)
        )
        readiness = self.formation_values[
            self._fv(lane, formation, self.F_READINESS)
        ]
        fatigue = self.formation_values[
            self._fv(lane, formation, self.F_FATIGUE)
        ]
        command = self.formation_values[
            self._fv(lane, formation, self.F_COMMAND)
        ]
        fatigue_adjusted = clamp(readiness * (1.0 - 0.65 * clamp(fatigue)))
        return clamp(
            fatigue_adjusted * (0.2 + 0.8 * supply_fraction) * clamp(command)
        )

    def formation_effective_strength(self, lane: int, formation: int) -> float:
        if (
            not self.formation_present[self._fo(lane, formation)]
            or self.formation_flags[self._ff(lane, formation, self.FF_MOVING)]
            or self.formation_flags[self._ff(lane, formation, self.FF_OUTSIDE)]
            or not self.formation_flags[
                self._ff(lane, formation, self.FF_EFFECTIVE)
            ]
        ):
            return 0.0
        personnel = max(
            0.0,
            self.formation_values[self._fv(lane, formation, self.F_PERSONNEL)],
        )
        availability = clamp(
            self.formation_values[self._fv(lane, formation, self.F_AVAILABILITY)]
        )
        available = (
            personnel * availability
            * self.formation_effective_readiness(lane, formation)
        )
        return (
            available
            * self.formation_values[self._fv(lane, formation, self.F_QUALITY)]
            * self.formation_values[self._fv(lane, formation, self.F_COHESION)]
            * (
                0.5
                + self.formation_values[
                    self._fv(lane, formation, self.F_INFORMATION)
                ]
            )
        )

    def local_fighter_equivalents(
        self, lane: int, organization: int, locality: int
    ) -> tuple[float, float]:
        offset = self._ol(lane, organization, locality)
        unfielded = min(
            max(0.0, self.manpower_pool[offset]),
            max(0.0, self.manpower_supply_reserve[offset])
            / self._cfg(lane, self.C_SUPPLY_PER_FIGHTER),
        )
        fielded = 0.0
        for formation in range(self.formation_count):
            fo = self._fo(lane, formation)
            if (
                self.formation_present[fo]
                and self.formation_organization[fo] == organization
                and self.formation_locality[fo] == locality
                and not self.formation_flags[
                    self._ff(lane, formation, self.FF_MOVING)
                ]
                and not self.formation_flags[
                    self._ff(lane, formation, self.FF_OUTSIDE)
                ]
            ):
                fielded += max(
                    0.0,
                    self.formation_values[
                        self._fv(lane, formation, self.F_PERSONNEL)
                    ],
                )
        return unfielded, fielded

    def action_attempt_hazard(
        self, lane: int, organization: int, locality: int
    ) -> float:
        oo = self._oo(lane, organization)
        if (
            not self.organization_present[oo]
            or not self.organization_active[oo]
            or not self.organization_action_eligible[oo]
        ):
            return 0.0
        unfielded, fielded = self.local_fighter_equivalents(
            lane, organization, locality
        )
        total = unfielded + fielded
        if total <= 0:
            return 0.0
        minimum = self._cfg(lane, self.C_MIN_FORMATION)
        committed = total * clamp(total / (total + minimum))
        return max(
            0.0,
            self._cfg(lane, self.C_ACTION_RATE) * committed / minimum,
        )

    def action_attempt_probability(
        self,
        lane: int,
        organization: int,
        locality: int,
        interval_days: float,
    ) -> float:
        if interval_days <= 0:
            return 0.0
        return clamp(
            -expm1(
                -self.action_attempt_hazard(lane, organization, locality)
                * float(interval_days)
            )
        )

    def action_probability_surface(self, interval_days: float) -> array:
        """Return [particle, organization, locality] action probabilities."""
        result = array("d")
        for lane in range(self.particle_count):
            for organization in range(self.organization_count):
                for locality in range(self.locality_count):
                    result.append(
                        self.action_attempt_probability(
                            lane, organization, locality, interval_days
                        )
                    )
        return result

    def _organization_matches_side(
        self, lane: int, organization: int, side: int
    ) -> bool:
        oo = self._oo(lane, organization)
        if not self.organization_active[oo]:
            return False
        if side == INSURGENT_SIDE:
            return self.organization_kind[oo] == INSURGENT_SIDE
        if side == GOVERNMENT_SIDE:
            return bool(self.organization_government_side[oo])
        return False

    def active_insurgent_count(self, lane: int) -> int:
        return sum(
            1
            for organization in range(self.organization_count)
            if (
                self.organization_present[self._oo(lane, organization)]
                and self.organization_active[self._oo(lane, organization)]
                and self.organization_kind[self._oo(lane, organization)]
                == INSURGENT_SIDE
            )
        )

    def advance_patrol_presence(
        self, lane: int, time: float, topology: "StaticWorldTopology"
    ) -> float:
        total = 0.0
        tau = self._cfg(lane, self.C_PRESENCE_TAU)
        patrol_count = len(self.patrol_ids)
        for patrol in range(patrol_count):
            base = lane * patrol_count + patrol
            if not self.patrol_present[base]:
                continue
            ibase = base * self.PATROL_INDEX_STRIDE
            vbase = base * self.PATROL_STRIDE
            formation = int(
                self.patrol_indices[ibase + self.PATROL_FORMATION]
            )
            locality = int(self.patrol_indices[ibase + self.PATROL_LOCALITY])
            zone = int(self.patrol_indices[ibase + self.PATROL_ZONE])
            if (
                formation == UINT32_MISSING
                or locality == UINT32_MISSING
                or zone == UINT32_MISSING
            ):
                continue
            fo = self._fo(lane, formation)
            if (
                not self.formation_present[fo]
                or self.formation_values[
                    self._fv(lane, formation, self.F_PERSONNEL)
                ] <= 0.0
                or self.formation_flags[
                    self._ff(lane, formation, self.FF_MOVING)
                ]
                or self.formation_flags[
                    self._ff(lane, formation, self.FF_OUTSIDE)
                ]
                or not self.formation_flags[
                    self._ff(lane, formation, self.FF_EFFECTIVE)
                ]
                or self.formation_locality[fo] != locality
                or self.patrol_values[
                    vbase + self.PATROL_AVAILABLE_AT
                ] > time
            ):
                continue
            available_at = float(
                self.patrol_values[vbase + self.PATROL_AVAILABLE_AT]
            )
            accounted = float(
                self.patrol_values[vbase + self.PATROL_ACCOUNTED_AT]
            )
            start = (
                available_at if accounted < -1e250
                else max(available_at, accounted)
            )
            duration = max(0.0, float(time) - start)
            self.patrol_values[vbase + self.PATROL_ACCOUNTED_AT] = max(
                start, float(time)
            )
            if duration <= 0:
                continue
            organization = int(self.formation_organization[fo])
            if organization == UINT32_MISSING:
                continue
            side_slot = (
                1
                if self.organization_kind[
                    self._oo(lane, organization)
                ] == INSURGENT_SIDE
                else 0
            )
            zo = self._zs(lane, zone, side_slot)
            elapsed = max(
                0.0, float(time) - float(self.zone_presence_updated_at[zo])
            )
            current = float(self.zone_presence_memory[zo]) * exp(-elapsed / tau)
            deployed = (
                self.formation_effective_strength(lane, formation)
                * clamp(
                    self.patrol_values[vbase + self.PATROL_RESPONSE]
                )
            )
            normalized = deployed / max(
                250.0, self._lp(lane, locality) * 0.002
            )
            target = self._cfg(lane, self.C_PATROL_GAIN) * normalized
            contribution = max(0.0, target) * (
                1.0 - exp(-duration / tau)
            )
            self.zone_presence_memory[zo] = current + contribution
            self.zone_presence_updated_at[zo] = float(time)
            if (
                side_slot == 1
                and self.organization_ids[organization] == "insurgent"
            ):
                org_zone = self._zo(lane, zone, organization)
                self.zone_org_presence_memory[org_zone] = current + contribution
                self.zone_org_presence_updated_at[org_zone] = float(time)
            total += contribution
        return total

    def response_times(
        self,
        lane: int,
        locality: int,
        side: int,
        time: float,
        topology: "StaticWorldTopology",
    ) -> list[float]:
        """Cached-topology response operator. It never runs Dijkstra."""
        zone_indices = [
            zone for zone, owner in enumerate(topology.microzone_locality)
            if int(owner) == locality
        ]
        delays: dict[int, float] = {}
        decay = self._cfg(lane, self.C_RESPONSE_DECAY)
        post_count = len(self.post_ids)
        for post in range(post_count):
            base = lane * post_count + post
            if not self.post_present[base]:
                continue
            ibase = base * self.POST_INDEX_STRIDE
            vbase = base * self.POST_STRIDE
            if self.post_indices[ibase + self.POST_LOCALITY] != locality:
                continue
            organization = int(self.post_indices[ibase + self.POST_ORG])
            if (
                organization == UINT32_MISSING
                or not self._organization_matches_side(lane, organization, side)
            ):
                continue
            available = float(
                self.post_values[vbase + self.POST_AVAILABLE]
            )
            formation = int(
                self.post_indices[ibase + self.POST_FORMATION]
            )
            if formation != UINT32_MISSING:
                fo = self._fo(lane, formation)
                if (
                    not self.formation_present[fo]
                    or self.formation_flags[
                        self._ff(lane, formation, self.FF_MOVING)
                    ]
                    or self.formation_flags[
                        self._ff(lane, formation, self.FF_OUTSIDE)
                    ]
                    or not self.formation_flags[
                        self._ff(lane, formation, self.FF_EFFECTIVE)
                    ]
                    or self.formation_locality[fo] != locality
                ):
                    available = 0.0
                else:
                    available *= (
                        self.formation_values[
                            self._fv(lane, formation, self.F_AVAILABILITY)
                        ]
                        * self.formation_effective_readiness(lane, formation)
                    )
            if available > 0:
                zone = int(self.post_indices[ibase + self.POST_ZONE])
                delay = (1.0 - available) * decay
                delays[zone] = min(delay, delays.get(zone, inf))

        patrol_count = len(self.patrol_ids)
        for patrol in range(patrol_count):
            base = lane * patrol_count + patrol
            if not self.patrol_present[base]:
                continue
            ibase = base * self.PATROL_INDEX_STRIDE
            vbase = base * self.PATROL_STRIDE
            if (
                self.patrol_indices[ibase + self.PATROL_LOCALITY] != locality
                or self.patrol_values[
                    vbase + self.PATROL_AVAILABLE_AT
                ] > time
            ):
                continue
            organization = int(self.patrol_indices[ibase + self.PATROL_ORG])
            formation = int(
                self.patrol_indices[ibase + self.PATROL_FORMATION]
            )
            if (
                organization == UINT32_MISSING
                or formation == UINT32_MISSING
                or not self._organization_matches_side(lane, organization, side)
            ):
                continue
            if (
                self.formation_flags[
                    self._ff(lane, formation, self.FF_MOVING)
                ]
                or self.formation_flags[
                    self._ff(lane, formation, self.FF_OUTSIDE)
                ]
                or not self.formation_flags[
                    self._ff(lane, formation, self.FF_EFFECTIVE)
                ]
            ):
                continue
            effective = (
                self.patrol_values[vbase + self.PATROL_RESPONSE]
                * self.formation_values[
                    self._fv(lane, formation, self.F_AVAILABILITY)
                ]
                * self.formation_effective_readiness(lane, formation)
            )
            if effective > 0:
                zone = int(self.patrol_indices[ibase + self.PATROL_ZONE])
                delay = (1.0 - effective) * decay
                delays[zone] = min(delay, delays.get(zone, inf))

        for formation in range(self.formation_count):
            fo = self._fo(lane, formation)
            if (
                not self.formation_present[fo]
                or self.formation_locality[fo] != locality
                or self.formation_flags[
                    self._ff(lane, formation, self.FF_MOVING)
                ]
                or self.formation_flags[
                    self._ff(lane, formation, self.FF_OUTSIDE)
                ]
                or not self.formation_flags[
                    self._ff(lane, formation, self.FF_EFFECTIVE)
                ]
                or self.formation_values[
                    self._fv(lane, formation, self.F_PERSONNEL)
                ] <= 0
            ):
                continue
            organization = int(self.formation_organization[fo])
            zone = int(self.formation_microzone[fo])
            if (
                organization == UINT32_MISSING
                or zone == UINT32_MISSING
                or not self._organization_matches_side(lane, organization, side)
            ):
                continue
            effective = (
                0.30
                * self.formation_values[
                    self._fv(lane, formation, self.F_AVAILABILITY)
                ]
                * self.formation_effective_readiness(lane, formation)
            )
            if effective > 0:
                delay = (1.0 - effective) * decay
                delays[zone] = min(delay, delays.get(zone, inf))

        result = [inf] * self.microzone_count
        count = self.microzone_count
        for target in zone_indices:
            best = inf
            for source, delay in delays.items():
                distance = topology.physical_distances[
                    source * count + target
                ]
                candidate = delay + distance
                if candidate < best:
                    best = candidate
            result[target] = best
        return result

    def recompute_physical_lane(
        self, lane: int, time: float, topology: "StaticWorldTopology"
    ) -> array:
        """Refresh contested side-level physical control for one packed lane."""
        self.advance_patrol_presence(lane, time, topology)
        raw = array("d", [0.0]) * (self.microzone_count * 2)
        aggregates = array("d", [0.0]) * (self.locality_count * 2)
        tau = self._cfg(lane, self.C_PRESENCE_TAU)
        for locality in range(self.locality_count):
            zone_indices = [
                zone for zone, owner in enumerate(topology.microzone_locality)
                if int(owner) == locality
            ]
            population = self._lp(lane, locality)
            for side_slot, side in enumerate((GOVERNMENT_SIDE, INSURGENT_SIDE)):
                response = self.response_times(
                    lane, locality, side, time, topology
                )
                posts = {zone: 0.0 for zone in zone_indices}
                formations = {zone: 0.0 for zone in zone_indices}

                post_count = len(self.post_ids)
                for post in range(post_count):
                    base = lane * post_count + post
                    if not self.post_present[base]:
                        continue
                    ibase = base * self.POST_INDEX_STRIDE
                    vbase = base * self.POST_STRIDE
                    if self.post_indices[ibase + self.POST_LOCALITY] != locality:
                        continue
                    organization = int(
                        self.post_indices[ibase + self.POST_ORG]
                    )
                    if (
                        organization == UINT32_MISSING
                        or not self._organization_matches_side(
                            lane, organization, side
                        )
                    ):
                        continue
                    effective_presence = float(
                        self.post_values[vbase + self.POST_FIXED]
                    )
                    formation = int(
                        self.post_indices[ibase + self.POST_FORMATION]
                    )
                    if formation != UINT32_MISSING:
                        fo = self._fo(lane, formation)
                        if (
                            self.formation_flags[
                                self._ff(lane, formation, self.FF_MOVING)
                            ]
                            or self.formation_flags[
                                self._ff(lane, formation, self.FF_OUTSIDE)
                            ]
                            or not self.formation_flags[
                                self._ff(lane, formation, self.FF_EFFECTIVE)
                            ]
                            or self.formation_locality[fo] != locality
                        ):
                            effective_presence = 0.0
                        else:
                            effective_presence *= (
                                self.formation_values[
                                    self._fv(
                                        lane, formation, self.F_AVAILABILITY
                                    )
                                ]
                                * self.formation_effective_readiness(
                                    lane, formation
                                )
                            )
                    zone = int(self.post_indices[ibase + self.POST_ZONE])
                    if zone in posts:
                        posts[zone] += effective_presence

                for formation in range(self.formation_count):
                    fo = self._fo(lane, formation)
                    if (
                        not self.formation_present[fo]
                        or self.formation_locality[fo] != locality
                        or self.formation_flags[
                            self._ff(lane, formation, self.FF_MOVING)
                        ]
                        or self.formation_flags[
                            self._ff(lane, formation, self.FF_OUTSIDE)
                        ]
                        or not self.formation_flags[
                            self._ff(lane, formation, self.FF_EFFECTIVE)
                        ]
                        or self.formation_values[
                            self._fv(lane, formation, self.F_PERSONNEL)
                        ] <= 0
                    ):
                        continue
                    organization = int(self.formation_organization[fo])
                    zone = int(self.formation_microzone[fo])
                    if (
                        organization == UINT32_MISSING
                        or zone == UINT32_MISSING
                        or zone not in formations
                        or not self._organization_matches_side(
                            lane, organization, side
                        )
                    ):
                        continue
                    formations[zone] += (
                        self._cfg(lane, self.C_FORMATION_GAIN)
                        * self.formation_effective_strength(lane, formation)
                        / max(250.0, population * 0.002)
                    )

                for zone in zone_indices:
                    zo = self._zs(lane, zone, side_slot)
                    if side == INSURGENT_SIDE:
                        memory = 0.0
                        for organization in range(self.organization_count):
                            oo = self._oo(lane, organization)
                            if (
                                not self.organization_active[oo]
                                or self.organization_kind[oo] != INSURGENT_SIDE
                            ):
                                continue
                            org_zone = self._zo(lane, zone, organization)
                            elapsed = max(
                                0.0,
                                float(time)
                                - float(
                                    self.zone_org_presence_updated_at[org_zone]
                                ),
                            )
                            value = float(
                                self.zone_org_presence_memory[org_zone]
                            ) * exp(-elapsed / tau)
                            self.zone_org_presence_memory[org_zone] = value
                            self.zone_org_presence_updated_at[org_zone] = float(
                                time
                            )
                            if self.organization_ids[organization] == "insurgent":
                                self.zone_presence_memory[zo] = value
                                self.zone_presence_updated_at[zo] = float(time)
                            memory += value
                    else:
                        elapsed = max(
                            0.0,
                            float(time)
                            - float(self.zone_presence_updated_at[zo]),
                        )
                        memory = float(self.zone_presence_memory[zo]) * exp(
                            -elapsed / tau
                        )
                        self.zone_presence_memory[zo] = memory
                        self.zone_presence_updated_at[zo] = float(time)
                    presence = 1.0 - exp(
                        -(
                            memory
                            + self._cfg(lane, self.C_POST_GAIN)
                            * posts.get(zone, 0.0)
                            + formations.get(zone, 0.0)
                        )
                    )
                    response_value = (
                        0.0
                        if response[zone] == inf
                        else exp(
                            -response[zone]
                            / self._cfg(lane, self.C_RESPONSE_DECAY)
                        )
                    )
                    raw[zone * 2 + side_slot] = clamp(
                        0.55 * presence + 0.45 * response_value
                    )

            for zone in zone_indices:
                government = raw[zone * 2]
                insurgent = raw[zone * 2 + 1]
                self.zone_insurgent_side_raw[
                    lane * self.microzone_count + zone
                ] = insurgent
                government_contested = clamp(
                    government * (1.0 - 0.35 * insurgent)
                )
                insurgent_contested = clamp(
                    insurgent * (1.0 - 0.35 * government)
                )
                self.zone_physical_control[self._zs(lane, zone, 0)] = (
                    government_contested
                )
                self.zone_physical_control[self._zs(lane, zone, 1)] = (
                    insurgent_contested
                )
                share = self.zone_population_share[zone]
                aggregates[locality * 2] += share * government_contested
                aggregates[locality * 2 + 1] += share * insurgent_contested
            aggregates[locality * 2] = clamp(aggregates[locality * 2])
            aggregates[locality * 2 + 1] = clamp(
                aggregates[locality * 2 + 1]
            )
        self.dirty_lanes.add(lane)
        return aggregates

    def export_lane_to_world(
        self,
        lane: int,
        world: Any,
        topology: "StaticWorldTopology",
        *,
        clear_dirty: bool = True,
    ) -> None:
        """Write only migrated hot state into a Python reference/view world."""
        for formation_id, fi in self.formation_index.items():
            formation = world.formations.get(formation_id)
            if formation is None:
                continue
            fo = self._fo(lane, fi)
            if not self.formation_present[fo]:
                continue
            locality = int(self.formation_locality[fo])
            zone = int(self.formation_microzone[fo])
            if locality != UINT32_MISSING:
                formation.locality_id = topology.locality_ids[locality]
            formation.current_microzone_id = (
                topology.microzone_ids[zone]
                if zone != UINT32_MISSING
                else None
            )
            formation.personnel = float(
                self.formation_values[self._fv(lane, fi, self.F_PERSONNEL)]
            )
            formation.readiness = float(
                self.formation_values[self._fv(lane, fi, self.F_READINESS)]
            )
            formation.sustainment = float(
                self.formation_values[self._fv(lane, fi, self.F_SUSTAINMENT)]
            )
            formation.supply_stock = float(
                self.formation_values[self._fv(lane, fi, self.F_SUPPLY_STOCK)]
            )
            formation.supply_capacity = float(
                self.formation_values[
                    self._fv(lane, fi, self.F_SUPPLY_CAPACITY)
                ]
            )
            formation.fatigue = float(
                self.formation_values[self._fv(lane, fi, self.F_FATIGUE)]
            )
            formation.availability = float(
                self.formation_values[
                    self._fv(lane, fi, self.F_AVAILABILITY)
                ]
            )
            formation.moving = bool(
                self.formation_flags[self._ff(lane, fi, self.FF_MOVING)]
            )
            formation.outside_pineland = bool(
                self.formation_flags[self._ff(lane, fi, self.FF_OUTSIDE)]
            )
            formation.operational_status = (
                "effective"
                if self.formation_flags[
                    self._ff(lane, fi, self.FF_EFFECTIVE)
                ]
                else "ineffective"
            )

        for organization_id, oi in self.organization_index.items():
            for locality_id, li in topology.locality_index.items():
                offset = self._ol(lane, oi, li)
                key = (organization_id, locality_id)
                pool = float(self.manpower_pool[offset])
                reserve = float(self.manpower_supply_reserve[offset])
                if pool > 1e-12:
                    world.organization_manpower_pools[key] = pool
                elif key in world.organization_manpower_pools:
                    # A zero-valued pool can be an explicit decision-state key
                    # created by a reference sparse event.  Preserve that key;
                    # only omit keys that were never represented in the world.
                    world.organization_manpower_pools[key] = 0.0
                else:
                    world.organization_manpower_pools.pop(key, None)
                if reserve > 1e-12:
                    world.organization_manpower_supply_reserves[key] = reserve
                elif key in world.organization_manpower_supply_reserves:
                    world.organization_manpower_supply_reserves[key] = 0.0
                else:
                    world.organization_manpower_supply_reserves.pop(key, None)

        patrol_count = len(self.patrol_ids)
        for patrol_id, pi in self.patrol_index.items():
            patrol = world.patrols.get(patrol_id)
            if patrol is None:
                continue
            base = lane * patrol_count + pi
            ibase = base * self.PATROL_INDEX_STRIDE
            vbase = base * self.PATROL_STRIDE
            zone = int(self.patrol_indices[ibase + self.PATROL_ZONE])
            if zone != UINT32_MISSING:
                patrol.current_microzone_id = topology.microzone_ids[zone]
            patrol.available_at = float(
                self.patrol_values[vbase + self.PATROL_AVAILABLE_AT]
            )
            patrol.response_fraction = float(
                self.patrol_values[vbase + self.PATROL_RESPONSE]
            )
            accounted = float(
                self.patrol_values[vbase + self.PATROL_ACCOUNTED_AT]
            )
            patrol.presence_accounted_at = (
                None if accounted < -1e250 else accounted
            )

        for zone_id, zi in topology.microzone_index.items():
            zone = world.microzones[zone_id]
            go = self._zs(lane, zi, 0)
            io = self._zs(lane, zi, 1)
            zone.presence_memory["government"] = float(
                self.zone_presence_memory[go]
            )
            zone.presence_updated_at["government"] = float(
                self.zone_presence_updated_at[go]
            )
            zone.presence_memory["insurgent"] = float(
                self.zone_presence_memory[io]
            )
            zone.presence_updated_at["insurgent"] = float(
                self.zone_presence_updated_at[io]
            )
            for organization_id, oi in self.organization_index.items():
                org_zone = self._zo(lane, zi, oi)
                if (
                    self.organization_present[self._oo(lane, oi)]
                    and self.organization_kind[self._oo(lane, oi)]
                    == INSURGENT_SIDE
                ):
                    zone.presence_memory[organization_id] = float(
                        self.zone_org_presence_memory[org_zone]
                    )
                    zone.presence_updated_at[organization_id] = float(
                        self.zone_org_presence_updated_at[org_zone]
                    )
            zone.physical_control["government"] = float(
                self.zone_physical_control[go]
            )
            zone.physical_control["__insurgent_side__"] = float(
                self.zone_insurgent_side_raw[
                    lane * self.microzone_count + zi
                ]
            )
            zone.physical_control["insurgent"] = float(
                self.zone_physical_control[io]
            )

        # Locality physical state is a scalar mirror of the authoritative
        # microzone state. Sparse handlers read it directly, so materialize the
        # aggregate only at this explicit Python-view boundary.
        for locality_id, li in topology.locality_index.items():
            government = 0.0
            insurgent = 0.0
            for zi, owner in enumerate(topology.microzone_locality):
                if int(owner) != li:
                    continue
                share = self.zone_population_share[zi]
                government += share * self.zone_physical_control[
                    self._zs(lane, zi, 0)
                ]
                insurgent += share * self.zone_physical_control[
                    self._zs(lane, zi, 1)
                ]
            locality = world.localities[locality_id]
            locality.population = self._lp(lane, li)
            locality.control.setdefault(
                "government", type(next(iter(locality.control.values())))()
            ).physical = clamp(government)
            locality.control.setdefault(
                "insurgent", type(next(iter(locality.control.values())))()
            ).physical = clamp(insurgent)
            active_insurgents = [
                organization_id
                for organization_id, oi in self.organization_index.items()
                if (
                    self.organization_present[self._oo(lane, oi)]
                    and self.organization_active[self._oo(lane, oi)]
                    and self.organization_kind[self._oo(lane, oi)]
                    == INSURGENT_SIDE
                )
            ]
            if len(active_insurgents) == 1:
                locality.control.setdefault(
                    active_insurgents[0],
                    type(next(iter(locality.control.values())))(),
                ).physical = clamp(insurgent)

        world.rebuild_runtime_entity_indexes()
        if clear_dirty:
            self.dirty_lanes.discard(lane)


SparseBoundary = Callable[["ParticleBatchState", int, str, float], None]


@dataclass(slots=True)
class NativeEnsembleRunner:
    """Batch transition engine over authoritative packed particle lanes."""

    topology: "StaticWorldTopology"
    hot_state: PackedHotState
    sparse_boundary: SparseBoundary | None = None
    enable_information_boundary: bool = True
    enable_physical_island: bool = True
    enable_action_noop_island: bool = True
    scheduler_oracle: bool = True
    event_counts: dict[str, int] = field(default_factory=dict)
    physical_refreshes: int = 0
    action_opportunities: int = 0
    information_boundaries: int = 0
    sparse_boundaries: int = 0
    realized_action_boundaries: int = 0
    packed_noop_actions: int = 0
    policy_boundaries: int = 0
    structural_rebuilds: int = 0
    initialized_lanes: set[int] = field(default_factory=set, repr=False)

    @classmethod
    def from_batch(
        cls,
        batch: "ParticleBatchState",
        *,
        sparse_boundary: SparseBoundary | None = None,
        enable_information_boundary: bool = True,
        enable_physical_island: bool = True,
        enable_action_noop_island: bool = True,
        scheduler_oracle: bool = True,
    ) -> "NativeEnsembleRunner":
        hot = getattr(batch, "hot_state", None)
        if hot is None:
            hot = PackedHotState.from_particles(
                batch.particles, batch.topology
            )
            batch.hot_state = hot
        return cls(
            topology=batch.topology,
            hot_state=hot,
            sparse_boundary=sparse_boundary,
            enable_information_boundary=enable_information_boundary,
            enable_physical_island=enable_physical_island,
            enable_action_noop_island=enable_action_noop_island,
            scheduler_oracle=bool(scheduler_oracle),
        )

    def __call__(self, batch: "ParticleBatchState", until: float) -> None:
        self.advance(batch, min(batch.times), float(until))

    @property
    def requires_reference_lineages(self) -> bool:
        """Whether resampling must fork scheduler/RNG metadata per child."""
        return bool(self.scheduler_oracle)

    def _initialize_lane(
        self, batch: "ParticleBatchState", lane: int
    ) -> Any:
        if lane in self.initialized_lanes:
            simulation = _particle_simulation(batch.particles[lane])
            if simulation is None:
                raise RuntimeError("scheduler-oracle execution needs Simulation views")
            return simulation
        if not batch.particles:
            raise RuntimeError("scheduler-oracle execution needs retained particles")
        particle = batch.particles[lane]
        simulation = _particle_simulation(particle)
        if simulation is None:
            raise RuntimeError("scheduler-oracle execution needs Simulation views")
        was_initialized = bool(getattr(simulation, "_initialized", False))
        simulation.initialize()
        # Initialization can execute a configured burn-in. Pull that exact
        # stabilized state back into the packed lane once; ordinary zero-burn-in
        # initialization only populates the event queue and is inexpensive.
        if not was_initialized:
            self.hot_state.import_lane(lane, simulation.world, self.topology)
            batch.refresh_beliefs_from_world(lane)
            batch.times[lane] = float(simulation.world.time)
        self.initialized_lanes.add(lane)
        return simulation

    def _structure_changed(self, world: Any) -> bool:
        return (
            any(key not in self.hot_state.organization_index
                for key in world.organizations)
            or any(key not in self.hot_state.formation_index
                   for key in world.formations)
            or any(key not in self.hot_state.patrol_index
                   for key in world.patrols)
            or any(key not in self.hot_state.post_index
                   for key in world.security_posts)
            or any(key not in self.hot_state.supply_source_index
                   for key in world.supply_sources)
        )

    def _rebuild_structure(
        self,
        batch: "ParticleBatchState",
        *,
        preserve_lanes: tuple[int, ...] = (),
    ) -> None:
        """Rare structural boundary for new organizations/formations.

        Dynamic organization ecology can create entity IDs that did not exist
        when the batch was first packed. At that point all lanes are explicitly
        materialized once, a new union codebook is built, and packed authority
        resumes. The lane whose sparse event created the structure is already
        synchronized *before* the reference handler runs. Exporting the old
        packed state over that lane here would erase the just-computed event
        (for example, organization ecology can both add a formation and change
        existing formations). Other lanes still need the normal packed export
        before the union topology is rebuilt.

        This is deliberately rare and never occurs on a normal
        hot physical/information tick.
        """
        preserved = {int(lane) for lane in preserve_lanes}
        for lane in range(batch.particle_count):
            if lane not in preserved:
                batch.synchronize_lane_to_world(lane)
        replacement = PackedHotState.from_particles(
            batch.particles, self.topology
        )
        batch.hot_state = replacement
        self.hot_state = replacement
        self.structural_rebuilds += 1

    def _consume_packed_process_event(
        self, simulation: Any, event_type: str
    ) -> None:
        """Advance ProcessEngine event identity for a packed-handled event."""
        from .world import seeded_rng

        process_engine = simulation.processes
        process_engine.event_counter += 1
        if process_engine._injected_rng is None:
            process_engine.rng = process_engine._process_rngs.setdefault(
                event_type,
                seeded_rng(
                    process_engine.world.config,
                    process_engine._stream_name(f"process:{event_type}"),
                ),
            )
        process_engine.world.active_event_id = None
        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1

    def _apply_policy_if_due(
        self,
        batch: "ParticleBatchState",
        lane: int,
        time: float,
    ) -> None:
        simulation = _particle_simulation(batch.particles[lane])
        hook = getattr(simulation, "policy_hook", None)
        if hook is None:
            return
        next_boundary = getattr(hook, "next_boundary_time", None)
        if callable(next_boundary):
            due = next_boundary()
            if due is None or float(due) > float(time) + 1e-12:
                return
        # Generic hooks without a boundary protocol retain reference semantics
        # by executing at every event. Hooks that implement next_boundary_time
        # pay this materialization cost only when they can actually change state.
        batch.times[lane] = float(time)
        batch.synchronize_lane_to_world(lane)
        world = _particle_world(batch.particles[lane])
        world.time = float(time)
        hook(world, float(time))
        if self._structure_changed(world):
            self._rebuild_structure(batch, preserve_lanes=(lane,))
        else:
            self.hot_state.import_lane(lane, world, self.topology)
            batch.refresh_beliefs_from_world(lane)
        self.policy_boundaries += 1

    def _maybe_start_recruitment(self, simulation: Any, time: float) -> None:
        if getattr(simulation, "_recruitment_clock_started", False):
            return
        if not any(
            organization.kind is OrganizationKind.INSURGENT
            and organization.status == "active"
            for organization in simulation.world.organizations.values()
        ):
            return
        interval = simulation.world.config.intervals.recruitment
        simulation.scheduler.schedule(
            float(time),
            "recruitment",
            {"interval": interval, "elapsed_days": 0.0},
            priority=60,
        )
        simulation._recruitment_clock_started = True

    def _execute_reference_event(
        self,
        batch: "ParticleBatchState",
        lane: int,
        event: Any,
    ) -> None:
        """Execute exactly one explicitly sparse ProcessEngine event."""
        simulation = _particle_simulation(batch.particles[lane])
        batch.times[lane] = float(event.time)
        if event.event_type == "patrol":
            batch.synchronize_hot_lane_to_world(lane)
        else:
            batch.synchronize_lane_to_world(lane)
        world = simulation.world
        world.time = float(event.time)
        simulation.processes.execute(event)
        self.sparse_boundaries += 1
        self.event_counts[event.event_type] = (
            self.event_counts.get(event.event_type, 0) + 1
        )
        if self._structure_changed(world):
            self._rebuild_structure(batch, preserve_lanes=(lane,))
        else:
            self.hot_state.import_lane(lane, world, self.topology)
            batch.refresh_beliefs_from_world(lane)

    def _schedule_organized_actions(
        self,
        simulation: Any,
        lane: int,
        current_time: float,
        *,
        interval_days: float,
        realization_time: float,
    ) -> int:
        """Schedule action opportunities from packed local capacity.

        Iteration is by the same sorted organization/locality IDs used by the
        reference scheduler, preserving same-time sequence order.
        """
        scheduled = 0
        for organization_id in self.hot_state.organization_ids:
            organization = self.hot_state.organization_index[organization_id]
            oo = self.hot_state._oo(lane, organization)
            if (
                not self.hot_state.organization_present[oo]
                or not self.hot_state.organization_active[oo]
                or not self.hot_state.organization_action_eligible[oo]
            ):
                continue
            for locality_id in sorted(self.hot_state.locality_ids):
                locality = self.topology.locality_index[locality_id]
                unfielded, fielded = self.hot_state.local_fighter_equivalents(
                    lane, organization, locality
                )
                if unfielded + fielded <= 0.0:
                    continue
                simulation.scheduler.schedule(
                    float(realization_time),
                    "organized_action",
                    {
                        "organization_id": organization_id,
                        "locality_id": locality_id,
                        "interval_days": float(interval_days),
                    },
                    priority=18,
                )
                scheduled += 1
        self.action_opportunities += scheduled
        return scheduled

    def _organized_action_event(
        self,
        batch: "ParticleBatchState",
        lane: int,
        event: Any,
    ) -> bool:
        """Handle the dominant no-action path without materializing a world.

        Returns True when the complete event was handled in packed state. If an
        action opportunity realizes, the RNG is restored and False is returned
        so the exact reference consequence handler consumes the same draw and
        all subsequent channel/consequence draws.
        """
        from .world import seeded_rng

        simulation = _particle_simulation(batch.particles[lane])
        world = simulation.world
        organization_id = str(event.payload["organization_id"])
        locality_id = str(event.payload["locality_id"])
        organization = self.hot_state.organization_index.get(organization_id)
        locality = self.topology.locality_index.get(locality_id)
        if organization is None or locality is None:
            return False
        oo = self.hot_state._oo(lane, organization)
        if (
            not self.hot_state.organization_present[oo]
            or not self.hot_state.organization_active[oo]
            or not self.hot_state.organization_action_eligible[oo]
        ):
            self._consume_packed_process_event(simulation, "organized_action")
            self.packed_noop_actions += 1
            return True
        self.hot_state.advance_patrol_presence(
            lane, float(event.time), self.topology
        )
        interval_days = max(
            0.0, float(event.payload.get("interval_days", 1.0))
        )
        hazard = self.hot_state.action_attempt_hazard(
            lane, organization, locality
        )
        unfielded, fielded = self.hot_state.local_fighter_equivalents(
            lane, organization, locality
        )
        if unfielded + fielded <= 0.0:
            world.record_activity_hazard(
                time=float(event.time),
                locality_id=locality_id,
                hazard_per_day=hazard,
                interval_days=interval_days,
            )
            self._consume_packed_process_event(simulation, "organized_action")
            self.packed_noop_actions += 1
            return True
        probability = self.hot_state.action_attempt_probability(
            lane, organization, locality, interval_days
        )
        process_engine = simulation.processes
        rng = process_engine._process_rngs.setdefault(
            "organized_action",
            seeded_rng(
                world.config,
                process_engine._stream_name("process:organized_action"),
            ),
        )
        before = rng.getstate()
        draw = rng.random()
        if draw >= probability:
            # Successful attempts are handed to the reference realization
            # handler, which records this same exposure. Record it here only
            # when the whole no-op event remains packed.
            world.record_activity_hazard(
                time=float(event.time),
                locality_id=locality_id,
                hazard_per_day=hazard,
                interval_days=interval_days,
            )
            states = list(
                self.hot_state.rng_states.get(
                    "organized_action",
                    (None,) * self.hot_state.particle_count,
                )
            )
            states[lane] = rng.getstate()
            self.hot_state.rng_states["organized_action"] = tuple(states)
            self._consume_packed_process_event(simulation, "organized_action")
            self.packed_noop_actions += 1
            return True
        # Let the reference handler realize the action from the exact pre-draw
        # RNG state. It will repeat this successful draw and then consume
        # channel/target/consequence randomness in the canonical order.
        rng.setstate(before)
        self.realized_action_boundaries += 1
        return False

    def _information_boundary(
        self, batch: "ParticleBatchState", lane: int, time: float
    ) -> None:
        if not self.enable_information_boundary:
            return
        if not batch.particles:
            raise RuntimeError(
                "information boundary needs retained Python views"
            )
        particle = batch.particles[lane]
        world = _particle_world(particle)
        self.hot_state.export_lane_to_world(
            lane, world, self.topology, clear_dirty=False
        )
        simulation = _particle_simulation(particle)
        if simulation is None:
            raise RuntimeError(
                "information boundary requires a Simulation view"
            )
        from .ensemble import process_information_numeric
        from .world import seeded_rng

        process_engine = simulation.processes
        process_engine.event_counter += 1
        rng = process_engine._process_rngs.setdefault(
            "information",
            seeded_rng(
                world.config,
                process_engine._stream_name("process:information"),
            ),
        )
        process_engine.rng = rng
        world.time = float(time)
        process_information_numeric(world, float(time), rng)
        if world.execution_profile == "particle":
            world.compact_particle_information_state()
        world.active_event_id = None
        batch.refresh_beliefs_from_world(lane)
        states = list(
            self.hot_state.rng_states.get(
                "information", (None,) * self.hot_state.particle_count
            )
        )
        states[lane] = rng.getstate()
        self.hot_state.rng_states["information"] = tuple(states)
        self.information_boundaries += 1
        self.event_counts["information"] = (
            self.event_counts.get("information", 0) + 1
        )

    def _sparse(
        self,
        batch: "ParticleBatchState",
        lane: int,
        name: str,
        time: float,
    ) -> None:
        self.sparse_boundaries += 1
        if self.sparse_boundary is None:
            raise RuntimeError(
                "native ensemble reached non-migrated "
                f"{name!r} boundary at t={time}; provide sparse_boundary "
                "or use the reference engine"
            )
        self.sparse_boundary(batch, lane, name, time)
        if batch.particles:
            world = _particle_world(batch.particles[lane])
            self.hot_state.import_lane(lane, world, self.topology)
            batch.refresh_beliefs_from_world(lane)

    def _advance_scheduler_oracle(
        self,
        batch: "ParticleBatchState",
        end_time: float,
    ) -> None:
        """Advance exact scheduler order while executing migrated islands packed."""
        if not batch.particles:
            raise RuntimeError(
                "scheduler-oracle execution needs retained particle views"
            )
        simulations = [
            self._initialize_lane(batch, lane)
            for lane in range(batch.particle_count)
        ]
        while True:
            next_time = inf
            lanes: list[int] = []
            for lane, simulation in enumerate(simulations):
                candidate = simulation.scheduler.peek_time()
                if candidate is None:
                    continue
                candidate = float(candidate)
                if candidate < next_time - 1e-12:
                    next_time = candidate
                    lanes = [lane]
                elif abs(candidate - next_time) <= 1e-12:
                    lanes.append(lane)
            if next_time == inf or next_time > end_time + 1e-12:
                break

            # Particle lanes are independent. Within each lane, consume every
            # event at this timestamp in exact scheduler priority/sequence
            # order, including events newly scheduled at the same timestamp.
            for lane in lanes:
                simulation = simulations[lane]
                while (
                    simulation.scheduler.peek_time() is not None
                    and abs(
                        float(simulation.scheduler.peek_time()) - next_time
                    ) <= 1e-12
                ):
                    event = simulation.scheduler.pop_next()
                    if (
                        event.event_type == "checkpoint"
                        and not simulation._checkpointing
                    ):
                        continue
                    batch.times[lane] = float(event.time)
                    self._apply_policy_if_due(
                        batch, lane, float(event.time)
                    )

                    if event.event_type == "contact_scan":
                        interval = float(event.payload["interval"])
                        exposure_days = min(
                            interval,
                            max(0.0, end_time - float(event.time)),
                        )
                        if exposure_days > 0.0:
                            if (
                                simulation.world.config.combat
                                .organized_action_architecture
                                == "multichannel_v5"
                            ):
                                self._schedule_organized_actions(
                                    simulation,
                                    lane,
                                    float(event.time),
                                    interval_days=exposure_days,
                                    realization_time=(
                                        float(event.time) + exposure_days
                                    ),
                                )
                            else:
                                # Legacy contact architecture is not a hot
                                # Phase-A target. Preserve it as an explicit
                                # sparse scheduler boundary.
                                batch.synchronize_lane_to_world(lane)
                                simulation.world.time = float(event.time)
                                simulation._schedule_contacts(
                                    float(event.time),
                                    interval_days=exposure_days,
                                    realization_time=(
                                        float(event.time) + exposure_days
                                    ),
                                )
                                self.sparse_boundaries += 1
                        simulation._reschedule(
                            event.event_type,
                            event.payload,
                            float(event.time),
                        )
                        self.event_counts["contact_scan"] = (
                            self.event_counts.get("contact_scan", 0) + 1
                        )
                        continue

                    if event.event_type == "physical_refresh":
                        if (
                            self.enable_physical_island
                            and self.hot_state.active_insurgent_count(lane) <= 1
                        ):
                            self.hot_state.recompute_physical_lane(
                                lane, float(event.time), self.topology
                            )
                            self._consume_packed_process_event(
                                simulation, "physical_refresh"
                            )
                            self.physical_refreshes += 1
                        else:
                            self._execute_reference_event(
                                batch, lane, event
                            )
                        self._maybe_start_recruitment(
                            simulation, float(event.time)
                        )
                        simulation._reschedule(
                            event.event_type,
                            event.payload,
                            float(event.time),
                        )
                        continue

                    if event.event_type == "information":
                        if self.enable_information_boundary:
                            self._information_boundary(
                                batch, lane, float(event.time)
                            )
                        else:
                            self._execute_reference_event(
                                batch, lane, event
                            )
                        self._maybe_start_recruitment(
                            simulation, float(event.time)
                        )
                        simulation._reschedule(
                            event.event_type,
                            event.payload,
                            float(event.time),
                        )
                        continue

                    if event.event_type == "organized_action":
                        handled = (
                            self._organized_action_event(
                                batch, lane, event
                            )
                            if self.enable_action_noop_island
                            else False
                        )
                        if not handled:
                            self._execute_reference_event(
                                batch, lane, event
                            )
                        self._maybe_start_recruitment(
                            simulation, float(event.time)
                        )
                        # Organized-action realization events are one-shot.
                        continue

                    # Every other event is named, counted, and crosses the
                    # explicit reference boundary one event at a time. This is
                    # categorically different from calling Simulation.run().
                    self._execute_reference_event(batch, lane, event)
                    self._maybe_start_recruitment(
                        simulation, float(event.time)
                    )
                    simulation._reschedule(
                        event.event_type,
                        event.payload,
                        float(event.time),
                    )

        # Calendar boundary semantics match Simulation.run: close continuous
        # patrol exposure through the requested horizon without manufacturing
        # another discrete event.
        for lane, simulation in enumerate(simulations):
            self.hot_state.advance_patrol_presence(
                lane, end_time, self.topology
            )
            batch.times[lane] = float(end_time)
            simulation.world.time = float(end_time)

    def advance(
        self,
        batch: "ParticleBatchState",
        start_time: float,
        end_time: float,
    ) -> None:
        if batch.hot_state is not self.hot_state:
            raise ValueError("runner hot state does not belong to batch")
        end_time = float(end_time)
        if end_time < min(batch.times) - 1e-12:
            raise ValueError("native ensemble cannot move backward")
        if self.scheduler_oracle and batch.particles:
            self._advance_scheduler_oracle(batch, end_time)
            return
        while True:
            next_time = inf
            next_name = None
            for name in HOT_CLOCKS:
                values = self.hot_state.next_clocks[name]
                candidate = min(values) if values else inf
                if candidate < next_time:
                    next_time = candidate
                    next_name = name
            if next_name is None or next_time > end_time + 1e-12:
                break
            lanes = [
                lane
                for lane, value in enumerate(
                    self.hot_state.next_clocks[next_name]
                )
                if abs(float(value) - float(next_time)) <= 1e-12
                and float(value) <= end_time + 1e-12
            ]
            for lane in lanes:
                if next_name == "physical_refresh":
                    self.hot_state.recompute_physical_lane(
                        lane, next_time, self.topology
                    )
                    self.physical_refreshes += 1
                elif next_name == "action_opportunity":
                    for organization in range(
                        self.hot_state.organization_count
                    ):
                        for locality in range(
                            self.hot_state.locality_count
                        ):
                            if self.hot_state.action_attempt_hazard(
                                lane, organization, locality
                            ) > 0:
                                self.event_counts["action_hazard_cells"] = (
                                    self.event_counts.get(
                                        "action_hazard_cells", 0
                                    )
                                    + 1
                                )
                    self.action_opportunities += 1
                elif next_name == "information":
                    self._information_boundary(
                        batch, lane, next_time
                    )
                else:
                    self._sparse(batch, lane, next_name, next_time)
                interval = float(
                    self.hot_state.clock_intervals[next_name][lane]
                )
                self.hot_state.next_clocks[next_name][lane] = (
                    inf
                    if interval <= 0 or interval == inf
                    else next_time + interval
                )
                self.event_counts[next_name] = (
                    self.event_counts.get(next_name, 0) + 1
                )
        for lane in range(batch.particle_count):
            self.hot_state.advance_patrol_presence(
                lane, end_time, self.topology
            )
        batch.times = array(
            "d", [end_time] * batch.particle_count
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "engine": "NativeEnsembleRunner",
            "authoritative": "packed_hot_state",
            "particles": self.hot_state.particle_count,
            "physical_refreshes": self.physical_refreshes,
            "action_opportunities": self.action_opportunities,
            "information_boundaries": self.information_boundaries,
            "sparse_boundaries": self.sparse_boundaries,
            "event_counts": dict(self.event_counts),
            "dijkstra_calls": 0,
            "particle_advance_to_calls": 0,
        }


__all__ = [
    "GOVERNMENT_SIDE",
    "HOT_CLOCKS",
    "INSURGENT_SIDE",
    "NativeEnsembleRunner",
    "PackedHotState",
    "SparseBoundary",
    "UINT32_MISSING",
]
