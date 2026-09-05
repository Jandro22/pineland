"""Bound Pineland's generated-artifact disk growth without deleting evidence.

Dry-run is the default.  With --apply this script:

* removes known disposable smoke/probe/cache artifacts after a safety age;
* LZX-compresses stale study run directories and raw-source directories on NTFS;
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


def disposable_paths() -> list[Path]:
    paths: list[Path] = []
    outputs = ROOT / "outputs"
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
    paths.extend(ROOT.glob("studies/*/runs/**/*_probe"))

    temp_clone = ROOT / "tmp" / "VietnamWarData2"
    if temp_clone.exists():
        paths.append(temp_clone)

    for cache_name in ("__pycache__", ".pytest_cache"):
        paths.extend(p for p in ROOT.rglob(cache_name) if p.is_dir())
    return sorted(set(paths))


def stale_compression_roots(cutoff: float) -> list[Path]:
    roots: list[Path] = []
    for runs in ROOT.glob("studies/*/runs"):
        # Compress at the immediate experiment-directory level.  A live child
        # keeps its own experiment tree recent and therefore excluded.
        for child in runs.iterdir():
            if child.is_dir():
                if old_enough(child, cutoff):
                    roots.append(child)
                else:
                    for grandchild in child.iterdir():
                        if grandchild.is_dir() and old_enough(grandchild, cutoff):
                            roots.append(grandchild)
    # Raw source trees are immutable inputs in normal use and benefit from
    # transparent compression, especially extracted CSVs.
    for raw in ROOT.glob("studies/*/data/raw"):
        if raw.is_dir() and old_enough(raw, cutoff):
            roots.append(raw)
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
    def clear_readonly(function, item, excinfo) -> None:
        try:
            os.chmod(item, stat.S_IWRITE)
            function(item)
        except OSError:
            raise excinfo

    shutil.rmtree(path, onexc=clear_readonly)


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
    delete = [path for path in disposable_paths() if old_enough(path, cutoff)]
    reclaimable = sum(tree_stats(path)[0] for path in delete)

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'} root={ROOT}")
    print(f"delete_candidates={len(delete)} logical_bytes={human(reclaimable)}")
    for path in delete:
        size, files, _ = tree_stats(path)
        print(f"DELETE  {human(size):>10} {files:6d}  {path.relative_to(ROOT)}")

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
