"""Repository-local Pineland CLI.

This wrapper makes the scientific reproduction entry points usable directly
from a source checkout without requiring an editable package installation.
The installed console entry point remains ``pineland-sim``.
"""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
