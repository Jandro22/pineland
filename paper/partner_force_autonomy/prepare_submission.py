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


def main() -> None:
    # utf-8-sig accepts the Windows-authored source whether or not it carries a BOM.
    text = MANUSCRIPT.read_text(encoding="utf-8-sig")
    anonymized = anonymize_front_matter(text)

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "figures").mkdir(parents=True)

    anon_path = OUT / "manuscript_anonymized.md"
    anon_path.write_text(anonymized, encoding="utf-8", newline="\n")

    word_count = source_word_count(text)
    title_page = f"""# {TITLE}

**Author:** {AUTHOR}  
**Affiliation:** {AFFILIATION}  
**Date:** {DATE}  
**Keywords:** {KEYWORDS}  
**Canonical manuscript source word count:** {word_count:,}

The word count is the repository's deterministic whitespace-delimited count of
`manuscript.md`. A journal submission system may calculate its displayed count
differently after citation and document rendering.
"""
    (OUT / "title_page.md").write_text(title_page, encoding="utf-8", newline="\n")

    shutil.copy2(ROOT / "references.bib", OUT / "references.bib")
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
- Separate author/title page: `title_page.md`
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
