"""Bound Pineland's generated-artifact disk growth without deleting evidence.

Dry-run is the default.  With --apply this script:

* removes known disposable smoke/probe/cache artifacts after a safety age;
* LZX-compresses stale study runs, results, data, and outputs on NTFS;
* skips any directory with recently modified files so live runs are not touched.

The compacted files keep their existing paths and are transparently decompressed
by Windows, so analysis scripts do not need special gzip/zip handling.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]

DISPOSABLE_OUTPUT_NAMES = {
    "smoke",
    "final-smoke",
    "causal-integrity-smoke",
    "causal-integrity-smoke2",
}

CACHE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    "htmlcov",
}


def tree_stats(path: Path) -> tuple[int, int, float]:
    """Return (bytes, files, newest_mtime) for a file tree."""
    if not path.exists():
        return 0, 0, 0.0
    if path.is_file():
        stat = path.stat()
        return stat.st_size, 1, stat.st_mtime
    total = 0
    files = 0
    newest = path.stat().st_mtime
    for base, _, names in os.walk(path):
        for name in names:
            item = Path(base) / name
            try:
                stat = item.stat()
            except OSError:
                continue
            total += stat.st_size
            files += 1
            newest = max(newest, stat.st_mtime)
    return total, files, newest


def old_enough(path: Path, cutoff: float) -> bool:
    return tree_stats(path)[2] < cutoff


def disposable_paths(root: Path = ROOT) -> list[Path]:
    paths: list[Path] = []
    outputs = root / "outputs"
    if outputs.is_dir():
        for child in outputs.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if (
                name in DISPOSABLE_OUTPUT_NAMES
                or (name.startswith("phase") and "smoke" in name)
                or name.startswith("causal-integrity-smoke")
            ):
                paths.append(child)

    # Explicitly disposable exploratory reruns.  Stable/final rescores are kept.
    paths.extend(root.glob("studies/*/runs/**/*_probe"))

    temp_clone = root / "tmp" / "VietnamWarData2"
    if temp_clone.exists():
        paths.append(temp_clone)

    for cache_name in CACHE_DIR_NAMES:
        paths.extend(p for p in root.rglob(cache_name) if p.is_dir())
    return sorted(set(paths))


def _stale_tree_or_children(path: Path, cutoff: float) -> list[Path]:
    """Prefer one stale parent; otherwise return stale immediate children."""
    if not path.is_dir():
        return []
    if old_enough(path, cutoff):
        return [path]
    return [child for child in path.iterdir() if child.is_dir() and old_enough(child, cutoff)]


def stale_compression_roots(cutoff: float, root: Path = ROOT) -> list[Path]:
    roots: list[Path] = []
    for runs in root.glob("studies/*/runs"):
        # Compress at the immediate experiment-directory level.  A live child
        # keeps its own experiment tree recent and therefore excluded.
        for child in runs.iterdir() if runs.is_dir() else ():
            if child.is_dir():
                roots.extend(_stale_tree_or_children(child, cutoff))

    # Results are valuable evidence, so never delete them.  Transparent
    # compression keeps paths and bytes unchanged while bounding disk growth.
    for results in root.glob("studies/*/results"):
        roots.extend(_stale_tree_or_children(results, cutoff))

    # Raw/processed case data are normally immutable or reproducible products.
    # Keeping their paths stable avoids special archive/restore logic.
    for data_kind in ("raw", "processed"):
        for data in root.glob(f"studies/*/data/{data_kind}"):
            if data.is_dir() and old_enough(data, cutoff):
                roots.append(data)

    # Top-level outputs are generated artifacts.  If recent work makes the
    # directory itself young, compact only stale child directories; individual
    # loose files are intentionally left alone rather than racing writers.
    outputs = root / "outputs"
    roots.extend(_stale_tree_or_children(outputs, cutoff))
    return sorted(set(roots))


def compact_ntfs(path: Path) -> None:
    subprocess.run(
        ["compact", "/c", f"/s:{path}", "/i", "/q", "/exe:lzx"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def remove_tree(path: Path) -> None:
    """Remove a disposable tree, including read-only VCS/cache files on Windows."""
    def clear_readonly(function, item, _excinfo) -> None:
        os.chmod(item, stat.S_IWRITE)
        function(item)

    # ``onerror`` is available on the project's Python 3.11 floor.  ``onexc``
    # was only added in Python 3.12.
    shutil.rmtree(path, onerror=clear_readonly)


def contains_tracked_files(path: Path, root: Path = ROOT) -> bool:
    """Return True when Git tracks anything at or below *path*."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return True
    result = subprocess.run(
        ["git", "ls-files", "--", relative.as_posix()],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def safe_delete_candidates(candidates: list[Path], root: Path = ROOT) -> tuple[list[Path], list[Path]]:
    """Partition candidates into deletable paths and tracked-file refusals."""
    safe: list[Path] = []
    refused: list[Path] = []
    for path in candidates:
        if contains_tracked_files(path, root):
            refused.append(path)
        else:
            safe.append(path)
    return safe, refused


def human(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    raise AssertionError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="perform cleanup; default is dry-run")
    parser.add_argument(
        "--safety-age-hours",
        type=float,
        default=6.0,
        help="never delete/compress a tree modified more recently than this",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="delete disposable artifacts but skip NTFS compression",
    )
    args = parser.parse_args()
    if args.safety_age_hours < 0:
        parser.error("--safety-age-hours must be non-negative")

    cutoff = time.time() - args.safety_age_hours * 3600.0
    delete_candidates = [path for path in disposable_paths() if old_enough(path, cutoff)]
    delete, refused = safe_delete_candidates(delete_candidates)
    reclaimable = sum(tree_stats(path)[0] for path in delete)

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'} root={ROOT}")
    print(f"delete_candidates={len(delete)} logical_bytes={human(reclaimable)}")
    for path in delete:
        size, files, _ = tree_stats(path)
        print(f"DELETE  {human(size):>10} {files:6d}  {path.relative_to(ROOT)}")
    for path in refused:
        print(f"REFUSE  tracked files present  {path.relative_to(ROOT)}")

    compression = [] if args.no_compress or os.name != "nt" else stale_compression_roots(cutoff)
    print(f"compress_candidates={len(compression)}")
    for path in compression:
        size, files, _ = tree_stats(path)
        print(f"COMPACT {human(size):>10} {files:6d}  {path.relative_to(ROOT)}")

    if not args.apply:
        return

    # Deepest paths first so deleting a cache never invalidates an outer path.
    for path in sorted(delete, key=lambda p: len(p.parts), reverse=True):
        if path.exists():
            remove_tree(path)
    for path in compression:
        if path.exists():
            compact_ntfs(path)


if __name__ == "__main__":
    main()
