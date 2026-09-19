#!/usr/bin/env python3
"""Cheap, dependency-free checks for eventual public release readiness.

This audit intentionally does not run scientific tests. It checks repository
metadata, obvious publication hazards, and source-manifest completeness while
long-running experiments can continue independently.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    ".github/workflows/pineland-ci.yml",
    "docs/release-policy.md",
    "docs/archive-policy.md",
    "docs/data-redistribution.md",
    "docs/public-release-checklist.md",
    "docs/subsystem-status.md",
    "docs/subsystem-evidence-index.md",
    ".gitleaks.toml",
    "scripts/scan_git_history_secrets.py",
)

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "private_key_header": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
}

SUSPICIOUS_FILENAMES = re.compile(
    r"(^|/)(?:\.env(?:\.|$)|id_rsa$|id_ed25519$|credentials?|secrets?|"
    r"[^/]+\.(?:pem|p12|key)$)",
    re.IGNORECASE,
)

GENERATED_TRACKED = re.compile(
    r"(^|/)(?:__pycache__|\.pytest_cache|target(?:-[^/]+)?)(/|$)|"
    r"\.py[co]$|(^|/)outputs/"
)

RUST_EXTERNAL_MODULE = re.compile(
    r"^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;"
)


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout


def citation_version() -> str | None:
    path = ROOT / "CITATION.cff"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return None


def source_manifest_warnings() -> list[str]:
    warnings: list[str] = []
    for manifest in sorted(ROOT.glob("studies/*/data/manifests/sources.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - diagnostic path
            warnings.append(f"{manifest.relative_to(ROOT)}: unreadable JSON ({exc})")
            continue
        missing_license: list[str] = []
        missing_redistribution: list[str] = []
        review_required: list[str] = []
        sources = data.get("sources", [])
        for index, source in enumerate(sources):
            source_id = (
                source.get("source_id")
                or source.get("dataset")
                or source.get("provider")
                or f"source[{index}]"
            )
            if not source.get("license") and not source.get("license_url"):
                missing_license.append(str(source_id))
            if "redistribution" not in source:
                missing_redistribution.append(str(source_id))
            if (
                source.get("license") == "review_required"
                or source.get("redistribution") == "review_required"
            ):
                review_required.append(str(source_id))
        if missing_license:
            warnings.append(
                f"{manifest.relative_to(ROOT)}: {len(missing_license)}/{len(sources)} "
                "sources lack license/license_url"
            )
        if missing_redistribution:
            warnings.append(
                f"{manifest.relative_to(ROOT)}: {len(missing_redistribution)}/{len(sources)} "
                "sources lack redistribution status"
            )
        if review_required:
            warnings.append(
                f"{manifest.relative_to(ROOT)}: {len(review_required)}/{len(sources)} "
                "sources remain review_required"
            )
    return warnings


def tracked_files() -> list[str]:
    return [p for p in git("ls-files").splitlines() if p]


def scan_current_tree_for_secrets(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for relative in paths:
        if SUSPICIOUS_FILENAMES.search(relative.replace("\\", "/")):
            findings.append(f"suspicious tracked filename: {relative}")
        path = ROOT / relative
        try:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            text = raw.decode("utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label} pattern in tracked file: {relative}")
    return findings


def scan_current_tree_for_replacement_characters(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for relative in paths:
        path = ROOT / relative
        try:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            text = raw.decode("utf-8", errors="ignore")
        except OSError:
            continue
        if "\ufffd" in text:
            findings.append(relative)
    return findings


def missing_rust_modules(paths: list[str]) -> list[str]:
    """Return external Rust module declarations whose source file is absent."""
    missing: list[str] = []
    for relative in paths:
        normalized = relative.replace("\\", "/")
        if not normalized.startswith("rust/") or not normalized.endswith(".rs"):
            continue
        source = ROOT / relative
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, start=1):
            match = RUST_EXTERNAL_MODULE.match(line)
            if not match:
                continue
            name = match.group(1)
            file_candidate = source.parent / f"{name}.rs"
            dir_candidate = source.parent / name / "mod.rs"
            if not file_candidate.exists() and not dir_candidate.exists():
                missing.append(
                    f"{relative}:{lineno} declares mod {name} but neither "
                    f"{file_candidate.relative_to(ROOT)} nor "
                    f"{dir_candidate.relative_to(ROOT)} exists"
                )
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as failures (appropriate immediately before release)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        dest="json_path",
        help="write the audit result as JSON in addition to console output",
    )
    ns = parser.parse_args()

    passes: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    missing = [name for name in REQUIRED_FILES if not (ROOT / name).exists()]
    if missing:
        failures.append("missing required public files: " + ", ".join(missing))
    else:
        passes.append("required public/release metadata files exist")

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = str(pyproject["project"]["version"])
    cff_version = citation_version()
    if cff_version == package_version:
        passes.append(f"package and CITATION.cff versions agree ({package_version})")
    else:
        failures.append(
            f"version mismatch: pyproject={package_version!r}, CITATION.cff={cff_version!r}"
        )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if (
        "actions/workflows/pineland-ci.yml" in readme
        and "badge.svg?branch=main" in readme
    ):
        passes.append("README CI badge targets main")
    else:
        warnings.append("README CI badge does not target pineland-ci.yml on main")
    if "\ufffd" in readme:
        failures.append("README contains Unicode replacement characters")
    else:
        passes.append("README contains no Unicode replacement characters")

    tracked = tracked_files()
    replacement_character_files = scan_current_tree_for_replacement_characters(tracked)
    if replacement_character_files:
        failures.append(
            "Unicode replacement characters found in tracked text files: "
            + ", ".join(replacement_character_files[:20])
        )
    else:
        passes.append("tracked text files contain no Unicode replacement characters")

    generated = [
        p
        for p in tracked
        if GENERATED_TRACKED.search(p.replace("\\", "/"))
        and Path(p).name not in {".gitignore", ".gitkeep"}
    ]
    if generated:
        warnings.append(
            "generated-looking paths are tracked: " + ", ".join(generated[:20])
        )
    else:
        passes.append("no obvious generated/cache/build paths are tracked")

    secrets = scan_current_tree_for_secrets(tracked)
    if secrets:
        failures.extend(secrets)
    else:
        passes.append("current tracked tree passes high-signal secret-pattern scan")

    rust_modules = missing_rust_modules(tracked)
    if rust_modules:
        failures.extend(f"missing Rust module source: {item}" for item in rust_modules)
    else:
        passes.append("all tracked external Rust module declarations resolve")

    tag = f"v{package_version}"
    if git("tag", "--list", tag).strip() == tag:
        passes.append(f"software tag exists ({tag})")
    else:
        warnings.append(f"software tag {tag} does not exist yet")

    warnings.extend(source_manifest_warnings())

    status = git("status", "--porcelain").splitlines()
    if status:
        warnings.append("working tree is not clean")
    else:
        passes.append("working tree is clean")

    payload = {
        "schema_version": "pineland.public_release_audit.v1",
        "package_version": package_version,
        "passes": passes,
        "warnings": warnings,
        "failures": failures,
        "strict": ns.strict,
    }

    for item in passes:
        print(f"PASS  {item}")
    for item in warnings:
        print(f"WARN  {item}")
    for item in failures:
        print(f"FAIL  {item}")

    if ns.json_path is not None:
        output = ns.json_path if ns.json_path.is_absolute() else ROOT / ns.json_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        f"SUMMARY passes={len(passes)} warnings={len(warnings)} failures={len(failures)}"
    )
    if failures or (ns.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
