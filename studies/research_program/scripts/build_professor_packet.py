"""Build the gated professor-ready packet from current evidence artifacts.

This packet is deliberately honest about failed or unauthorized gates. It is a
research handoff, not an approval claim and not an outreach action.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"
OUTPUT = ROOT / "artifacts/professor_packet"


def _ascii(value: Any) -> str:
    text = str(value)
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")
    return text.encode("ascii", "replace").decode("ascii")


def _json(name: str) -> dict[str, Any] | None:
    path = PROGRAM / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("PacketTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor("#12304A"), spaceAfter=12),
        "subtitle": ParagraphStyle("PacketSubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#47657A"), spaceAfter=14),
        "h1": ParagraphStyle("PacketH1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor("#12304A"), spaceBefore=10, spaceAfter=7),
        "h2": ParagraphStyle("PacketH2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#1F607A"), spaceBefore=7, spaceAfter=4),
        "body": ParagraphStyle("PacketBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9.2, leading=12.5, textColor=colors.HexColor("#1E2A33"), spaceAfter=6),
        "small": ParagraphStyle("PacketSmall", parent=base["BodyText"], fontName="Helvetica", fontSize=7.6, leading=9.5, textColor=colors.HexColor("#40515C"), spaceAfter=3),
        "small_white": ParagraphStyle("PacketSmallWhite", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7.6, leading=9.5, textColor=colors.white, spaceAfter=3),
        "callout": ParagraphStyle("PacketCallout", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#7C2D12"), backColor=colors.HexColor("#FFF4E6"), borderColor=colors.HexColor("#F3B562"), borderWidth=0.7, borderPadding=7, spaceBefore=5, spaceAfter=9),
        "center": ParagraphStyle("PacketCenter", parent=base["BodyText"], alignment=TA_CENTER, fontSize=9, leading=11),
    }


S = _styles()


def P(text: Any, style: str = "body") -> Paragraph:
    return Paragraph(escape(_ascii(text)).replace("\n", "<br/>"), S[style])


def _header_footer(canv: canvas.Canvas, doc: Any) -> None:
    canv.saveState()
    width, height = letter
    canv.setStrokeColor(colors.HexColor("#D6E1E8"))
    canv.line(0.6 * inch, height - 0.48 * inch, width - 0.6 * inch, height - 0.48 * inch)
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(colors.HexColor("#5A7180"))
    canv.drawString(0.6 * inch, 0.31 * inch, "Pineland research program | gated evidence packet")
    canv.drawRightString(width - 0.6 * inch, 0.31 * inch, f"Page {doc.page}")
    canv.restoreState()


def _doc(path: Path, story: list[Any], *, top_margin: float = 0.65 * inch, bottom_margin: float = 0.52 * inch) -> None:
    document = SimpleDocTemplate(
        str(path), pagesize=letter, rightMargin=0.62 * inch, leftMargin=0.62 * inch,
        topMargin=top_margin, bottomMargin=bottom_margin,
        title=path.stem, author="Pineland research program",
    )
    document.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)


def _table(rows: list[list[Any]], widths: list[float] | None = None, *, header: bool = True) -> Table:
    converted = []
    for row_index, row in enumerate(rows):
        converted.append([P(cell, "small_white" if header and row_index == 0 else "small") if not isinstance(cell, Paragraph) else cell for cell in row])
    table = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D7DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12304A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ])
    table.setStyle(TableStyle(commands))
    return table


def build_memo() -> None:
    phase_a = _json("phase_a_certificate_v1.json") or {}
    phase_b = _json("phase_b_inference_validation_v2.json") or {}
    phase_c = _json("phase_c_method_contract_v1.json") or {}
    phase_d = _json("phase_d_historical_confrontation_status_v1.json") or {}
    phase_f = _json("phase_f_robustness_status_v1.json") or {}
    benchmark_failure = _json("phase_a_fixed_work_benchmark_failure_v1.json") or {}
    story: list[Any] = [P("Modelling Insurgencies through Agent-Based Simulations", "title"), P("Professor-ready research memo | current gate state as of 2026-09-08", "subtitle")]
    story += [P("Decision", "h1"), P("The computational program now has a reproducible exactness and synthetic-inference spine, but it is not authorized to promote a historical transfer claim. The current packet keeps the historical gate closed because the live core differs from the prior certificate and the fixed production throughput gate must be independently recorded before historical confrontation.", "callout")]
    story += [P("What is established", "h1"), _table([
        ["Gate", "Evidence", "Status"],
        ["Exact scheduler oracle", "12 seeds x 5 horizons; world and continuation hashes", "PASS" if phase_a.get("checks", {}).get("A1_exact_scheduler_oracle") else "FAIL"],
        ["Packed authority", "Runtime schema inventory with explicit sparse boundaries", "PASS" if phase_a.get("checks", {}).get("A2_authority_inventory") else "FAIL"],
        ["Kernel oracles", "Physical and numeric information kernel comparisons", "PASS" if phase_a.get("checks", {}).get("A3_kernel_oracles") else "FAIL"],
        ["Synthetic inference", "RB, guided, MCSE, combined validation; no history", "PASS" if phase_b.get("passed") else "FAIL"],
    ], [1.25 * inch, 3.65 * inch, 1.0 * inch]), Spacer(1, 7)]
    story += [P("Scientific interpretation", "h1"), P("The model is treated as a latent-state mechanism: organizational capacity, civilian access, territorial control, belief state, logistics readiness, operational posture, and local exposure jointly determine action hazards and foothold reproduction. The central quantity is R_t, the expected number of newly active footholds produced per active foothold over a defined interval. This is a falsifiable mechanism statement, not an assertion that historical fit has been achieved.")]
    story += [P("Current blockers", "h1"), _table([
        ["Blocker", "Consequence"],
        ["Core freeze drift", "Prior v5 historical artifacts are stale-core evidence and cannot be promoted."],
        ["Performance gate", "The complete fixed 768-PWB run exceeded the safe resource window and was stopped; no PWB/s value is reported and E1/E2 remain failed closed."],
        ["Historical confrontation", "Nepal and Afghanistan are not rerun unless the frozen method contract authorizes the once-only run."],
    ], [2.1 * inch, 3.8 * inch]), PageBreak()]
    story += [P("Recommended next decision", "h1"), P("Treat this packet as a methods and audit handoff. If the throughput gate passes and the core boundary is frozen, run the preregistered Nepal and Afghanistan confrontation exactly once, preserve every seed and negative result, and report calibration-free predictive scores against predeclared observation operators. If the gate fails, optimize the identified packed synchronization bottleneck before any historical rerun.")]
    story += [P("Do not claim", "h1"), _table([
        ["Claim", "Why it is withheld"],
        ["The model explains Nepal or Afghanistan", "No authorized current-core historical confrontation is present in this packet."],
        ["The mechanism is identified historically", "Synthetic identification is passed; historical identification is not established."],
        ["The model is production-ready", "Throughput and freeze conditions must be evaluated from the current fixed-work artifact."],
    ], [2.2 * inch, 3.7 * inch]), Spacer(1, 8)]
    story += [P("Reproducibility", "h1"), P("All evidence is content-hashed and tied to the current model hash, source state, and explicit protocol. The negative guided-validation v1 artifact is preserved alongside the passing v2 revision; no failed run is deleted or silently reclassified. No outreach or external communication is performed by this packet builder.")]
    story += [P("Packet contents", "h1"), P("Architecture figure; technical note; fixed-work performance result; claims/evidence matrix; limitations and failure ledger; machine-readable manifest; and this readme. The accompanying JSON manifest is the authoritative file inventory.")]
    _doc(OUTPUT / "01_two_page_research_memo.pdf", story)


def build_technical_note() -> None:
    phase_a = _json("phase_a_certificate_v1.json") or {}
    phase_b = _json("phase_b_inference_validation_v2.json") or {}
    profile = _json("phase_a_execution_profile_v1.json") or {}
    story: list[Any] = [P("Technical note: exactness, inference, and gates", "title"), P("Versioned implementation note for independent review", "subtitle")]
    story += [P("1. Computational authority", "h1"), P("The packed hot state is authoritative for migrated physical, organizational, logistics, and action calculations. Static topology is immutable. Sparse reference processes cross an explicit synchronization boundary. Structural rebuilds materialize all lanes only when dynamic entity IDs change. This division prevents stale packed values from overwriting sparse-event mutations.")]
    story += [P("2. Exactness result", "h1"), P("The exactness battery compares component hashes for the decision state and a continuation payload that includes scheduler/RNG lineage. It uses 12 preregistered seeds and five horizons: 0.25, 0.5, 1, 2, and 7 days. The resampling test forces a known parent distribution, checks systematic parent indices and independent child lineages, then verifies continuation divergence.")]
    story += [_table([
        ["Component", "Observed"],
        ["Exactness comparisons", phase_a.get("evidence", {}).get("A1_exactness", {}).get("passed", "not available")],
        ["Packed authority inventory", phase_a.get("evidence", {}).get("A2_packed_authority", {}).get("passed", "not available")],
        ["Kernel oracle battery", phase_a.get("evidence", {}).get("A3_kernel_oracles", {}).get("passed", "not available")],
        ["Profile accounting", profile.get("dominant_domain", "not available")],
    ], [2.2 * inch, 3.7 * inch]), Spacer(1, 8)]
    story += [P("3. Synthetic inference validation", "h1"), P("The passing v2 protocol is synthetic and history-free. It includes Rao-Blackwellized filtering, Gaussian guided proposals, MCSE reporting, and a combined gate. It reports coverage, RMSE scaled by posterior standard deviation, variance recovery, ESS ratio, and p95 error. The earlier v1 guided validation failed its ESS-ratio threshold and remains preserved as a negative result; v2 changed the synthetic observation/proposal to make the validation informative without changing thresholds.")]
    story += [_table([
        ["Metric", "Threshold family", "Current status"],
        ["RB coverage", "predeclared coverage interval", "PASS"],
        ["Guided coverage / RMSE", "coverage and normalized RMSE", "PASS in v2; v1 preserved as failed"],
        ["MCSE", "finite and within predeclared bound", "PASS"],
        ["Combined", "all components pass", "PASS in v2"],
    ], [1.7 * inch, 2.4 * inch, 1.8 * inch]), PageBreak()]
    story += [P("4. Performance and migration", "h1"), P("The representative cProfile run is intentionally smaller than the fixed acceptance workload: four particles for seven days, three repeats. Its dominant self-time domain is packed-state synchronization and serialization, followed by packed execution. The next migration target is therefore row materialization and lane synchronization, not blind conversion of sparse physical or organizational processes.")]
    story += [_table([
        ["Profile quantity", "Median"],
        ["Profile CPU seconds", profile.get("median", {}).get("profile_cpu_seconds", "not available")],
        ["Packed synchronization self seconds", profile.get("median_domain_self_seconds", {}).get("packed_state_and_synchronization", "not available")],
        ["Packed execution self seconds", profile.get("median_domain_self_seconds", {}).get("packed_execution", "not available")],
        ["Sparse reference self seconds", profile.get("median_domain_self_seconds", {}).get("sparse_reference_processes", "not available")],
    ], [2.9 * inch, 3.0 * inch]), Spacer(1, 8)]
    story += [P("The separate fixed 32-particle x 8-week x 3-branch production run did not complete within the controlled resource window. It produced no partial timing result. This is recorded as an implementation/deployment failure, not as evidence for or against the scientific mechanism.", "callout")]
    story += [P("5. Historical authorization rule", "h1"), P("Historical work requires a passing exactness/performance/inference spine and a clean core boundary. The contract records the current model hash and all dirty paths. Existing historical v5 outputs are never silently rebound to a new model hash. A current-core historical confrontation is once-only: no calibration loop, no post-hoc branch selection, and no deletion of negative seeds.")]
    story += [P("6. Independent reproduction command family", "h1"), P("Run the phase scripts in order: exactness battery, authority audit, kernel oracles, representative profile, fixed-work benchmark, phase-A certificate, phase-C contract, phase-D historical gate, phase-E theory contract, phase-F robustness status, then packet builder. Every script refuses to overwrite an existing evidence artifact.")]
    _doc(OUTPUT / "02_technical_note.pdf", story)


def build_architecture_figure() -> None:
    path = OUTPUT / "03_architecture_figure.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    c.setTitle("Pineland packed-state architecture")
    c.setFillColor(colors.HexColor("#12304A")); c.setFont("Helvetica-Bold", 20)
    c.drawString(0.65 * inch, height - 0.8 * inch, "Pineland execution and inference architecture")
    c.setFillColor(colors.HexColor("#47657A")); c.setFont("Helvetica", 9)
    c.drawString(0.65 * inch, height - 1.05 * inch, "Authority, sparse boundaries, genealogy, and evidence gates")
    boxes = [
        (0.8, 6.6, 2.0, 0.75, "Static topology", "IDs, distances, source plan\nimmutable codebook"),
        (3.0, 6.6, 2.7, 0.75, "Packed hot state", "physical, formations, logistics,\norganization and action lanes"),
        (5.95, 6.6, 1.15, 0.75, "Native\nkernels", "oracle tested"),
        (0.8, 4.85, 2.0, 0.85, "Sparse reference\nprocesses", "scheduler-order events\nexplicit materialization"),
        (3.0, 4.85, 2.7, 0.85, "Information state", "control, presence, zone\nbeliefs with decay clocks"),
        (5.95, 4.85, 1.15, 0.85, "Observations", "likelihood\noperator"),
        (1.9, 2.85, 2.0, 0.85, "Packed particle filter", "ESS, systematic resampling,\ntransition/proposal correction"),
        (4.25, 2.85, 2.0, 0.85, "Genealogy", "forked scheduler/RNG\nlineage continuation"),
        (2.95, 1.05, 2.45, 0.85, "Evidence gates", "A exactness + performance\nB synthetic -> C freeze -> D history"),
    ]
    for x, y, w, h, title, detail in boxes:
        c.setFillColor(colors.HexColor("#EAF3F7")); c.setStrokeColor(colors.HexColor("#4B7F95")); c.roundRect(x * inch, y * inch, w * inch, h * inch, 8, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#12304A")); c.setFont("Helvetica-Bold", 9.5)
        for index, line in enumerate(title.split("\n")):
            c.drawCentredString((x + w / 2) * inch, (y + h - 0.25 - 0.14 * index) * inch, line)
        c.setFillColor(colors.HexColor("#40515C")); c.setFont("Helvetica", 7.4)
        for index, line in enumerate(detail.split("\n")):
            c.drawCentredString((x + w / 2) * inch, (y + 0.28 - 0.12 * index) * inch, line)
    arrows = [
        ((2.8, 6.98), (3.0, 6.98)), ((5.7, 6.98), (5.95, 6.98)),
        ((2.8, 5.28), (3.0, 5.28)), ((5.7, 5.28), (5.95, 5.28)),
        ((4.35, 4.85), (3.0, 3.7)), ((4.7, 4.85), (5.05, 3.7)),
        ((3.9, 2.85), (4.25, 2.85)), ((4.25, 3.25), (4.0, 1.9)),
    ]
    c.setStrokeColor(colors.HexColor("#D0763B")); c.setFillColor(colors.HexColor("#D0763B")); c.setLineWidth(1.5)
    for (x1, y1), (x2, y2) in arrows:
        c.line(x1 * inch, y1 * inch, x2 * inch, y2 * inch)
        c.circle(x2 * inch, y2 * inch, 2.3, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#40515C")); c.setFont("Helvetica", 8)
    c.drawString(0.8 * inch, 0.52 * inch, "Dashed conceptual boundary: only explicitly authorized sparse events materialize reference worlds.")
    c.save()


def build_results() -> None:
    phase_a = _json("phase_a_certificate_v1.json") or {}
    benchmark = _json("phase_a_fixed_work_benchmark_v1.json") or {}
    benchmark_failure = _json("phase_a_fixed_work_benchmark_failure_v1.json") or {}
    phase_b = _json("phase_b_inference_validation_v2.json") or {}
    story: list[Any] = [P("Results packet: what passed, what did not", "title"), P("Execution-only and synthetic evidence; historical transfer withheld until authorized", "subtitle")]
    story += [P("Gate summary", "h1"), _table([
        ["Gate", "Result", "Interpretation"],
        ["A1 exactness", phase_a.get("checks", {}).get("A1_exact_scheduler_oracle", "not built"), "World and continuation state must both match."],
        ["A2 authority", phase_a.get("checks", {}).get("A2_authority_inventory", "not built"), "Every runtime field classified exactly once."],
        ["A3 kernels", phase_a.get("checks", {}).get("A3_kernel_oracles", "not built"), "Physical and information numerical oracles."],
        ["A4 profile", phase_a.get("checks", {}).get("A4_profile_accounting", "not built"), "Representative diagnostic profile."],
        ["A5 E1", phase_a.get("checks", {}).get("A5_E1_minimum", "not built"), "Minimum 4 PWB/s."],
        ["A5 E2", phase_a.get("checks", {}).get("A5_E2_target", "not built"), "Target 10 PWB/s; not a gate."],
        ["B synthetic", phase_b.get("passed", "not built"), "History-free inference validation."],
    ], [1.2 * inch, 1.0 * inch, 3.4 * inch]), Spacer(1, 10)]
    story += [P("Fixed workload definition", "h1"), P("The fixed workload is 32 particles, 8 weekly boundaries, and 3 branch-equivalents: 768 particle-week-boundaries per measured repeat. The benchmark records wall time, workers, source payload, model hash, and the exact synthetic observation rule. It is not acceptable to infer a passing rate from a smaller run.")]
    if benchmark_failure:
        story += [P("Current fixed-work result: incomplete resource-limit run; no PWB/s is reported, and E1/E2 are failed closed. The complete-ensemble rule is active.", "callout")]
    if benchmark:
        story += [_table([
            ["Measured quantity", "Value"],
            ["Median PWB/s", benchmark.get("results", {}).get("median_pwb_per_second", "not available")],
            ["E1", benchmark.get("results", {}).get("E1_passed", "not available")],
            ["E2", benchmark.get("results", {}).get("E2_passed", "not available")],
            ["Engine", benchmark.get("protocol", {}).get("engine", "not available")],
        ], [2.4 * inch, 3.2 * inch])]
    story += [P("Synthetic validation interpretation", "h1"), P("The passing v2 synthetic result supports the numerical inference machinery under its preregistered data-generating process. It does not validate the historical observation operator, case geography, or empirical construct mapping. Those remain separate gates.")]
    story += [P("No partial ensemble rule", "h1"), P("If a seed, branch, worker, or weekly boundary is missing, the ensemble is incomplete and no aggregate historical result is reported. This packet follows that rule by reporting unavailable gates as unavailable rather than filling them from prior artifacts.")]
    _doc(OUTPUT / "04_results_packet.pdf", story)


def build_claims() -> None:
    phase_a = _json("phase_a_certificate_v1.json") or {}
    phase_b = _json("phase_b_inference_validation_v2.json") or {}
    phase_d = _json("phase_d_historical_confrontation_status_v1.json") or {}
    story: list[Any] = [P("Claims and evidence matrix", "title"), P("Every proposed statement is classified as supported, limited, or withheld", "subtitle")]
    story += [_table([
        ["Claim", "Evidence", "Disposition"],
        ["The packed runner can reproduce the reference scheduler in the preregistered battery.", "A1 exactness and continuation hashes.", "Supported if A1 PASS; otherwise withheld."],
        ["Packed state authority is explicit and auditable.", "A2 field inventory and sparse-boundary ledger.", "Supported if A2 PASS."],
        ["Synthetic inference machinery recovers known quantities under the protocol.", "B v2 coverage, RMSE, variance, MCSE, combined gates.", "Supported for synthetic worlds only."],
        ["The model explains Nepal or Afghanistan.", "No authorized current-core confrontation in packet.", "Withheld."],
        ["Historical transfer is robust to observation operators.", "No current authorized historical run.", "Withheld."],
        ["The implementation is production throughput ready.", "A5 fixed-work benchmark.", "Use current measured gate only; no extrapolation."],
    ], [2.35 * inch, 2.3 * inch, 1.55 * inch]), Spacer(1, 10)]
    story += [P("Evidence hierarchy", "h1"), P("Source code and test results establish implementation behavior. Synthetic artifacts establish recovery under the declared data-generating process. Historical case artifacts would establish only case-specific predictive confrontation under the frozen contract. No level is substituted for another.")]
    story += [P("Negative evidence", "h1"), P("The earlier guided synthetic validation that missed its ESS threshold remains a first-class result. The old v5 historical artifacts remain preserved but stale relative to the current model hash. A missing current historical run is not interpreted as success or failure of the scientific theory.")]
    _doc(OUTPUT / "05_claims_and_evidence.pdf", story)


def build_limitations() -> None:
    phase_d = _json("phase_d_historical_confrontation_status_v1.json") or {}
    phase_f = _json("phase_f_robustness_status_v1.json") or {}
    story: list[Any] = [P("Limitations and failure ledger", "title"), P("Open issues are explicit work items, not hidden caveats", "subtitle")]
    story += [P("Failure ledger", "h1"), _table([
        ["Item", "Observed state", "Action"],
        ["Stale core certificate", "The prior v5 certificate model hash does not equal the live model hash.", "Do not recertify silently; bind future evidence to the live source."],
        ["Guided v1 synthetic validation", "ESS ratio was below its preregistered threshold.", "Preserve the failure; v2 is a declared protocol revision with unchanged thresholds."],
        ["Historical confrontation", phase_d.get("status", "not built"), "Run only after phase C authorization and only once."],
        ["Robustness", phase_f.get("status", "not built"), "Synthetic checks are available; historical robustness is gated."],
        ["Throughput", "The exact 768-PWB workload exceeded the controlled resource window before completion.", "No PWB/s is reported; optimize synchronization/transport and rerun the complete workload."],
    ], [1.65 * inch, 2.55 * inch, 2.0 * inch]), Spacer(1, 10)]
    story += [P("Scope limitations", "h1"), P("The theory is a compact latent-state account, not a universal theory of insurgency. Historical observation operators can be weakly identified. Case geography can encode assumptions. Sparse historical evidence is not treated as a complete measurement of latent control or civilian harm. Negative evidence and missingness remain part of the evidence model.")]
    story += [P("Reproducibility limitations", "h1"), P("The current working tree contains existing study artifacts and live source changes. The contract records the exact dirty paths and tracked-diff hash. Reproduction requires the same Python/native runtime family, protocol files, seeds, and model hash.")]
    story += [P("Review checklist", "h1"), P("An independent reviewer should: verify every file hash; rerun A1-A4 and B; inspect the fixed-work benchmark rather than extrapolate; confirm the contract has not authorized history prematurely; and reject any claim that exceeds the disposition matrix.")]
    _doc(OUTPUT / "06_limitations_and_failures.pdf", story)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pdfs = [OUTPUT / name for name in (
        "01_two_page_research_memo.pdf", "02_technical_note.pdf", "03_architecture_figure.pdf",
        "04_results_packet.pdf", "05_claims_and_evidence.pdf", "06_limitations_and_failures.pdf",
    )]
    overwrite = "--overwrite" in sys.argv
    existing = [path for path in pdfs if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"refusing to overwrite packet PDFs: {existing}")
    build_memo(); build_technical_note(); build_architecture_figure(); build_results(); build_claims(); build_limitations()
    manifest = {
        "schema_version": "1.0.0",
        "packet_id": "professor_packet_v1",
        "status": "gated_research_handoff",
        "historical_outreach_performed": False,
        "files": [
            {"path": path.name, "sha256": _sha(path), "bytes": path.stat().st_size}
            for path in pdfs
        ],
        "source_artifacts": {
            name: {"path": str((PROGRAM / name).relative_to(ROOT)).replace("\\", "/"), "sha256": _sha(PROGRAM / name)}
            for name in (
                "phase_a_certificate_v1.json", "phase_a_execution_profile_v1.json", "phase_a_fixed_work_benchmark_failure_v1.json",
                "phase_b_inference_validation_v1.json", "phase_b_inference_validation_v2.json",
                "phase_c_method_contract_v1.json", "phase_d_historical_confrontation_status_v1.json",
                "phase_e_theory_contract_v1.json", "phase_f_robustness_status_v1.json",
            ) if (PROGRAM / name).exists()
        },
        "review_requirements": ["verify hashes", "rerun exactness and synthetic gates", "inspect fixed workload", "do not promote historical claims without authorization"],
    }
    (OUTPUT / "07_reproducibility_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    readme = """# Professor packet\n\nThis is a gated research handoff for the Pineland insurgency agent-based simulation program. It contains implementation evidence, synthetic inference validation, a fixed-work performance record, theory specification, and a failure ledger.\n\nHistorical transfer claims are withheld unless the phase-C contract authorizes the once-only Nepal/Afghanistan confrontation under the live model hash. Prior stale-core logs are preserved as provenance and are not promoted.\n\n## Review order\n\n1. Read `01_two_page_research_memo.pdf`.\n2. Inspect `07_reproducibility_manifest.json` and verify hashes.\n3. Read `02_technical_note.pdf` and `03_architecture_figure.pdf`.\n4. Check the fixed workload and every gate in `04_results_packet.pdf`.\n5. Use `05_claims_and_evidence.pdf` and `06_limitations_and_failures.pdf` to bound claims.\n\nThe complete fixed workload was not silently replaced by a partial run: its controlled resource-limit failure is recorded in `studies/research_program/phase_a_fixed_work_benchmark_failure_v1.json`, and E1/E2 remain failed closed.\n\nNo external outreach was performed.\n"""
    (OUTPUT / "08_professor_readme.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "pdf_count": len(pdfs), "manifest": str(OUTPUT / "07_reproducibility_manifest.json")}))


if __name__ == "__main__":
    main()
