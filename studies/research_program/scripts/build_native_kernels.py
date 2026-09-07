"""Build the optional dependency-free Rust acceleration kernels."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "native" / "pineland_kernels.rs"
DESTINATION = (
    ROOT / "src" / "pineland_sim" / "_native" / "pineland_kernels.dll"
)


def main() -> None:
    rustc = shutil.which("rustc")
    if rustc is None:
        raise SystemExit("rustc is not available")
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            rustc,
            "--crate-type",
            "cdylib",
            "-C",
            "opt-level=3",
            "-C",
            "target-cpu=native",
            str(SOURCE),
            "-o",
            str(DESTINATION),
        ],
        check=True,
    )
    print(DESTINATION)


if __name__ == "__main__":
    main()
