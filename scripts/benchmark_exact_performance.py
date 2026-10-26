"""Run separately against baseline and candidate imports; compare hashes, not scores."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--case-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--days', type=float, default=180)
    parser.add_argument('--seed', type=int, default=20011126)
    parser.add_argument('--agents', type=int, default=750)
    args = parser.parse_args()
    root = args.source_root.resolve()
    sys.path.insert(0, str(root / 'src'))
    from pineland_sim.config import SimulationConfig
    from pineland_sim.generator import generate_pineland
    from pineland_sim.simulation import Simulation
    from pineland_sim.reproducibility import (
        canonical_sha256, decision_state_sha256, trajectory_sha256, model_sha256,
    )
    case = json.loads(args.case_file.read_text(encoding='utf-8'))
    config = SimulationConfig(seed=args.seed, agent_count=args.agents,
        locality_count=len(case['localities']), horizon_days=args.days, output_mode='ensemble')
    config.information.observation_retention_days = 90
    config.organization_ecology.observed_active_intervals = {'insurgent': [[0.,args.days]]}
    before = model_sha256(root)
    start = time.perf_counter()
    world = Simulation(generate_pineland(config, empirical_geography=case)).run().world
    elapsed = time.perf_counter() - start
    after = model_sha256(root)
    if before != after:
        raise RuntimeError('source changed during benchmark')
    payload = {'seconds': elapsed, 'model_sha256': before,
        'seed': args.seed, 'days': args.days, 'agents': args.agents,
        'decision_state': decision_state_sha256(world), 'trajectory': trajectory_sha256(world),
        'records': canonical_sha256(world.synthetic_records), 'event_counts': world.event_counts}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(payload))


if __name__ == '__main__':
    main()
