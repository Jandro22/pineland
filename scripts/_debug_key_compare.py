import hashlib, json, os, pathlib, subprocess, tempfile
import struct
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
from certify_rust_initialization import python_components

root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / 'scenarios' / 'baseline.json').read_text())
base.update(agent_count=300, locality_count=34, burn_in_days=0.0, output_mode='calibration', seed=0, horizon_days=30.0)
config = SimulationConfig.from_dict(base)
world = generate_pineland(config)
sim = Simulation(world)
sim.run(until=30.0)
org_ids = list(sim.world.organizations)
locality_ids = list(sim.world.localities)
org_index = {value: index for index, value in enumerate(org_ids)}
loc_index = {value: index for index, value in enumerate(locality_ids)}
formation_ids = list(sim.world.formations)
formation_index = {value: index for index, value in enumerate(formation_ids)}
post_ids = list(sim.world.security_posts)
post_index = {value: index for index, value in enumerate(post_ids)}
community_ids = sorted(sim.world.social_communities)
auxiliary_ids = sorted(set(community_ids) | {f'ADMIN:{l}' for l in locality_ids} | {f'ELITE:{c}' for c in community_ids} | {f'ELITE-CAP:{l}' for l in locality_ids} | {f'INTERPRETER-CAP:{l}' for l in locality_ids})
auxiliary_index = {value: index for index, value in enumerate(auxiliary_ids)}
command_ids = sorted(f'CMD:{o}' for o in org_ids)
command_index = {value: index for index, value in enumerate(command_ids)}
fixed = {(o, t, l) for o in org_ids for l in locality_ids for t in ('insurgent' if o == 'insurgent' else 'government', 'government' if o == 'insurgent' else 'insurgent')}
def dyn(o):
    if o in formation_index: return len(org_ids) + formation_index[o]
    if o in post_index: return len(org_ids) + len(formation_ids) + post_index[o]
    if o in auxiliary_index: return len(org_ids) + len(formation_ids) + len(post_ids) + auxiliary_index[o]
    return len(org_ids) + len(formation_ids) + len(post_ids) + len(auxiliary_ids) + command_index[o]
dynamic = sorted((key for key in sim.world.control_beliefs if key not in fixed), key=lambda key: (dyn(key[0]), org_index[key[1]], loc_index[key[2]]))
py = []
for o in org_ids:
    for l in locality_ids:
        py.extend([{'observer': org_index[o], 'target': org_index['insurgent'], 'locality': loc_index[l], 'kind': 0}, {'observer': org_index[o], 'target': org_index['insurgent'] if o == 'insurgent' else org_index['government'], 'locality': loc_index[l], 'kind': 1}, {'observer': org_index[o], 'target': org_index['government'] if o == 'insurgent' else org_index['insurgent'], 'locality': loc_index[l], 'kind': 2}])
for o, t, l in dynamic:
    py.append({'observer': dyn(o), 'target': org_index[t], 'locality': loc_index[l], 'kind': 3})
print('py counts', len(py), len(sim.world.beliefs), len(sim.world.control_beliefs), 'dynamic', len(dynamic))
with tempfile.TemporaryDirectory() as d:
    path = pathlib.Path(d) / 'config.json'
    path.write_text(json.dumps(base))
    env = os.environ.copy(); env['PINELAND_CERT_DEBUG'] = '1'; env['PINELAND_EVENT_TRACE'] = '1'
    completed = subprocess.run([str(root/'rust/target/release/pineland.exe'), 'certify-trajectory', '--config', str(path), '--seed', '0', '--until', '30'], cwd=root, env=env, text=True, capture_output=True, check=True)
    raw = completed.stdout
    native_event_trace = [line for line in completed.stderr.splitlines() if line.startswith('EVENT ')]
native_payload = json.loads(raw)
native = json.loads(raw)['debug_transition_state']['belief_keys']
native_debug = native_payload['debug_transition_state']
print('native count', len(native))
print('event counts', sim.scheduler._counter if hasattr(sim.scheduler, '_counter') else 'python-counter-unknown', native_payload.get('events_processed'), native_payload.get('actual_time'))
print('native counts', native_payload.get('counts'))
belief_rng_state = sim.processes._process_rngs['beliefs'].getstate()
belief_rng_bytes = bytearray(struct.pack('<624I', *belief_rng_state[1][:624]))
belief_rng_bytes.extend(struct.pack('<I', belief_rng_state[1][624]))
if belief_rng_state[2] is None:
    belief_rng_bytes.append(0)
else:
    belief_rng_bytes.append(1)
    belief_rng_bytes.extend(struct.pack('<d', belief_rng_state[2]))
print('belief rng digest', hashlib.sha256(belief_rng_bytes).hexdigest(),
      native_payload['rng_streams'].get('process:beliefs'))
print('python event log tail', [(entry.time, entry.event_type) for entry in sim.world.event_log[-35:]])
print('native event trace tail', native_event_trace[-35:])
print('native head', native[:3])
print('py head', py[:3])
print('native tail', native[-10:])
print('py tail', py[-10:])
print('first raw', next(((i,a,b) for i,(a,b) in enumerate(zip(py,native)) if a != b), None))
print('set only py', sorted(set(tuple(x.values()) for x in py)-set(tuple(x.values()) for x in native))[:10])
print('set only native', sorted(set(tuple(x.values()) for x in native)-set(tuple(x.values()) for x in py))[:10])
print('dynamic py', dynamic)
print('dynamic native', [row for row in native if row['kind'] == 3])
py_org_index = {value: index for index, value in enumerate(org_ids)}
py_people_organization = [py_org_index.get(person.organization_id, 2**32 - 1) for person in world.persons.values()]
py_people_armed_fraction = [person.armed_fraction for person in world.persons.values()]
py_members = [
    sum(
        person.weight * person.armed_fraction
        for person in world.persons.values()
        if person.organization_id == organization_id
    )
    for organization_id in org_ids
]
native_orgs = native_debug['people_organization']
native_fractions = native_debug['people_armed_fraction']
org_mismatches = [
    (i, expected, actual)
    for i, (expected, actual) in enumerate(zip(py_people_organization, native_orgs))
    if expected != actual
]
fraction_mismatches = [
    (i, expected, actual)
    for i, (expected, actual) in enumerate(zip(py_people_armed_fraction, native_fractions))
    if expected != actual
]
print('people organization mismatches', len(org_mismatches), org_mismatches[:10])
print('armed fraction mismatches', len(fraction_mismatches), fraction_mismatches[:10])
print('py exact members', list(zip(org_ids, py_members)))
print('py forms', [(f.formation_id, f.locality_id, f.personnel, f.supply_stock, f.supply_capacity) for f in world.formations.values()])
print('native members', native_debug['organization_member_population'])
native_expected_control = native_debug['people_expected_control']
python_expected_control = [
    person.expected_control.get(actor, 0.2 if actor == 'insurgent' else 0.5)
    for person in world.persons.values()
    for actor in ('government', 'insurgent')
]
expected_control_mismatches = [
    (i, expected, actual)
    for i, (expected, actual) in enumerate(zip(python_expected_control, native_expected_control))
    if expected != actual
]
print('expected control mismatches', len(expected_control_mismatches), expected_control_mismatches[:10])
for person in (65, 237):
    print('expected control row', person, native_expected_control[person * 2:person * 2 + 2],
          python_expected_control[person * 2:person * 2 + 2])
    community = world.social_communities[list(world.persons.values())[person].community_id]
    native_community = native_debug['community_government_cooperation']
    native_insurgent = native_debug['community_insurgent_sympathy']
    print('community row', person, community.community_id, repr(community.government_cooperation),
          repr(native_community[int(community.community_id[1:])]),
          repr(community.insurgent_sympathy), repr(native_insurgent[int(community.community_id[1:])]))
py_sources = [
    (py_org_index[source.organization_id], loc_index[source.locality_id],
     source.production_per_day, source.capacity, source.stock)
    for source in world.supply_sources.values()
]
native_sources = [
    (row['organization'], row['locality'], row['production'], row['capacity'], row['stock'])
    for row in native_debug['logistics']
]
source_mismatches = [
    (i, expected, actual)
    for i, (expected, actual) in enumerate(zip(py_sources, native_sources))
    if expected != actual
]
print('source mismatches', len(source_mismatches), source_mismatches[:5])
for i, expected, actual in source_mismatches[:5]:
    print('source mismatch bits', i,
          [struct.unpack('Q', struct.pack('d', value))[0] if isinstance(value, float) else value for value in expected],
          [struct.unpack('Q', struct.pack('d', value))[0] if isinstance(value, float) else value for value in actual])
print('python active shipments', [
    (shipment.shipment_id, shipment.source_id, shipment.formation_id,
     shipment.quantity_sent, shipment.quantity_deliverable, shipment.arrives_at)
    for shipment in world.supply_shipments.values()
    if shipment.status == 'in_transit'
])
print('python formation supply', [
    (formation.formation_id, formation.supply_stock, formation.supply_capacity,
     formation.sustainment, formation.command)
    for formation in world.formations.values()
])
print('native formation supply', [
    (row['index'], row['supply_stock'], row['supply_capacity'],
     row['sustainment'], row['command'])
    for row in native_debug['formations']
])
python_component_values = python_components(world, sim)
component_mismatches = [
    (key, python_component_values[key], native_payload['components'].get(key))
    for key in python_component_values
    if python_component_values[key] != native_payload['components'].get(key)
]
print('component mismatches', len(component_mismatches))
for item in component_mismatches[:20]:
    print('component mismatch', item)
