#!/usr/bin/env python3
"""Build a compact, auditable index of subsystem-facing test evidence."""
from __future__ import annotations

import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "subsystem-evidence-index.md"

GROUPS = [
    {
        "name": "Runtime, determinism, and reproducibility",
        "role": "Research-load-bearing infrastructure",
        "py": [
            "tests/test_reproducibility.py", "tests/test_scheduler.py",
            "tests/test_timebase.py", "tests/test_simulation.py", "tests/test_io.py",
            "tests/test_archive_stream.py", "tests/test_native_ensemble.py",
            "tests/test_native_kernels.py",
        ],
        "rs": [
            "rust/pineland-core/src/checkpoint.rs", "rust/pineland-core/src/config.rs",
            "rust/pineland-core/src/json.rs", "rust/pineland-core/src/rng.rs",
            "rust/pineland-core/src/scheduler.rs", "rust/pineland-core/src/sha256.rs",
            "rust/pineland-core/src/state.rs",
        ],
        "docs": ["rust/README.md", "docs/repository-layout.md"],
    },
    {
        "name": "Physical presence and territorial control",
        "role": "Research-load-bearing mechanism",
        "py": [
            "tests/test_physical.py", "tests/test_role_capacity_resolution.py",
            "tests/test_scaling.py", "tests/test_weighted_representative_semantics.py",
            "tests/test_resource_semantics.py",
        ],
        "rs": [],
        "docs": ["docs/physical-model.md", "docs/odd-model.md"],
    },
    {
        "name": "Logistics, readiness, and command",
        "role": "Research-load-bearing mechanism",
        "py": [
            "tests/test_logistics.py", "tests/test_causal_integrity.py",
            "tests/test_armed_formation_operational_semantics.py",
            "tests/test_resource_semantics.py",
        ],
        "rs": ["rust/pineland-model/src/logistics.rs", "rust/pineland-model/src/movement.rs"],
        "docs": ["docs/logistics-model.md", "docs/resource-semantics.md"],
    },
    {
        "name": "Organization ecology and reproduction",
        "role": "Research-load-bearing in General Theory v1",
        "py": [
            "tests/test_organization_ecology.py", "tests/test_insurgent_reproduction.py",
            "tests/test_insurgent_reproduction_identification.py",
            "tests/test_competitive_local_renewal.py", "tests/test_local_foothold_state.py",
            "tests/test_local_force_critical_mass.py",
            "tests/test_locality_activation_genealogy.py",
            "tests/test_locality_reproduction_ensemble.py", "tests/test_franchise_ecology.py",
        ],
        "rs": ["rust/pineland-model/src/state_regeneration.rs"],
        "docs": [
            "docs/organization-ecology.md",
            "studies/research_program/general_theory_v1/README.md",
        ],
    },
    {
        "name": "Information, observations, and actor beliefs",
        "role": "Research-load-bearing mechanism",
        "py": [
            "tests/test_information.py", "tests/test_compact_information_state.py",
            "tests/test_measurement.py", "tests/test_truth_firewall.py",
            "tests/test_social_exposure_provenance.py", "tests/test_networks.py",
        ],
        "rs": ["rust/pineland-model/src/information.rs"],
        "docs": [
            "docs/information-model.md", "docs/social-network-semantics.md",
            "docs/research-readiness.md",
        ],
    },
    {
        "name": "State estimation and inference",
        "role": "Research-load-bearing inference layer",
        "py": [
            "tests/test_state_estimation.py", "tests/test_recovery.py",
            "tests/test_reproduction_identification_recovery.py",
            "tests/test_identifiability_triage.py",
            "tests/test_afghanistan_filtered_state_estimation.py",
        ],
        "rs": [
            "rust/pineland-inference/src/filter.rs",
            "rust/pineland-inference/src/forecast.rs",
            "rust/pineland-inference/src/parallel.rs",
            "rust/pineland-inference/src/resampling.rs",
        ],
        "docs": ["docs/state-estimation.md", "docs/research-v1.md"],
    },
    {
        "name": "Organized action and combat",
        "role": "Implemented and used by active studies",
        "py": [
            "tests/test_action_model.py", "tests/test_combat.py",
            "tests/test_contact_pipeline.py", "tests/test_event_support_architecture.py",
            "tests/test_experimental_action_support.py",
            "tests/test_insurgent_portfolio_synthetic_validation.py",
        ],
        "rs": ["rust/pineland-model/src/lib.rs"],
        "docs": ["docs/action-model.md", "docs/combat-model.md"],
    },
    {
        "name": "Political order and governance",
        "role": "Implemented; secondary to the first-paper inference program",
        "py": ["tests/test_political_order.py"],
        "rs": [],
        "docs": ["docs/political-order.md"],
    },
    {
        "name": "Foreign affairs and partner-force support",
        "role": "Implemented; partner-force support is an active Stage-3 program",
        "py": ["tests/test_foreign_affairs.py", "tests/test_arc_hpc_campaign.py"],
        "rs": [
            "rust/pineland-model/src/lib.rs", "rust/pineland-model/src/logistics.rs",
            "rust/pineland-model/src/movement.rs",
            "rust/pineland-model/src/state_regeneration.rs",
        ],
        "docs": [
            "docs/foreign-affairs.md",
            "studies/research_program/general_theory_v1/partner_force_autonomy/README.md",
        ],
    },
    {
        "name": "Peace process",
        "role": "Implemented; currently peripheral",
        "py": ["tests/test_peace_process.py"],
        "rs": [],
        "docs": ["docs/peace-process.md"],
    },
    {
        "name": "Historical measurement and case transport",
        "role": "Active external-validation layer",
        "py": [
            "tests/test_empirical.py", "tests/test_empirical_geography.py",
            "tests/test_historical.py", "tests/test_historical_database_v2.py",
            "tests/test_case_readiness.py", "tests/test_comparative_case_contract.py",
            "tests/test_comparative_control_presence_panels.py",
            "tests/test_afghanistan_historical_inputs.py",
            "tests/test_afghanistan_transfer_gate.py",
            "tests/test_nigeria_2014_external_holdout_design.py",
        ],
        "rs": [],
        "docs": ["docs/empirical-benchmarking.md", "docs/research-validation.md"],
    },
    {
        "name": "HPC and distributed execution",
        "role": "Research-load-bearing execution infrastructure",
        "py": ["tests/test_arc_hpc_campaign.py", "tests/test_execution_scaling.py"],
        "rs": [
            "rust/pineland-hpc/src/distributed.rs", "rust/pineland-hpc/src/distribution.rs",
            "rust/pineland-hpc/src/migration.rs", "rust/pineland-hpc/src/mpi.rs",
        ],
        "docs": ["rust/hpc/ARC.md", "rust/README.md"],
    },
]

def py_count(relative):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"))
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )

def rs_count(relative):
    text = (ROOT / relative).read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(r"#\s*\[test\]", text))

def md_link(relative):
    target = "../" + relative if not relative.startswith("docs/") else relative[5:]
    return "[{}]({})".format(relative, target)

def main():
    py_paths = sorted((ROOT / "tests").glob("test_*.py"))
    py_total = sum(py_count(p.relative_to(ROOT).as_posix()) for p in py_paths)
    rs_paths = sorted((ROOT / "rust").rglob("*.rs"))
    rs_counts = [(p, len(re.findall(r"#\s*\[test\]", p.read_text(encoding="utf-8", errors="ignore")))) for p in rs_paths]
    rs_nonzero = [(p, n) for p, n in rs_counts if n]
    rs_total = sum(n for _, n in rs_nonzero)

    lines = [
        "# Subsystem evidence index",
        "",
        "This is a mechanical index of test and documentation evidence, not a maturity score.",
        "Counts show where executable verification effort exists; they do not establish",
        "historical validity, realism, or correctness by themselves.",
        "",
        "Current repository baseline: **{} Python test functions across {} test files** and".format(py_total, len(py_paths)),
        "**{} Rust test cases across {} Rust source files**.".format(rs_total, len(rs_nonzero)),
        "",
        "| Subsystem | Role | Selected Python tests | Selected Rust tests | Primary evidence |",
        "|---|---|---:|---:|---|",
    ]

    for group in GROUPS:
        for relative in group["py"] + group["rs"] + group["docs"]:
            if not (ROOT / relative).exists():
                raise SystemExit("evidence path does not exist: " + relative)
        pcount = sum(py_count(p) for p in group["py"])
        rcount = sum(rs_count(p) for p in group["rs"])
        evidence = "; ".join(md_link(p) for p in group["docs"])
        lines.append("| {} | {} | {} | {} | {} |".format(group["name"], group["role"], pcount, rcount, evidence))

    lines += [
        "",
        "## Selected executable evidence",
        "",
        "The table intentionally uses selected test files rather than assigning every",
        "cross-cutting test to exactly one subsystem. A test may appear in multiple rows",
        "when the same invariant crosses subsystem boundaries.",
        "",
    ]

    for group in GROUPS:
        lines += ["### " + group["name"], ""]
        if group["py"]:
            lines.append("Python:")
            for path in group["py"]:
                lines.append("- {} - {} test functions".format(md_link(path), py_count(path)))
        if group["rs"]:
            lines += ["", "Rust:"]
            for path in group["rs"]:
                count = rs_count(path)
                suffix = "{} test cases".format(count) if count else "implementation evidence; no local test case in this file"
                lines.append("- {} - {}".format(md_link(path), suffix))
        lines.append("")

    lines += [
        "## Interpretation",
        "",
        "Three distinct questions remain separate:",
        "",
        "1. **Implementation evidence:** does executable code and regression coverage exist?",
        "2. **Synthetic scientific evidence:** does the mechanism or inference method survive",
        "   known-truth, sensitivity, falsification, or holdout tests?",
        "3. **Historical validity:** can the corresponding construct be measured and defended",
        "   against real-world evidence?",
        "",
        "The existence of many tests is evidence for engineering attention, not a substitute",
        "for the latter two questions.",
        "",
        "Regenerate this page with:",
        "",
        "    python scripts/build_subsystem_evidence_index.py",
        "",
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUTPUT.relative_to(ROOT))

if __name__ == "__main__":
    main()


