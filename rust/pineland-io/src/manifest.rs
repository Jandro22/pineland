//! Stable run-manifest construction.
use pineland_core::provenance::ProvenanceManifest;
use pineland_core::sha256;
use pineland_model::SimulationEngine;
use std::path::{Path, PathBuf};
use std::process::Command;

pub fn for_engine(engine: &SimulationEngine) -> ProvenanceManifest {
    let mut manifest = ProvenanceManifest::start(
        engine.config.seed,
        engine
            .config
            .initialization_seed
            .unwrap_or(engine.config.seed),
        engine.config.canonical_hash(),
    );
    let workspace = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    manifest.cargo_lock_sha256 =
        hash_file(&workspace.join("Cargo.lock")).unwrap_or_else(|| "unavailable".to_string());
    manifest.rust_source_sha256 =
        hash_tree(&workspace).unwrap_or_else(|| "unavailable".to_string());
    manifest.binary_sha256 = std::env::current_exe()
        .ok()
        .and_then(|path| hash_file(&path))
        .unwrap_or_else(|| "unavailable".to_string());
    manifest.compiler_version = Command::new("rustc")
        .arg("--version")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string())
        .unwrap_or_else(|| manifest.compiler_version);
    manifest.git_commit = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(&workspace)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string())
        .unwrap_or_else(|| manifest.git_commit);
    manifest
}

fn hash_file(path: &Path) -> Option<String> {
    std::fs::read(path)
        .ok()
        .map(|bytes| sha256::digest_hex(&bytes))
}

fn hash_tree(root: &Path) -> Option<String> {
    let mut files = Vec::new();
    collect_files(root, root, &mut files);
    if files.is_empty() {
        return None;
    }
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let mut bytes = Vec::new();
    for (relative, path) in files {
        bytes.extend_from_slice(relative.to_string_lossy().as_bytes());
        bytes.push(0);
        bytes.extend_from_slice(&std::fs::read(path).ok()?);
    }
    Some(sha256::digest_hex(&bytes))
}

fn collect_files(root: &Path, current: &Path, files: &mut Vec<(PathBuf, PathBuf)>) {
    let Ok(entries) = std::fs::read_dir(current) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let relative = path.strip_prefix(root).unwrap_or(&path).to_path_buf();
        if path.is_dir() {
            if entry.file_name() != "target" {
                collect_files(root, &path, files)
            }
        } else if path.is_file() {
            files.push((relative, path));
        }
    }
}
