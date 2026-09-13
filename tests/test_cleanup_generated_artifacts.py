from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import time


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_generated_artifacts.py"
SPEC = importlib.util.spec_from_file_location("cleanup_generated_artifacts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)


def _age(path: Path, hours: float = 12.0) -> None:
    timestamp = time.time() - hours * 3600.0
    path.touch(exist_ok=True)
    path.chmod(0o666)
    import os

    os.utime(path, (timestamp, timestamp))


def _age_tree(path: Path, hours: float = 12.0) -> None:
    import os

    timestamp = time.time() - hours * 3600.0
    for item in sorted(path.rglob("*"), reverse=True):
        os.utime(item, (timestamp, timestamp))
    os.utime(path, (timestamp, timestamp))


def test_stale_compression_roots_preserve_recent_run_and_cover_research_artifacts(tmp_path: Path) -> None:
    old_run = tmp_path / "studies" / "case" / "runs" / "old_experiment"
    live_run = tmp_path / "studies" / "case" / "runs" / "live_experiment"
    results = tmp_path / "studies" / "case" / "results"
    raw = tmp_path / "studies" / "case" / "data" / "raw"
    processed = tmp_path / "studies" / "case" / "data" / "processed"
    for directory in (old_run, live_run, results, raw, processed):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "artifact.json").write_text("{}", encoding="utf-8")
    for directory in (old_run, results, raw, processed):
        _age_tree(directory)

    cutoff = time.time() - 6 * 3600.0
    candidates = set(cleanup.stale_compression_roots(cutoff, tmp_path))

    assert old_run in candidates
    assert live_run not in candidates
    assert results in candidates
    assert raw in candidates
    assert processed in candidates


def test_disposable_paths_include_common_caches_but_not_entire_tmp(tmp_path: Path) -> None:
    cache = tmp_path / "src" / "pkg" / "__pycache__"
    ruff = tmp_path / ".ruff_cache"
    scratch = tmp_path / "tmp" / "important_notes.txt"
    for path in (cache, ruff):
        path.mkdir(parents=True)
    scratch.parent.mkdir(parents=True)
    scratch.write_text("keep me", encoding="utf-8")

    candidates = set(cleanup.disposable_paths(tmp_path))

    assert cache in candidates
    assert ruff in candidates
    assert scratch.parent not in candidates


def test_disposable_paths_detect_cargo_targets_by_cachedir_marker(tmp_path: Path) -> None:
    root_target = tmp_path / "target-policy-v9"
    nested_target = tmp_path / "studies" / "theory" / "native_probe" / "target-special"
    source_dir = tmp_path / "studies" / "theory" / "native_probe" / "src"
    for target in (root_target, nested_target):
        target.mkdir(parents=True)
        (target / "CACHEDIR.TAG").write_text(
            "Signature: 8a477f597d28d172789f06886806bc55\n",
            encoding="utf-8",
        )
    source_dir.mkdir(parents=True)
    (source_dir / "main.rs").write_text("fn main() {}\n", encoding="utf-8")

    candidates = set(cleanup.disposable_paths(tmp_path))

    assert root_target in candidates
    assert nested_target in candidates
    assert source_dir not in candidates


def test_safe_delete_candidates_refuses_tracked_evidence(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked_dir = tmp_path / "outputs" / "smoke"
    untracked_dir = tmp_path / "src" / "__pycache__"
    tracked_dir.mkdir(parents=True)
    untracked_dir.mkdir(parents=True)
    tracked_file = tracked_dir / "evidence.json"
    tracked_file.write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", tracked_file.relative_to(tmp_path)], cwd=tmp_path, check=True)

    safe, refused = cleanup.safe_delete_candidates([tracked_dir, untracked_dir], tmp_path)

    assert safe == [untracked_dir]
    assert refused == [tracked_dir]


def test_remove_tree_handles_readonly_files(tmp_path: Path) -> None:
    target = tmp_path / "cache"
    target.mkdir()
    item = target / "readonly.pyc"
    item.write_bytes(b"cache")
    item.chmod(0o444)

    cleanup.remove_tree(target)

    assert not target.exists()
