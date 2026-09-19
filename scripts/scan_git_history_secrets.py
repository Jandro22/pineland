#!/usr/bin/env python3
"""Run the repository's full-history Gitleaks scan.

This is intentionally separate from the dependency-free public-release audit:
Gitleaks is an external binary and should be installed explicitly by a release
operator or CI job.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        help="optional JSON report path (Gitleaks output is redacted)",
    )
    args = parser.parse_args()

    binary = shutil.which("gitleaks")
    if binary is None:
        print(
            "gitleaks is required for the history scan. Install Gitleaks 8.x "
            "and rerun this command.",
            file=sys.stderr,
        )
        return 2

    if args.report:
        report = args.report.resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        handle = tempfile.NamedTemporaryFile(
            prefix="pineland-gitleaks-", suffix=".json", delete=False
        )
        handle.close()
        report = Path(handle.name)
        cleanup = True

    try:
        command = [
            binary,
            "git",
            "--redact",
            "--config",
            str(ROOT / ".gitleaks.toml"),
            "--report-format",
            "json",
            "--report-path",
            str(report),
            str(ROOT),
        ]
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode == 0:
            print("PASS full Git history contains no unallowlisted Gitleaks findings")
            return 0
        print(
            f"FAIL Gitleaks reported findings; inspect the redacted report at {report}",
            file=sys.stderr,
        )
        if cleanup:
            cleanup = False  # preserve the report when findings exist
        return result.returncode
    finally:
        if cleanup:
            report.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
