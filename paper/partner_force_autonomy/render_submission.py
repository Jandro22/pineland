"""Render the review package to editable DOCX and Word-exported PDF files.

Run `prepare_submission.py` first.  Pandoc resolves citations and embeds the
tracked figures; python-docx applies conservative manuscript formatting and
removes identifying metadata from the anonymous file; Microsoft Word performs
the PDF export so the DOCX and PDF share the same pagination.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pypandoc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from win32com.client import DispatchEx


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "submission"
REFERENCE = OUT / "_reference.docx"
WORD_PDF_FORMAT = 17


def set_run_font(run, name: str = "Times New Roman", size: int = 12) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def make_reference_docx() -> None:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal.paragraph_format.line_spacing = 2
    normal.paragraph_format.space_after = Pt(0)

    for style_name in ("Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
        if style_name not in doc.styles:
            continue
        style = doc.styles[style_name]
        style.font.name = "Times New Roman"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        style.paragraph_format.keep_with_next = True
        if style_name == "Title":
            style.font.size = Pt(14)
            style.font.bold = True
            style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            style.font.size = Pt(12)
            style.font.bold = True
            style.paragraph_format.line_spacing = 2
            style.paragraph_format.space_before = Pt(6)
            style.paragraph_format.space_after = Pt(0)

    if "Caption" in doc.styles:
        cap = doc.styles["Caption"]
        cap.font.name = "Times New Roman"
        cap.font.size = Pt(10)
        cap._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        cap.paragraph_format.line_spacing = 1

    doc.save(REFERENCE)


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    set_run_font(run, size=10)
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr)
    run._r.append(fld_char2)


def postprocess_docx(path: Path, anonymous: bool) -> None:
    doc = Document(path)
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        footer = section.footer
        if not footer.paragraphs:
            footer.add_paragraph()
        footer.paragraphs[0].clear()
        add_page_number(footer.paragraphs[0])

    # Keep tables readable without letting double spacing make them enormous.
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.line_spacing = 1
                    paragraph.paragraph_format.space_after = Pt(0)
                    for run in paragraph.runs:
                        set_run_font(run, size=9)

    # Center paragraphs containing embedded figures.
    for paragraph in doc.paragraphs:
        if paragraph._p.xpath(".//w:drawing"):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    props = doc.core_properties
    if anonymous:
        props.author = ""
        props.last_modified_by = ""
        props.comments = ""
        props.subject = ""
        props.keywords = ""
    else:
        props.author = "Alejandro Grenier"
        props.last_modified_by = "Alejandro Grenier"

    doc.save(path)


def pandoc_docx(src: Path, dst: Path, citeproc: bool) -> None:
    args = [
        f"--reference-doc={REFERENCE}",
        f"--resource-path={OUT}",
        "--standalone",
    ]
    if citeproc:
        args.extend(["--citeproc", f"--bibliography={OUT / 'references.bib'}"])
    pypandoc.convert_file(
        str(src),
        to="docx",
        format="markdown",
        outputfile=str(dst),
        extra_args=args,
    )


def export_pdf(docx_path: Path, pdf_path: Path) -> None:
    word = DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = None
    try:
        doc = word.Documents.Open(str(docx_path.resolve()), ReadOnly=True)
        doc.ExportAsFixedFormat(str(pdf_path.resolve()), WORD_PDF_FORMAT)
    finally:
        if doc is not None:
            doc.Close(False)
        word.Quit()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def refresh_manifest() -> None:
    manifest = OUT / "SHA256SUMS.md"
    paths = sorted(
        p
        for p in OUT.rglob("*")
        if p.is_file() and p.name not in {"SHA256SUMS.md", "_reference.docx"}
    )
    lines = ["# SHA-256 manifest", ""]
    for path in paths:
        lines.append(f"`{sha256(path)}`  `{path.relative_to(OUT).as_posix()}`")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    if not (OUT / "manuscript_anonymized.md").exists():
        raise RuntimeError("run prepare_submission.py before render_submission.py")

    make_reference_docx()

    manuscript_docx = OUT / "manuscript_anonymized.docx"
    manuscript_pdf = OUT / "manuscript_anonymized.pdf"
    title_docx = OUT / "title_page.docx"
    title_pdf = OUT / "title_page.pdf"

    pandoc_docx(OUT / "manuscript_anonymized.md", manuscript_docx, citeproc=True)
    postprocess_docx(manuscript_docx, anonymous=True)
    export_pdf(manuscript_docx, manuscript_pdf)

    pandoc_docx(OUT / "title_page.md", title_docx, citeproc=False)
    postprocess_docx(title_docx, anonymous=False)
    export_pdf(title_docx, title_pdf)

    REFERENCE.unlink(missing_ok=True)
    refresh_manifest()
    print(f"rendered {manuscript_docx.name} and {manuscript_pdf.name}")
    print(f"rendered {title_docx.name} and {title_pdf.name}")


if __name__ == "__main__":
    main()
