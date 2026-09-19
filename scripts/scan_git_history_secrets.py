#!/usr/bin/env python3
"""Run the repository's full-history Gitleaks scan.

This is intentionally separate from the dependency-free public-release audit:
Gitleaks is an external binary and should be installed explicitly by a release
operator or CI job.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]

BUILTIN_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "private_key_header": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
}


def builtin_history_scan() -> int:
    """Scan every reachable textual commit diff for high-signal secrets."""
    command = [
        "git",
        "log",
        "--all",
        "--full-history",
        "--no-ext-diff",
        "--text",
        "--format=commit %H",
        "-p",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    current_commit = "unknown"
    findings: list[tuple[str, str]] = []
    for line in process.stdout:
        if line.startswith("commit "):
            current_commit = line.split(None, 1)[1].strip()
        for label, pattern in BUILTIN_PATTERNS.items():
            if pattern.search(line):
                findings.append((current_commit, label))
    stderr = process.stderr.read() if process.stderr is not None else ""
    returncode = process.wait()
    if returncode:
        print(stderr, file=sys.stderr)
        return returncode
    if findings:
        unique = sorted(set(findings))
        for commit, label in unique:
            print(f"FAIL {label} pattern found in history at {commit}", file=sys.stderr)
        return 1
    print(
        "PASS full Git history contains no high-signal secret patterns "
        "(dependency-free fallback)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        help="optional JSON report path (Gitleaks output is redacted)",
    )
    parser.add_argument(
        "--builtin-only",
        action="store_true",
        help="run the dependency-free high-signal history scan instead of Gitleaks",
    )
    args = parser.parse_args()

    if args.builtin_only:
        return builtin_history_scan()

    binary = shutil.which("gitleaks")
    if binary is None:
        print("gitleaks is not installed; running high-signal built-in fallback.")
        return builtin_history_scan()

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
