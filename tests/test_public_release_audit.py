from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_release_audit.py"


def load_audit_module():
    spec = importlib.util.spec_from_file_location("pineland_public_release_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_rust_modules_detects_uncommitted_external_module(tmp_path: Path) -> None:
    audit = load_audit_module()
    audit.ROOT = tmp_path
    src = tmp_path / "rust" / "example" / "src"
    src.mkdir(parents=True)
    (src / "lib.rs").write_text("pub mod present;\npub mod missing;\n", encoding="utf-8")
    (src / "present.rs").write_text("pub fn present() {}\n", encoding="utf-8")

    missing = audit.missing_rust_modules(
        ["rust/example/src/lib.rs", "rust/example/src/present.rs"]
    )

    assert len(missing) == 1
    assert "declares mod missing" in missing[0]


def test_missing_rust_modules_accepts_file_and_directory_modules(tmp_path: Path) -> None:
    audit = load_audit_module()
    audit.ROOT = tmp_path
    src = tmp_path / "rust" / "example" / "src"
    (src / "nested").mkdir(parents=True)
    (src / "lib.rs").write_text("mod flat;\nmod nested;\n", encoding="utf-8")
    (src / "flat.rs").write_text("pub fn flat() {}\n", encoding="utf-8")
    (src / "nested" / "mod.rs").write_text("pub fn nested() {}\n", encoding="utf-8")

    missing = audit.missing_rust_modules(
        [
            "rust/example/src/lib.rs",
            "rust/example/src/flat.rs",
            "rust/example/src/nested/mod.rs",
        ]
    )

    assert missing == []


def test_restricted_source_artifacts_tracked_flags_declared_local_path(
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    audit.ROOT = tmp_path
    manifest = tmp_path / "studies" / "case_a" / "data" / "manifests" / "sources.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """{
  "sources": [{
    "dataset": "restricted example",
    "local_path": "data/raw/source.zip",
    "redistribution": "permission_required"
  }]
}
""",
        encoding="utf-8",
    )

    findings = audit.restricted_source_artifacts_tracked(
        {"studies/case_a/data/raw/source.zip"}
    )

    assert len(findings) == 1
    assert "permission_required" in findings[0]


def test_restricted_source_artifacts_tracked_allows_manifest_only(
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    audit.ROOT = tmp_path
    manifest = tmp_path / "studies" / "case_a" / "data" / "manifests" / "sources.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """{
  "sources": [{
    "dataset": "metadata-only example",
    "local_path": "data/raw/source.zip",
    "redistribution": "metadata_only"
  }]
}
""",
        encoding="utf-8",
    )

    findings = audit.restricted_source_artifacts_tracked(
        {"studies/case_a/data/manifests/sources.json"}
    )

    assert findings == []
