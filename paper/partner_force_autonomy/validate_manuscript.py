#!/usr/bin/env python3
"""Validate manuscript mechanics and headline evidence against tracked Stage-4 outputs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper" / "partner_force_autonomy"
EVIDENCE = (
    ROOT
    / "studies"
    / "research_program"
    / "general_theory_v1"
    / "partner_force_autonomy"
    / "evidence"
    / "stage4"
)


def main() -> None:
    manuscript = (PAPER / "manuscript.md").read_text(encoding="utf-8")
    paper_text = "\n".join(
        path.read_text(encoding="utf-8", errors="strict")
        for path in PAPER.iterdir()
        if path.is_file() and path.suffix in {".md", ".bib", ".py"}
    )

    assert "\u2014" not in paper_text, "em dash found in paper source"
    assert "\ufffd" not in paper_text, "Unicode replacement character found"

    bib = (PAPER / "references.bib").read_text(encoding="utf-8")
    bib_keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    cited_keys: set[str] = set()
    for block in re.findall(r"\[(@[^\]]+)\]", manuscript):
        cited_keys.update(re.findall(r"@([A-Za-z0-9_:-]+)", block))
    missing = cited_keys - bib_keys
    assert not missing, f"missing bibliography keys: {sorted(missing)}"

    ready = json.loads(
        (EVIDENCE / "READY_STAGE4_INTEGRATED.json").read_text(encoding="utf-8")
    )
    assert ready["status"] == "STAGE4_INTEGRATED_PROGRAM_COMPLETE"
    assert ready["production_worlds"] == 2808

    phase = pd.read_csv(EVIDENCE / "phase_cell_summary_v1.csv")
    treated = phase[phase["factor_support_intensity"] > 0]
    effective = treated[treated["phase_regime"] != "not_initially_effective"]
    assert len(treated) == 120
    assert len(effective) == 106
    assert (effective["phase_regime"] == "effective_autonomy_trap").sum() == 96
    assert (effective["phase_regime"] == "effective_autonomy_building").sum() == 10
    assert (
        treated["robust_phase_regime"] == "robust_effective_autonomy_trap"
    ).sum() == 53
    assert (
        treated["robust_phase_regime"] == "robust_effective_autonomy_building"
    ).sum() == 0

    migration = pd.read_csv(EVIDENCE / "migration_target_match_summary_v1.csv")
    matched = migration[
        migration["observed_target_match"].eq(True)
        & migration["factor_support_target"].isin(["command", "forcegen", "logistics"])
    ]
    expected_migration = {
        "command": (38, 38),
        "forcegen": (46, 46),
        "logistics": (85, 0),
    }
    for target, (expected_n, expected_events) in expected_migration.items():
        group = matched[matched["factor_support_target"] == target]
        assert int(group["n"].sum()) == expected_n
        assert int(group["persistent_migration_count"].sum()) == expected_events

    expected_relief_yield = {
        "command": (0.00353620531578948, 0.0555494112894737),
        "forcegen": (2.07804347823507e-7, 0.0),
        "logistics": (0.0169926201764706, -0.221527308552941),
    }
    for target, (expected_cap30, expected_q360) in expected_relief_yield.items():
        group = matched[matched["factor_support_target"] == target]
        n = float(group["n"].sum())
        cap30 = float((group["mean_delta_capability_h30"] * group["n"]).sum() / n)
        q360 = float((group["mean_delta_q_feasible_h360"] * group["n"]).sum() / n)
        assert abs(cap30 - expected_cap30) < 1e-12
        assert abs(q360 - expected_q360) < 1e-12

    mechanism = pd.read_csv(EVIDENCE / "mechanism_mode_contrasts_v1.csv")
    logistics = mechanism[
        mechanism["factor_target"].eq("logistics")
        & mechanism["contrast"].eq("development_minus_substitution")
    ]
    assert len(logistics) == 4
    assert (logistics["delta_q_feasible_h360_boot95_lo"] > 0).all()
    assert (logistics["delta_q_feasible_h360_boot95_hi"] > 0).all()

    print(
        "PASS manuscript validation: no em dashes; citations complete; "
        "Stage-4 provenance, headline results, and relief-yield synthesis "
        "match tracked evidence"
    )


if __name__ == "__main__":
    main()
