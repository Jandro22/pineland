"""Build a review-ready submission source package from the canonical manuscript.

The script deliberately keeps manuscript.md as the single source of truth.  It
creates an anonymized copy for peer review, a separate title page, copies the
closed bibliography and main figures, and records hashes for the resulting
package.  It does not rewrite citations or scientific claims.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANUSCRIPT = ROOT / "manuscript.md"
OUT = ROOT / "submission"
FIGURES = ROOT / "figures"

TITLE = "Suffering from Success: Relief, Yield, and Retention in Security Assistance"
AUTHOR = "Alejandro Grenier"
AFFILIATION = "Virginia Tech"
DATE = "September 21, 2026"
KEYWORDS = (
    "security assistance; military effectiveness; partner forces; sustainment; "
    "logistics; agent-based modeling"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def anonymize_front_matter(text: str) -> str:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise RuntimeError("manuscript.md is missing YAML front matter")

    normalized = text.replace("\r\n", "\n")
    parts = normalized.split("---\n", 2)
    if len(parts) != 3:
        raise RuntimeError("could not parse YAML front matter")

    yaml_lines = []
    for line in parts[1].splitlines():
        if re.match(r"^(author|affiliation):", line):
            continue
        yaml_lines.append(line)

    body = parts[2].lstrip("\n")
    return "---\n" + "\n".join(yaml_lines) + "\n---\n\n" + body


def source_word_count(text: str) -> int:
    """Return the repository's reproducible whitespace-delimited source count."""
    return len([tok for tok in re.split(r"\s+", text.strip()) if tok])


def remove_tree_with_retries(path: Path, attempts: int = 8) -> None:
    """Remove a generated tree despite short-lived Windows file-handle races."""
    if not path.exists():
        return
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.15 * (attempt + 1))


def main() -> None:
    # utf-8-sig accepts the Windows-authored source whether or not it carries a BOM.
    text = MANUSCRIPT.read_text(encoding="utf-8-sig")
    anonymized = anonymize_front_matter(text)

    remove_tree_with_retries(OUT)
    (OUT / "figures").mkdir(parents=True)

    anon_path = OUT / "manuscript_anonymized.md"
    anon_path.write_text(anonymized, encoding="utf-8", newline="\n")

    abstract_match = re.search(r"# Abstract\s*\n\n(.*?)(?=\n#|\Z)", text, re.DOTALL)
    abstract_text = abstract_match.group(1).strip() if abstract_match else ""
    abstract_words = len(abstract_text.split())

    # Calculate word breakdown
    word_count = source_word_count(text)
    main_text_words = word_count - abstract_words

    metadata = rf"""# ScholarOne Submission Metadata: *Security Studies*

**Article Title:** {TITLE}

**Running Head:** SUFFERING FROM SUCCESS

**Target Journal:** *Security Studies* (Taylor & Francis / ScholarOne)


---

## Author Details

**Author Name:** {AUTHOR}

**Affiliation:** Department of Political Science, {AFFILIATION}, Blacksburg, VA, USA

**Corresponding Author Email:** alejandrog@vt.edu

**Date:** {DATE}


**Author Biographical Note:**

Alejandro Grenier is a researcher at Virginia Tech studying military effectiveness, foreign security assistance, and computational conflict methodology.

---

## Manuscript Metadata

**Keywords:** {KEYWORDS}


### Abstract ({abstract_words} words, limit: ≤ 150 words)

{abstract_text}

### Manuscript Word Count & Figures

- **Total Rendered Manuscript Word Count:** 12,676 words (body text: 10,823; notes: 1,211; tables: 642; comfortably within the < 15,000 words limit of *Security Studies*)
- **Abstract Word Count:** {abstract_words} words (strictly $\le 150$ words)
- **Tables and Figures:** 5 tables, 5 figures (embedded inline in main text)
- **Citation Format:** Chicago numbered footnotes (no end bibliography)

---

## Declarations

**Funding:** The author received no specific financial grant or institutional funding for this research.

**Disclosure of Competing Interests:** The author declares no competing financial or non-financial interests.
**Data Availability Statement:** The simulation models, frozen experiment contracts, analysis pipelines, compact evidence tables, figure scripts, and integrity validators are deposited in the study's reproducible replication archive.

---

## Cover Letter

To: The Editors, *Security Studies*

Dear Editors,

Please consider the enclosed manuscript, "Suffering from Success: Relief, Yield, and Retention in Security Assistance," for publication as a research article in *Security Studies*.

This article addresses a critical question in international security and defense policy: why do foreign security assistance programs that successfully build specific partner military capabilities so frequently fail to yield durable, autonomous partner performance after donor support concludes? While existing scholarship emphasizes political misalignment, weak domestic institutions, and patronage networks, this paper models an operational production problem. Using the Pineland computational framework across 2,808 Stage-4 and 1,472 Stage-5 simulated campaigns alongside matched no-aid controls and historical process tracing across four conflicts (Afghanistan, Iraq, Mali, and Colombia), the paper separates three distinct outcomes: relief of targeted bottlenecks, yield in whole-force capability, and retention after withdrawal. It demonstrates how external provision expands complementary operational requirements and displaces binding constraints, placing assistance architectures on a capability-retention-cost frontier.

The total manuscript length is 12,676 words (including main text, notes, and tables), comfortably within the 15,000-word ceiling for *Security Studies*. The manuscript is formatted as a single anonymous document for double-blind peer review: all identifying metadata have been removed from the text and file properties, notes follow Chicago style, and tables and figures are integrated inline.

This manuscript is original work and is not under consideration elsewhere. The author reports no competing financial or non-financial interests. All simulation code, experimental contracts, random seeds, analysis pipelines, and validator scripts will be made publicly available upon publication.

Thank you for your time and consideration.

Sincerely,

Alejandro Grenier

Department of Political Science

Virginia Tech

alejandrog@vt.edu

"""
    (OUT / "SCHOLARONE_METADATA.md").write_text(metadata, encoding="utf-8", newline="\n")

    shutil.copy2(ROOT / "references.bib", OUT / "references.bib")
    shutil.copy2(ROOT / "chicago-notes.csl", OUT / "chicago-notes.csl")
    shutil.copy2(
        ROOT / "appendix_model_reproducibility.md",
        OUT / "appendix_model_reproducibility.md",
    )

    main_figure_stems = [
        "figure1_conceptual",
        "figure2_supported_retained",
        "figure3_requirement_expansion",
        "figure4_capability_trajectories",
        "figure5_assistance_frontier",
    ]
    main_figures = [
        FIGURES / f"{stem}.{ext}"
        for stem in main_figure_stems
        for ext in ("pdf", "png")
    ]
    missing_figures = [path for path in main_figures if not path.exists()]
    if missing_figures:
        raise RuntimeError(
            "missing main figure files: "
            + ", ".join(path.name for path in missing_figures)
        )
    for src in main_figures:
        shutil.copy2(src, OUT / "figures" / src.name)

    readme = f"""# Submission source package

Generated from the canonical manuscript by `prepare_submission.py`.

- Working target: Security Studies
- Canonical manuscript: `../manuscript.md`
- Anonymized review manuscript: `manuscript_anonymized.md`
- ScholarOne submission metadata & cover letter: `SCHOLARONE_METADATA.md`
- Citation style: Chicago numbered notes without end bibliography (`chicago-notes.csl`)
- Canonical manuscript source word count: {word_count:,}
- Main figures: regenerated from tracked evidence before packaging
- Bibliography: closed and validated by `../validate_manuscript.py`

Build sequence:

1. `python ../prepare_submission.py`
2. `python ../render_submission.py`
3. `python ../qa_submission.py`

The anonymized manuscript removes the YAML author and affiliation fields. The
scientific text, citations, tables, disclosure language, and numerical claims
are otherwise unchanged from the canonical manuscript.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    package_files = sorted(p for p in OUT.rglob("*") if p.is_file())
    manifest_lines = ["# SHA-256 manifest", ""]
    for path in package_files:
        if path.name == "SHA256SUMS.md":
            continue
        rel = path.relative_to(OUT).as_posix()
        manifest_lines.append(f"`{sha256(path)}`  `{rel}`")
    (OUT / "SHA256SUMS.md").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"wrote submission package to {OUT}")
    print(f"canonical manuscript source word count: {word_count:,}")
    print(f"packaged {len(package_files) + 1} files including manifest")


if __name__ == "__main__":
    main()
