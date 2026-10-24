"""Run one bundle of campaign tasks on one node, in parallel, with task-level recovery.

Each task writes to <scratch>/tasks/<id>/ and publishes _SUCCESS.json (with the
SHA-256 of its outputs) only after the harness exits cleanly. Completed tasks
are skipped on requeue; failed attempts keep their log for diagnosis.

  python run_bundle.py --campaign DIR --binary BIN --scratch DIR --bundle K --bundle-size N [--workers P]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(task: dict, campaign: Path, binary: str, scratch: Path) -> str:
    out = scratch / "tasks" / f"{task['id']:06d}"
    marker = out / "_SUCCESS.json"
    if marker.exists():
        return "skip"
    out.mkdir(parents=True, exist_ok=True)
    argv = [binary, "--stage4-contract", str(campaign / task["contract"]),
            "--cell-index", str(task["cell_index"]), "--seed", str(task["seed"]),
            "--output", str(out / "w.csv"), "--trajectory-output", str(out / "t.csv"),
            "--allow-dirty", "--allow-unfrozen", "--execute"]
    if task.get("locality"):
        argv += ["--locality-output", str(out / "localities.csv")]
    env = dict(os.environ, PINELAND_NO_DEGENERACY_GUARD="1", RAYON_NUM_THREADS="1")
    start = time.time()
    with (out / "run.log").open("w") as log:
        code = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
    if code != 0 or not (out / "w.csv").exists():
        return f"fail {task['id']} code={code}"
    products = {p.name: sha(p) for p in sorted(out.iterdir()) if p.suffix == ".csv"}
    tmp = out / "_SUCCESS.tmp"
    tmp.write_text(json.dumps(dict(task=task, seconds=round(time.time() - start, 1), products=products)))
    tmp.replace(marker)
    return "ok"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--bundle", type=int, required=True)
    ap.add_argument("--bundle-size", type=int, required=True)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    a = ap.parse_args()
    lines = (a.campaign / "tasks.jsonl").read_text().splitlines()
    chunk = [json.loads(x) for x in lines[a.bundle * a.bundle_size:(a.bundle + 1) * a.bundle_size]]
    # Longest-first is unknown in advance; interleave variants so one slow block does not serialize.
    chunk.sort(key=lambda t: (t["seed"], t["cell_index"]))
    tally: dict[str, int] = {}
    with cf.ThreadPoolExecutor(a.workers) as pool:
        for result in pool.map(lambda t: run(t, a.campaign, a.binary, a.scratch), chunk):
            key = result.split()[0]
            tally[key] = tally.get(key, 0) + 1
            if key == "fail":
                print(result, flush=True)
    print(f"bundle {a.bundle}: {tally}", flush=True)
    if tally.get("fail"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
