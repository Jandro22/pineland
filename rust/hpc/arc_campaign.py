#!/usr/bin/env python3
"""Deterministic ARC/Slurm campaign orchestration for Pineland ensembles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
DEFAULT_PROFILES = HERE / "arc_resource_profiles.json"
SCHEMA = "pineland-arc-campaign-v1"
SUCCESS_SCHEMA = "pineland-arc-task-success-v1"
DEFAULT_BUDGET_SU = 50_000.0
_HASH_CACHE: dict[str, tuple[int, int, str]] = {}


class CampaignError(RuntimeError):
    pass


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_sha256_cached(path: Path) -> str:
    resolved = path.resolve()
    stat = resolved.stat()
    key = str(resolved)
    cached = _HASH_CACHE.get(key)
    signature = (stat.st_size, stat.st_mtime_ns)
    if cached is not None and cached[:2] == signature:
        return cached[2]
    digest = _file_sha256(resolved)
    _HASH_CACHE[key] = (signature[0], signature[1], digest)
    return digest


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CampaignError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CampaignError(f"invalid JSON in {path}: {exc}") from exc


def _safe_campaign_id(value: Any) -> str:
    campaign_id = str(value or "")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if not campaign_id or len(campaign_id) > 80 or any(char not in allowed for char in campaign_id):
        raise CampaignError("campaign_id must contain only letters, digits, '.', '_', and '-'")
    return campaign_id


def _safe_token(value: Any, label: str) -> str:
    token = str(value or "")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if not token or len(token) > 80 or any(char not in allowed for char in token):
        raise CampaignError(f"{label} must contain only letters, digits, '.', '_', and '-'")
    return token


def _config_rows(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise CampaignError("spec.configs must be a non-empty list")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            path = item
            config_id = Path(item).stem
        elif isinstance(item, dict):
            path = str(item.get("path", ""))
            config_id = str(item.get("id") or Path(path).stem)
        else:
            raise CampaignError(f"spec.configs[{index}] must be a path string or object")
        if not path or not config_id:
            raise CampaignError(f"spec.configs[{index}] has an empty id/path")
        config_id = _safe_token(config_id, f"spec.configs[{index}].id")
        rows.append({"id": config_id, "path": path})
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise CampaignError("config ids must be unique")
    return rows


def _seed_rows(value: Any) -> list[int]:
    if not isinstance(value, list) or not value:
        raise CampaignError("spec.seeds must be a non-empty list")
    seeds: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > (2**64 - 1):
            raise CampaignError("all seeds must be unsigned 64-bit integers")
        seeds.append(item)
    if len(set(seeds)) != len(seeds):
        raise CampaignError("seeds must be unique")
    return seeds


def _validate_extra_args(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CampaignError("extra_args must be a list of strings")
    forbidden = ("--output", "--seed", "--days", "--config")
    if any(item == flag or item.startswith(flag + "=") for item in value for flag in forbidden):
        raise CampaignError("extra_args cannot override --output, --seed, or --days")
    return list(value)


def normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CampaignError("campaign spec must be a JSON object")
    campaign_id = _safe_campaign_id(raw.get("campaign_id"))
    command = str(raw.get("command", "run"))
    if command not in {"run", "generate"}:
        raise CampaignError("campaign command must be 'run' or 'generate'")
    binary = str(raw.get("binary", "rust/target/release/pineland"))
    if not binary:
        raise CampaignError("binary cannot be empty")
    configs = _config_rows(raw.get("configs"))
    seeds = _seed_rows(raw.get("seeds"))
    days = raw.get("days")
    if days is not None:
        if isinstance(days, bool) or not isinstance(days, (int, float)) or not (float(days) > 0):
            raise CampaignError("days must be a positive number")
        days = float(days)
    expected_files = raw.get("expected_files", ["summary.json", "run_metadata.json", "checkpoint_*/manifest.json"])
    if not isinstance(expected_files, list) or not expected_files or not all(
        isinstance(item, str) and item for item in expected_files
    ):
        raise CampaignError("expected_files must be a non-empty list of glob strings")
    if any(Path(item).is_absolute() or ".." in Path(item).parts for item in expected_files):
        raise CampaignError("expected_files patterns must stay inside the task output directory")
    budget_su_cap = float(raw.get("budget_su_cap", DEFAULT_BUDGET_SU))
    if budget_su_cap <= 0:
        raise CampaignError("budget_su_cap must be positive")
    return {
        "schema": SCHEMA,
        "campaign_id": campaign_id,
        "binary": binary,
        "command": command,
        "configs": configs,
        "seeds": seeds,
        "days": days,
        "extra_args": _validate_extra_args(raw.get("extra_args")),
        "expected_files": expected_files,
        "budget_su_cap": budget_su_cap,
    }


def expand_tasks(spec: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for config in spec["configs"]:
        for seed in spec["seeds"]:
            task_id = len(tasks)
            key = f'{config["id"]}-seed-{seed}'
            argv = [spec["binary"], spec["command"], config["path"], "--seed", str(seed)]
            if spec["days"] is not None:
                argv.extend(["--days", format(spec["days"], ".15g")])
            argv.extend(spec["extra_args"])
            argv.extend(["--output", "{output}"])
            base = {
                "task_id": task_id,
                "task_key": key,
                "campaign_id": spec["campaign_id"],
                "config_id": config["id"],
                "config_path": config["path"],
                "config_sha256": config["sha256"],
                "binary_sha256": spec["binary_sha256"],
                "seed": seed,
                "argv": argv,
                "expected_files": spec["expected_files"],
            }
            task = dict(base)
            task["fingerprint"] = _digest(base)
            tasks.append(task)
    return tasks


def build_campaign(spec_path: Path, manifest_dir: Path, repo_root: Path) -> dict[str, Any]:
    spec = normalize_spec(_load_json(spec_path))
    binary = _resolve_repo_path(repo_root, spec["binary"])
    if not binary.is_file():
        raise CampaignError(f"campaign binary does not exist: {binary}")
    locked_configs: list[dict[str, str]] = []
    for config in spec["configs"]:
        config_path = _resolve_repo_path(repo_root, config["path"])
        if not config_path.is_file():
            raise CampaignError(f"campaign config does not exist: {config_path}")
        locked_configs.append(
            {
                **config,
                "sha256": _file_sha256(config_path),
            }
        )
    spec = {
        **spec,
        "binary_sha256": _file_sha256(binary),
        "configs": locked_configs,
    }
    tasks = expand_tasks(spec)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    task_lines = b"".join(_json_bytes(task) for task in tasks)
    tasks_path = manifest_dir / "tasks.jsonl"
    tmp = tasks_path.with_name(f".{tasks_path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(task_lines)
    os.replace(tmp, tasks_path)
    _atomic_json(manifest_dir / "campaign_spec.json", spec)
    manifest = {
        "schema": SCHEMA,
        "campaign_id": spec["campaign_id"],
        "task_count": len(tasks),
        "tasks_file": "tasks.jsonl",
        "tasks_sha256": hashlib.sha256(task_lines).hexdigest(),
        "spec_sha256": _digest(spec),
        "budget_su_cap": spec["budget_su_cap"],
    }
    manifest["manifest_sha256"] = _digest(manifest)
    _atomic_json(manifest_dir / "campaign_manifest.json", manifest)
    return manifest


def load_campaign(manifest_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _load_json(manifest_dir / "campaign_manifest.json")
    if manifest.get("schema") != SCHEMA:
        raise CampaignError(f"unsupported manifest schema: {manifest.get('schema')!r}")
    expected_manifest = dict(manifest)
    stored_manifest_hash = expected_manifest.pop("manifest_sha256", None)
    if stored_manifest_hash != _digest(expected_manifest):
        raise CampaignError("campaign_manifest.json hash does not verify")
    tasks_path = manifest_dir / str(manifest.get("tasks_file", "tasks.jsonl"))
    data = tasks_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest.get("tasks_sha256"):
        raise CampaignError("tasks.jsonl hash does not match campaign manifest")
    tasks: list[dict[str, Any]] = []
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CampaignError(f"invalid task JSON on line {line_number}") from exc
        fingerprint = task.get("fingerprint")
        base = dict(task)
        base.pop("fingerprint", None)
        if fingerprint != _digest(base):
            raise CampaignError(f"task {task.get('task_id')} fingerprint does not verify")
        tasks.append(task)
    if len(tasks) != int(manifest.get("task_count", -1)):
        raise CampaignError("manifest task_count does not match tasks.jsonl")
    if [task.get("task_id") for task in tasks] != list(range(len(tasks))):
        raise CampaignError("task ids must be contiguous and zero-based")
    return manifest, tasks


def _resolve_repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (repo_root / path).resolve()


def _attempt_name() -> str:
    job = os.environ.get("SLURM_ARRAY_JOB_ID") or os.environ.get("SLURM_JOB_ID")
    task = os.environ.get("SLURM_ARRAY_TASK_ID")
    restart = os.environ.get("SLURM_RESTART_COUNT", "0")
    if job:
        suffix = f"-task-{task}" if task is not None else ""
        return f"job-{job}{suffix}-restart-{restart}"
    return f"local-{int(time.time())}-{os.getpid()}"


def _matching_files(output: Path, patterns: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        matches = sorted(path for path in output.glob(pattern) if path.is_file())
        if not matches:
            raise CampaignError(f"expected output pattern {pattern!r} matched no files in {output}")
        files.extend(matches)
    unique: dict[str, Path] = {}
    for path in files:
        unique[str(path.relative_to(output))] = path
    return [unique[key] for key in sorted(unique)]


def verify_success(task_root: Path, task: dict[str, Any]) -> dict[str, Any] | None:
    marker_path = task_root / "_SUCCESS.json"
    if not marker_path.is_file():
        return None
    marker = _load_json(marker_path)
    if marker.get("schema") != SUCCESS_SCHEMA:
        raise CampaignError(f"invalid success marker schema in {marker_path}")
    if marker.get("task_fingerprint") != task["fingerprint"]:
        raise CampaignError(f"success marker fingerprint mismatch for task {task['task_id']}")
    if marker.get("binary_sha256") != task["binary_sha256"]:
        raise CampaignError(f"success marker binary hash mismatch for task {task['task_id']}")
    if marker.get("config_sha256") != task["config_sha256"]:
        raise CampaignError(f"success marker config hash mismatch for task {task['task_id']}")
    attempt = task_root / str(marker.get("attempt", ""))
    output = attempt / "output"
    if not output.is_dir():
        raise CampaignError(f"success marker points to missing output directory: {output}")
    recorded = marker.get("files")
    if not isinstance(recorded, list) or not recorded:
        raise CampaignError(f"success marker has no file hashes: {marker_path}")
    for item in recorded:
        path = output / str(item.get("path", ""))
        if not path.is_file() or _file_sha256(path) != item.get("sha256"):
            raise CampaignError(f"completed task artifact changed or disappeared: {path}")
    return marker


def run_task(
    manifest_dir: Path,
    task_id: int,
    repo_root: Path,
    scratch_root: Path,
    *,
    dry_run: bool = False,
) -> int:
    manifest, tasks = load_campaign(manifest_dir)
    if task_id < 0 or task_id >= len(tasks):
        raise CampaignError(f"task id {task_id} outside 0..{len(tasks) - 1}")
    task = tasks[task_id]
    binary = _resolve_repo_path(repo_root, task["argv"][0])
    if not binary.is_file():
        raise CampaignError(f"Pineland binary does not exist: {binary}")
    actual_binary_hash = _file_sha256_cached(binary)
    if actual_binary_hash != task["binary_sha256"]:
        raise CampaignError(
            f"Pineland binary hash drift for task {task_id}: "
            f"expected {task['binary_sha256']}, got {actual_binary_hash}"
        )
    config = _resolve_repo_path(repo_root, task["config_path"])
    if not config.is_file():
        raise CampaignError(f"task config does not exist: {config}")
    actual_config_hash = _file_sha256_cached(config)
    if actual_config_hash != task["config_sha256"]:
        raise CampaignError(
            f"config hash drift for task {task_id}: "
            f"expected {task['config_sha256']}, got {actual_config_hash}"
        )
    campaign_root = scratch_root / manifest["campaign_id"]
    task_root = campaign_root / "tasks" / f"{task_id:06d}-{task['task_key']}"
    task_root.mkdir(parents=True, exist_ok=True)
    completed = verify_success(task_root, task)
    if completed is not None:
        print(json.dumps({"status": "already_complete", "task_id": task_id, "task_root": str(task_root)}))
        return 0

    attempt_name = _attempt_name()
    attempt = task_root / attempt_name
    serial = 1
    while attempt.exists():
        serial += 1
        attempt = task_root / f"{attempt_name}-{serial}"
    output = attempt / "output"
    attempt.mkdir(parents=True)

    argv: list[str] = []
    for index, value in enumerate(task["argv"]):
        if value == "{output}":
            argv.append(str(output))
        elif index == 0:
            argv.append(str(_resolve_repo_path(repo_root, value)))
        elif value == task["config_path"]:
            argv.append(str(_resolve_repo_path(repo_root, value)))
        else:
            argv.append(str(value))

    command_record = {
        "task_id": task_id,
        "task_fingerprint": task["fingerprint"],
        "argv": argv,
        "cwd": str(repo_root),
        "host": socket.gethostname(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
        "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
    }
    _atomic_json(attempt / "command.json", command_record)
    if dry_run:
        print(shlex.join(argv))
        return 0

    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PINELAND_CAMPAIGN_ID"] = manifest["campaign_id"]
    env["PINELAND_TASK_ID"] = str(task_id)
    env["PINELAND_TASK_FINGERPRINT"] = task["fingerprint"]
    start = time.monotonic()
    with (attempt / "stdout.log").open("wb") as stdout, (attempt / "stderr.log").open("wb") as stderr:
        process = subprocess.run(argv, cwd=repo_root, env=env, stdout=stdout, stderr=stderr, check=False)
    elapsed = time.monotonic() - start
    status = {
        "task_id": task_id,
        "task_fingerprint": task["fingerprint"],
        "returncode": process.returncode,
        "wall_seconds": elapsed,
    }
    _atomic_json(attempt / "attempt_status.json", status)
    if process.returncode != 0:
        print(json.dumps({"status": "failed", **status, "attempt": str(attempt)}), file=sys.stderr)
        return process.returncode or 1

    files = _matching_files(output, task["expected_files"])
    file_records = [
        {"path": str(path.relative_to(output)).replace("\\", "/"), "sha256": _file_sha256(path)}
        for path in files
    ]
    marker = {
        "schema": SUCCESS_SCHEMA,
        "campaign_id": manifest["campaign_id"],
        "task_id": task_id,
        "task_fingerprint": task["fingerprint"],
        "attempt": attempt.name,
        "wall_seconds": elapsed,
        "binary_sha256": actual_binary_hash,
        "config_sha256": actual_config_hash,
        "files": file_records,
    }
    existing = verify_success(task_root, task)
    if existing is None:
        _atomic_json(task_root / "_SUCCESS.json", marker)
    print(json.dumps({"status": "complete", "task_id": task_id, "task_root": str(task_root)}))
    return 0


def run_bundle(
    manifest_dir: Path,
    bundle_id: int,
    tasks_per_bundle: int,
    repo_root: Path,
    scratch_root: Path,
    *,
    dry_run: bool = False,
) -> int:
    if tasks_per_bundle < 1:
        raise CampaignError("tasks_per_bundle must be positive")
    _manifest, tasks = load_campaign(manifest_dir)
    bundle_count = (len(tasks) + tasks_per_bundle - 1) // tasks_per_bundle
    if bundle_id < 0 or bundle_id >= bundle_count:
        raise CampaignError(f"bundle id {bundle_id} outside 0..{bundle_count - 1}")
    start = bundle_id * tasks_per_bundle
    stop = min(start + tasks_per_bundle, len(tasks))
    for task_id in range(start, stop):
        code = run_task(
            manifest_dir,
            task_id,
            repo_root,
            scratch_root,
            dry_run=dry_run,
        )
        if code != 0:
            return code
    return 0


def collect_campaign(
    manifest_dir: Path,
    scratch_root: Path,
    output: Path,
    *,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    manifest, tasks = load_campaign(manifest_dir)
    campaign_root = scratch_root / manifest["campaign_id"]
    completed: list[dict[str, Any]] = []
    missing: list[int] = []
    for task in tasks:
        task_root = campaign_root / "tasks" / f"{task['task_id']:06d}-{task['task_key']}"
        marker = verify_success(task_root, task)
        if marker is None:
            missing.append(task["task_id"])
            continue
        completed.append(
            {
                "task_id": task["task_id"],
                "task_key": task["task_key"],
                "config_id": task["config_id"],
                "config_sha256": task["config_sha256"],
                "seed": task["seed"],
                "task_fingerprint": task["fingerprint"],
                "task_root": str(task_root),
                "attempt": marker["attempt"],
                "wall_seconds": marker["wall_seconds"],
                "binary_sha256": marker["binary_sha256"],
                "files": marker["files"],
            }
        )
    report = {
        "schema": "pineland-arc-collection-v1",
        "campaign_id": manifest["campaign_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "expected_tasks": len(tasks),
        "completed_tasks": len(completed),
        "missing_task_ids": missing,
        "complete": not missing,
        "results": completed,
    }
    _atomic_json(output, report)
    if missing and not allow_incomplete:
        raise CampaignError(f"campaign incomplete: {len(missing)} of {len(tasks)} tasks missing")
    return report


def _parse_walltime(value: str) -> float:
    try:
        if "-" in value:
            days_text, clock = value.split("-", 1)
            days = int(days_text)
        else:
            days = 0
            clock = value
        hours_text, minutes_text, seconds_text = clock.split(":")
        return days * 24 + int(hours_text) + int(minutes_text) / 60 + int(seconds_text) / 3600
    except (ValueError, TypeError) as exc:
        raise CampaignError(f"unsupported walltime format {value!r}; expected [D-]HH:MM:SS") from exc


def load_profile(profile_file: Path, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    document = _load_json(profile_file)
    profiles = document.get("profiles", {})
    if name not in profiles:
        raise CampaignError(f"unknown resource profile {name!r}; choices: {', '.join(sorted(profiles))}")
    profile = dict(profiles[name])
    profile["name"] = name
    return document, profile


def budget_projection(array_elements: int, profile: dict[str, Any]) -> dict[str, float]:
    hours = _parse_walltime(str(profile["walltime"]))
    per_hour = float(profile["billing_su_per_hour"])
    return {
        "task_walltime_hours": hours,
        "billing_su_per_hour": per_hour,
        "worst_case_su": array_elements * hours * per_hour,
    }


def submit_campaign(
    manifest_dir: Path,
    repo_root: Path,
    scratch_root: Path,
    profile_file: Path,
    profile_name: str,
    *,
    max_concurrent: int | None,
    tasks_per_array_element: int | None,
    budget_cap_su: float | None,
    allow_budget_overrun: bool,
    dry_run: bool,
) -> dict[str, Any]:
    manifest, tasks = load_campaign(manifest_dir)
    profile_doc, profile = load_profile(profile_file, profile_name)
    count = len(tasks)
    if count == 0:
        raise CampaignError("cannot submit an empty campaign")
    concurrency = int(max_concurrent or profile["max_concurrent"])
    if concurrency < 1:
        raise CampaignError("max_concurrent must be positive")
    tasks_per_element = int(tasks_per_array_element or profile.get("tasks_per_array_element", 1))
    if tasks_per_element < 1:
        raise CampaignError("tasks_per_array_element must be positive")
    array_elements = (count + tasks_per_element - 1) // tasks_per_element
    projection = budget_projection(array_elements, profile)
    cap = float(budget_cap_su if budget_cap_su is not None else manifest.get("budget_su_cap", DEFAULT_BUDGET_SU))
    if projection["worst_case_su"] > cap and not allow_budget_overrun:
        raise CampaignError(
            f"worst-case reservation is {projection['worst_case_su']:.1f} SU, above the "
            f"{cap:.1f} SU campaign cap; reduce tasks/walltime, use a preemptable profile, "
            "or pass --allow-budget-overrun explicitly"
        )
    account = str(profile_doc.get("account", ""))
    if not account:
        raise CampaignError("resource profile document has no account")
    host = socket.gethostname().lower()
    observed_cluster = next(
        (name for name in ("tinkercliffs", "owl", "falcon") if name in host),
        None,
    )
    declared_cluster = str(profile.get("cluster", "")).lower()
    if observed_cluster is not None and declared_cluster != observed_cluster:
        raise CampaignError(
            f"resource profile {profile_name!r} is for {declared_cluster}, "
            f"but this login host appears to be {observed_cluster}"
        )
    slurm_script = HERE / "arc_array.sbatch"
    logs = manifest_dir / "slurm_logs"
    logs.mkdir(parents=True, exist_ok=True)
    export = ",".join(
        [
            "ALL",
            f"PINELAND_MANIFEST_DIR={manifest_dir.resolve()}",
            f"PINELAND_REPO_ROOT={repo_root.resolve()}",
            f"PINELAND_SCRATCH_ROOT={scratch_root}",
            f"PINELAND_TASKS_PER_ARRAY={tasks_per_element}",
        ]
    )
    argv = [
        "sbatch",
        f"--account={account}",
        f"--partition={profile['partition']}",
        "--nodes=1",
        "--ntasks=1",
        f"--cpus-per-task={int(profile['cpus_per_task'])}",
        f"--mem={int(profile['memory_gb'])}G",
        f"--time={profile['walltime']}",
        f"--array=0-{array_elements - 1}%{concurrency}",
        f"--output={logs / 'slurm-%A_%a.out'}",
        f"--error={logs / 'slurm-%A_%a.err'}",
        f"--export={export}",
        str(slurm_script),
    ]
    summary = {
        "campaign_id": manifest["campaign_id"],
        "profile": profile_name,
        "account": account,
        "tasks": count,
        "array_elements": array_elements,
        "tasks_per_array_element": tasks_per_element,
        "max_concurrent": concurrency,
        "budget_cap_su": cap,
        **projection,
        "command": shlex.join(argv),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if dry_run:
        return summary
    if shutil.which("sbatch") is None:
        raise CampaignError("sbatch is not on PATH; submit from an ARC login node")
    completed = subprocess.run(argv, cwd=repo_root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise CampaignError(f"sbatch failed: {completed.stderr.strip() or completed.stdout.strip()}")
    summary["sbatch_stdout"] = completed.stdout.strip()
    _atomic_json(manifest_dir / "last_submission.json", summary)
    print(completed.stdout.strip())
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--spec", type=Path, required=True)
    build.add_argument("--manifest-dir", type=Path, required=True)
    build.add_argument("--repo-root", type=Path, required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--manifest-dir", type=Path, required=True)

    run = sub.add_parser("run-task")
    run.add_argument("--manifest-dir", type=Path, required=True)
    run.add_argument("--task-id", type=int)
    run.add_argument("--repo-root", type=Path, required=True)
    run.add_argument("--scratch-root", type=Path)
    run.add_argument("--dry-run", action="store_true")

    bundle = sub.add_parser("run-bundle")
    bundle.add_argument("--manifest-dir", type=Path, required=True)
    bundle.add_argument("--bundle-id", type=int)
    bundle.add_argument("--tasks-per-bundle", type=int, required=True)
    bundle.add_argument("--repo-root", type=Path, required=True)
    bundle.add_argument("--scratch-root", type=Path)
    bundle.add_argument("--dry-run", action="store_true")

    collect = sub.add_parser("collect")
    collect.add_argument("--manifest-dir", type=Path, required=True)
    collect.add_argument("--scratch-root", type=Path)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--allow-incomplete", action="store_true")

    submit = sub.add_parser("submit")
    submit.add_argument("--manifest-dir", type=Path, required=True)
    submit.add_argument("--repo-root", type=Path, required=True)
    submit.add_argument("--scratch-root", type=Path)
    submit.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    submit.add_argument("--profile", required=True)
    submit.add_argument("--max-concurrent", type=int)
    submit.add_argument("--tasks-per-array-element", type=int)
    submit.add_argument("--budget-cap-su", type=float)
    submit.add_argument("--allow-budget-overrun", action="store_true")
    submit.add_argument("--dry-run", action="store_true")
    return parser


def _scratch_root(value: Path | None) -> Path:
    if value is not None:
        return value
    user = os.environ.get("USER") or os.environ.get("USERNAME")
    if not user:
        raise CampaignError("--scratch-root is required when USER is unavailable")
    return Path("/scratch") / user / "pineland"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            manifest = build_campaign(args.spec, args.manifest_dir, args.repo_root.resolve())
            print(json.dumps(manifest, indent=2, sort_keys=True))
        elif args.command == "validate":
            manifest, tasks = load_campaign(args.manifest_dir)
            print(json.dumps({"status": "valid", "campaign_id": manifest["campaign_id"], "tasks": len(tasks)}))
        elif args.command == "run-task":
            task_id = args.task_id
            if task_id is None:
                raw = os.environ.get("SLURM_ARRAY_TASK_ID")
                if raw is None:
                    raise CampaignError("--task-id is required outside a Slurm array")
                task_id = int(raw)
            return run_task(
                args.manifest_dir.resolve(),
                task_id,
                args.repo_root.resolve(),
                _scratch_root(args.scratch_root),
                dry_run=args.dry_run,
            )
        elif args.command == "run-bundle":
            bundle_id = args.bundle_id
            if bundle_id is None:
                raw = os.environ.get("SLURM_ARRAY_TASK_ID")
                if raw is None:
                    raise CampaignError("--bundle-id is required outside a Slurm array")
                bundle_id = int(raw)
            return run_bundle(
                args.manifest_dir.resolve(),
                bundle_id,
                args.tasks_per_bundle,
                args.repo_root.resolve(),
                _scratch_root(args.scratch_root),
                dry_run=args.dry_run,
            )
        elif args.command == "collect":
            report = collect_campaign(
                args.manifest_dir.resolve(),
                _scratch_root(args.scratch_root),
                args.output,
                allow_incomplete=args.allow_incomplete,
            )
            print(json.dumps({key: report[key] for key in ("campaign_id", "expected_tasks", "completed_tasks", "complete")}))
        elif args.command == "submit":
            submit_campaign(
                args.manifest_dir.resolve(),
                args.repo_root.resolve(),
                _scratch_root(args.scratch_root),
                args.profiles.resolve(),
                args.profile,
                max_concurrent=args.max_concurrent,
                tasks_per_array_element=args.tasks_per_array_element,
                budget_cap_su=args.budget_cap_su,
                allow_budget_overrun=args.allow_budget_overrun,
                dry_run=args.dry_run,
            )
        return 0
    except (CampaignError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
