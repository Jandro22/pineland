import copy, json, sys
sys.path.insert(0, 'src')
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
from pineland_sim.timebase import reference_probability

base = json.loads(open('scenarios/baseline.json').read())
base.update(agent_count=300, locality_count=34, burn_in_days=0.0,
            output_mode='calibration', seed=0, horizon_days=7.0)
world = generate_pineland(SimulationConfig.from_dict(base))
simulation = Simulation(world)
simulation.run(until=7.0, max_events=471)
rng = copy.deepcopy(simulation.processes._process_rngs['beliefs'])
for index, person in enumerate(world.persons.values()):
    community = world.social_communities[person.community_id]
    for actor in ('government', 'insurgent'):
        signal = (community.government_cooperation if actor == 'government'
                  else community.insurgent_sympathy)
        noise = rng.normalvariate(0, world.config.observation_noise)
        observed = max(0.0, min(1.0, signal + noise))
        trust = person.trust.get(actor, .2)
        old = person.expected_control.get(actor, .5 if actor == 'government' else .2)
        learning = reference_probability(.12 * trust, 1.0, 1.0)
        updated = max(0.0, min(1.0, old + learning * (observed - old)))
        if index in (65, 237):
            print(index, actor, 'signal', repr(signal), 'noise', repr(noise),
                  'observed', repr(observed), 'trust', repr(trust),
                  'old', repr(old), 'learning', repr(learning),
                  'updated', repr(updated), 'bits', updated.hex())
