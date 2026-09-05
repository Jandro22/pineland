from contextlib import nullcontext
import copy
import pytest
from pineland_sim.config import SimulationConfig
from pineland_sim.entities import CommandEdge
from pineland_sim.generator import generate_pineland
from pineland_sim.logistics import command_path, command_route_batch
from pineland_sim.physical import physical_refresh_sources, recompute_contested_controls
from pineland_sim.reproducibility import decision_state_sha256


def world():
    return generate_pineland(SimulationConfig(seed=821, agent_count=40, locality_count=17))


def test_command_batch_matches_uncached_paths_and_does_not_alias():
    w = world()
    w.command_edges = {('a','b'): CommandEdge('a','b','o',.8,2),
                       ('b','c'): CommandEdge('b','c','o',.9,1),
                       ('a','c'): CommandEdge('a','c','o',.5,0)}
    queries = [('o','a','c'), ('o','c','a'), ('o','missing','c'), ('x','a','c'), ('o','a','a')]
    expected = [command_path(w,*q) for q in queries]
    with command_route_batch(w):
        assert [command_path(w,*q) for q in queries] == expected
        command_path(w,*queries[0])[0].clear()
        assert [command_path(w,*q) for q in queries] == expected
        # Context-local and world-local: nested use cannot contaminate the outer batch.
        with command_route_batch(world()):
            assert command_path(w,*queries[0]) == expected[0]
    w.command_edges[('a','c')].reliability = 1
    changed = command_path(w,*queries[0])
    with command_route_batch(w):
        assert command_path(w,*queries[0]) == changed
    with pytest.raises(RuntimeError):
        with command_route_batch(w):
            raise RuntimeError('cleanup')
    w.command_edges.clear()
    assert command_path(w,*queries[0]) == ([],0,float('inf'))


def test_refresh_indexes_match_public_helpers_after_relocation():
    a = world()
    formation = next(iter(a.formations.values()))
    formation.locality_id = next(k for k in a.localities if k != formation.locality_id)
    b = copy.deepcopy(a)
    sources = physical_refresh_sources(b, 2.)
    for locality in sorted(a.localities):
        assert recompute_contested_controls(a,locality,2.) == recompute_contested_controls(b,locality,2.,_sources=sources[locality])
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
