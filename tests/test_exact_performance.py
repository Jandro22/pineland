import copy
from pineland_sim.config import SimulationConfig
from pineland_sim.entities import CommandEdge
from pineland_sim.generator import generate_pineland
from pineland_sim.logistics import command_path
from pineland_sim.physical import recompute_contested_controls
from pineland_sim.reproducibility import decision_state_sha256


def world():
    return generate_pineland(SimulationConfig(seed=821, agent_count=40, locality_count=17))


def test_command_path_cache_matches_uncached_paths_and_does_not_alias():
    w = world()
    w.command_edges = {('a','b'): CommandEdge('a','b','o',.8,2),
                       ('b','c'): CommandEdge('b','c','o',.9,1),
                       ('a','c'): CommandEdge('a','c','o',.5,0)}
    queries = [('o','a','c'), ('o','c','a'), ('o','missing','c'), ('x','a','c'), ('o','a','a')]
    expected = [command_path(w,*q) for q in queries]
    assert [command_path(w,*q) for q in queries] == expected
    command_path(w,*queries[0])[0].clear()
    assert [command_path(w,*q) for q in queries] == expected
    w.command_edges[('a','c')].reliability = 1
    w.command_path_cache.clear()
    changed = command_path(w,*queries[0])
    w.command_edges.clear()
    w.command_path_cache.clear()
    assert command_path(w,*queries[0]) == ([],0,float('inf'))
    assert changed != expected[0]


def test_runtime_physical_indexes_match_reference_after_relocation():
    a = world()
    formation = next(iter(a.formations.values()))
    formation.locality_id = next(k for k in a.localities if k != formation.locality_id)
    b = copy.deepcopy(a)
    a.rebuild_runtime_entity_indexes()
    b.rebuild_runtime_entity_indexes()
    for locality in sorted(a.localities):
        assert recompute_contested_controls(a, locality, 2.) == recompute_contested_controls(
            b, locality, 2., use_runtime_indexes=True
        )
    assert decision_state_sha256(a) == decision_state_sha256(b)



def test_worker_writes_identical_json_and_returns_only_metadata(tmp_path, monkeypatch):
    import importlib.util
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'studies/nepal_2001_2006/scripts/run_untuned_benchmark.py'
    spec = importlib.util.spec_from_file_location('perf_nepal_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = {'runtime_seconds': 1.25, 'contacts': [{'unicode': '\u00e9'}],
               'nested': [1, 0.1, None, {'a': True}]}
    monkeypatch.setattr(module, 'run_seed', lambda *args: payload)
    actual = tmp_path / 'actual.json'
    expected = tmp_path / 'expected.json'
    expected.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    result = module.run_seed_to_file(1, 750, 'E_combined', actual)
    assert actual.read_bytes() == expected.read_bytes()
    assert result == {'completed_seed': 1, 'runtime_seconds': 1.25, 'contacts': 1}
    assert not actual.with_suffix('.tmp').exists()
