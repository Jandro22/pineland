"""Render the review package to editable DOCX and Word-exported PDF files.

Run `prepare_submission.py` first.  Pandoc resolves citations and embeds the
tracked figures; python-docx applies conservative manuscript formatting,
enforces strict black-and-white typography and Booktabs table styling,
and removes identifying metadata from the anonymous file; Microsoft Word
performs the PDF export so the DOCX and PDF share the same pagination.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pypandoc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor
from win32com.client import DispatchEx


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "submission"
REFERENCE = OUT / "_reference.docx"
WORD_PDF_FORMAT = 17


def set_run_font(run, name: str = "Times New Roman", size: float = 12) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    run.font.color.theme_color = None
    rPr = run._element.rPr
    if rPr is not None:
        rPr.rFonts.set(qn("w:eastAsia"), name)
        color = rPr.find(qn("w:color"))
        if color is not None:
            color.attrib.pop(qn("w:themeColor"), None)
            color.attrib.pop(qn("w:themeShade"), None)
            color.attrib.pop(qn("w:themeTint"), None)
            color.set(qn("w:val"), "000000")


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
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.font.color.theme_color = None
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal.paragraph_format.line_spacing = 2
    normal.paragraph_format.space_after = Pt(0)

    for style_name in (
        "Title",
        "Subtitle",
        "Heading 1",
        "Heading 2",
        "Heading 3",
        "Caption",
        "Hyperlink",
        "Body Text",
        "First Paragraph",
        "Bibliography",
    ):
        if style_name not in doc.styles:
            continue
        style = doc.styles[style_name]
        style.font.name = "Times New Roman"
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.color.theme_color = None
        if hasattr(style, "_element") and style._element.rPr is not None:
            style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
            color = style._element.rPr.find(qn("w:color"))
            if color is not None:
                color.attrib.pop(qn("w:themeColor"), None)
                color.attrib.pop(qn("w:themeShade"), None)
                color.attrib.pop(qn("w:themeTint"), None)
                color.set(qn("w:val"), "000000")

        # Strip any paragraph borders (e.g. blue line under Title)
        if hasattr(style, "_element") and style._element.pPr is not None:
            pBdr = style._element.pPr.find(qn("w:pBdr"))
            if pBdr is not None:
                style._element.pPr.remove(pBdr)

        if style_name == "Title":
            style.font.size = Pt(14)
            style.font.bold = True
            style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.first_line_indent = Inches(0)
        elif style_name == "Subtitle":
            style.font.size = Pt(12)
            style.font.italic = True
            style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.first_line_indent = Inches(0)
        elif style_name == "Heading 1":
            style.font.size = Pt(12)
            style.font.bold = True
            style.paragraph_format.line_spacing = 2
            style.paragraph_format.space_before = Pt(12)
            style.paragraph_format.space_after = Pt(0)
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.first_line_indent = Inches(0)
        elif style_name == "Heading 2":
            style.font.size = Pt(12)
            style.font.bold = True
            style.font.italic = True
            style.paragraph_format.line_spacing = 2
            style.paragraph_format.space_before = Pt(6)
            style.paragraph_format.space_after = Pt(0)
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.first_line_indent = Inches(0)
        elif style_name == "Heading 3":
            style.font.size = Pt(12)
            style.font.italic = True
            style.paragraph_format.line_spacing = 2
            style.paragraph_format.space_before = Pt(6)
            style.paragraph_format.space_after = Pt(0)
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.first_line_indent = Inches(0)
        elif style_name == "Caption":
            style.font.size = Pt(10)
            style.paragraph_format.line_spacing = 1.15
            style.paragraph_format.space_before = Pt(6)
            style.paragraph_format.space_after = Pt(12)
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.first_line_indent = Inches(0)
        elif style_name in ("Body Text", "First Paragraph"):
            style.font.size = Pt(12)
            style.paragraph_format.line_spacing = 2
            style.paragraph_format.space_before = Pt(0)
            style.paragraph_format.space_after = Pt(0)
            style.paragraph_format.first_line_indent = Inches(0.5)
        elif style_name == "Bibliography":
            style.font.size = Pt(12)
            style.paragraph_format.line_spacing = 2
            style.paragraph_format.space_before = Pt(0)
            style.paragraph_format.space_after = Pt(0)
            style.paragraph_format.left_indent = Inches(0.5)
            style.paragraph_format.first_line_indent = Inches(-0.5)
        elif style_name == "Footnote Text":
            style.font.name = "Times New Roman"
            style.font.size = Pt(10)
            style.font.color.rgb = RGBColor(0, 0, 0)
            style.font.color.theme_color = None
            style.paragraph_format.line_spacing = 1.05
            style.paragraph_format.space_before = Pt(0)
            style.paragraph_format.space_after = Pt(2)
            style.paragraph_format.first_line_indent = Inches(0)
        elif style_name == "Footnote Reference":
            style.font.name = "Times New Roman"
            style.font.color.rgb = RGBColor(0, 0, 0)
            style.font.color.theme_color = None

    doc.save(REFERENCE)


def postprocess_footnotes_xml(docx_path: Path) -> None:
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ET.register_namespace("w", w_ns)
    ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")

    with zipfile.ZipFile(docx_path, "r") as z_in:
        file_map = {name: z_in.read(name) for name in z_in.namelist()}

    if "word/footnotes.xml" not in file_map:
        return

    root = ET.fromstring(file_map["word/footnotes.xml"])
    for fn in root.findall(f"{{{w_ns}}}footnote"):
        fn_id = fn.get(f"{{{w_ns}}}id")
        if fn_id is not None and int(fn_id) <= 0:
            continue
        for p in fn.findall(f"{{{w_ns}}}p"):
            pPr = p.find(f"{{{w_ns}}}pPr")
            if pPr is None:
                pPr = ET.Element(f"{{{w_ns}}}pPr")
                p.insert(0, pPr)
            pBdr = pPr.find(f"{{{w_ns}}}pBdr")
            if pBdr is not None:
                pPr.remove(pBdr)
            spacing = pPr.find(f"{{{w_ns}}}spacing")
            if spacing is None:
                spacing = ET.Element(f"{{{w_ns}}}spacing")
                pPr.append(spacing)
            spacing.set(f"{{{w_ns}}}after", "40")
            spacing.set(f"{{{w_ns}}}before", "0")
            spacing.set(f"{{{w_ns}}}line", "240")
            spacing.set(f"{{{w_ns}}}lineRule", "auto")

            for r in p.findall(f"{{{w_ns}}}r"):
                rPr = r.find(f"{{{w_ns}}}rPr")
                if rPr is None:
                    rPr = ET.Element(f"{{{w_ns}}}rPr")
                    r.insert(0, rPr)
                rFonts = rPr.find(f"{{{w_ns}}}rFonts")
                if rFonts is None:
                    rFonts = ET.Element(f"{{{w_ns}}}rFonts")
                    rPr.append(rFonts)
                rFonts.set(f"{{{w_ns}}}ascii", "Times New Roman")
                rFonts.set(f"{{{w_ns}}}hAnsi", "Times New Roman")
                rFonts.set(f"{{{w_ns}}}cs", "Times New Roman")
                rFonts.set(f"{{{w_ns}}}eastAsia", "Times New Roman")

                color = rPr.find(f"{{{w_ns}}}color")
                if color is None:
                    color = ET.Element(f"{{{w_ns}}}color")
                    rPr.append(color)
                for attr in list(color.attrib.keys()):
                    if "theme" in attr.lower():
                        del color.attrib[attr]
                color.set(f"{{{w_ns}}}val", "000000")

                rStyle = rPr.find(f"{{{w_ns}}}rStyle")
                is_ref = rStyle is not None and "FootnoteReference" in rStyle.get(f"{{{w_ns}}}val", "")
                if not is_ref:
                    sz = rPr.find(f"{{{w_ns}}}sz")
                    if sz is None:
                        sz = ET.Element(f"{{{w_ns}}}sz")
                        rPr.append(sz)
                    sz.set(f"{{{w_ns}}}val", "20")
                    szCs = rPr.find(f"{{{w_ns}}}szCs")
                    if szCs is None:
                        szCs = ET.Element(f"{{{w_ns}}}szCs")
                        rPr.append(szCs)
                    szCs.set(f"{{{w_ns}}}val", "20")

    file_map["word/footnotes.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as z_out:
        for name, content in file_map.items():
            z_out.writestr(name, content)


def postprocess_docx(path: Path, anonymous: bool) -> None:
    doc = Document(path)
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        # ScholarOne injects its own pagination and header banners; keep header and footer empty
        for h_p in section.header.paragraphs:
            h_p.clear()
        for f_p in section.footer.paragraphs:
            f_p.clear()

    # Strip theme color and enforce pure black on all styles
    for style in doc.styles:
        if hasattr(style, "font") and style.font is not None:
            style.font.color.rgb = RGBColor(0, 0, 0)
            style.font.color.theme_color = None
        sPr = getattr(style._element, "pPr", None)
        if sPr is not None:
            pBdr = sPr.find(qn("w:pBdr"))
            if pBdr is not None:
                sPr.remove(pBdr)
        rPr = getattr(style._element, "rPr", None)
        if rPr is not None:
            color = rPr.find(qn("w:color"))
            if color is not None:
                color.attrib.pop(qn("w:themeColor"), None)
                color.attrib.pop(qn("w:themeShade"), None)
                color.attrib.pop(qn("w:themeTint"), None)
                color.set(qn("w:val"), "000000")

    # Format paragraphs: strip blue borders, enforce black, handle figures, captions, headings, bibliography, and indentation
    in_references = False
    for paragraph in doc.paragraphs:
        pPr = paragraph._element.pPr
        if pPr is not None:
            pBdr = pPr.find(qn("w:pBdr"))
            if pBdr is not None:
                pPr.remove(pBdr)

        for run in paragraph.runs:
            run.font.color.rgb = RGBColor(0, 0, 0)
            run.font.color.theme_color = None
            rPr = run._element.rPr
            if rPr is not None:
                color = rPr.find(qn("w:color"))
                if color is not None:
                    color.attrib.pop(qn("w:themeColor"), None)
                    color.attrib.pop(qn("w:themeShade"), None)
                    color.attrib.pop(qn("w:themeTint"), None)
                    color.set(qn("w:val"), "000000")

        text = paragraph.text.strip()
        style_name = paragraph.style.name if paragraph.style else ""

        if not text and not paragraph._p.xpath(".//w:drawing"):
            continue

        # Detect start of references
        if text.lower() == "references" or text.startswith("# References"):
            in_references = True
            paragraph.paragraph_format.first_line_indent = Inches(0)
            paragraph.paragraph_format.left_indent = Inches(0)
            paragraph.paragraph_format.keep_with_next = True
            paragraph.paragraph_format.line_spacing = 2
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                set_run_font(run, size=12)
                run.font.bold = True
                run.font.italic = False
            continue

        # Handle bibliography entries
        if in_references or style_name == "Bibliography":
            paragraph.paragraph_format.left_indent = Inches(0.5)
            paragraph.paragraph_format.first_line_indent = Inches(-0.5)
            paragraph.paragraph_format.line_spacing = 2
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                set_run_font(run, size=12)
            continue

        # Handle embedded figures: center and keep with caption on same page
        if paragraph._p.xpath(".//w:drawing"):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.keep_with_next = True
            paragraph.paragraph_format.first_line_indent = Inches(0)
            paragraph.paragraph_format.left_indent = Inches(0)
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(6)

        # Handle figure captions: single-spaced 10pt, below image
        elif text.startswith("Figure "):
            paragraph.paragraph_format.line_spacing = 1.15
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(12)
            paragraph.paragraph_format.keep_with_next = False
            paragraph.paragraph_format.first_line_indent = Inches(0)
            paragraph.paragraph_format.left_indent = Inches(0)
            for run in paragraph.runs:
                set_run_font(run, size=10)

        # Handle table captions: single-spaced 10pt, above table
        elif text.startswith("Table "):
            paragraph.paragraph_format.line_spacing = 1.15
            paragraph.paragraph_format.space_before = Pt(12)
            paragraph.paragraph_format.space_after = Pt(4)
            paragraph.paragraph_format.keep_with_next = True
            paragraph.paragraph_format.first_line_indent = Inches(0)
            paragraph.paragraph_format.left_indent = Inches(0)
            for run in paragraph.runs:
                set_run_font(run, size=10)

        # Handle display math equations (oMathPara)
        elif paragraph._element.xpath(".//m:oMathPara"):
            paragraph.paragraph_format.first_line_indent = Inches(0)
            paragraph.paragraph_format.left_indent = Inches(0)
            paragraph.paragraph_format.space_before = Pt(6)
            paragraph.paragraph_format.space_after = Pt(6)

        # Handle Title and Date
        elif style_name in ("Title", "Subtitle") or text.startswith("Suffering from Success:") or text == "September 21, 2026":
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Inches(0)
            paragraph.paragraph_format.left_indent = Inches(0)
            paragraph.paragraph_format.keep_with_next = True
            if style_name == "Title" or text.startswith("Suffering from Success:"):
                for run in paragraph.runs:
                    set_run_font(run, size=14)
                    run.font.bold = True
            else:
                for run in paragraph.runs:
                    set_run_font(run, size=12)

        # Handle headings
        elif (
            style_name.startswith("Heading")
            or text.startswith("Abstract")
            or text.startswith("Data, Code")
            or text.startswith("Disclosure")
            or re.match(r"^[1-9]\.\s", text)
            or re.match(r"^[1-9]\.[0-9]+\s", text)
        ):
            paragraph.paragraph_format.first_line_indent = Inches(0)
            paragraph.paragraph_format.left_indent = Inches(0)
            paragraph.paragraph_format.keep_with_next = True
            paragraph.paragraph_format.line_spacing = 2
            paragraph.paragraph_format.space_after = Pt(0)

            is_level2 = bool(re.match(r"^[1-9]\.[0-9]+\s", text)) or style_name == "Heading 2"
            if is_level2:
                paragraph.paragraph_format.space_before = Pt(6)
                for run in paragraph.runs:
                    set_run_font(run, size=12)
                    run.font.bold = True
                    run.font.italic = True
            else:
                paragraph.paragraph_format.space_before = Pt(12)
                for run in paragraph.runs:
                    set_run_font(run, size=12)
                    run.font.bold = True
                    run.font.italic = False

        # Regular narrative body paragraph
        else:
            paragraph.paragraph_format.first_line_indent = Inches(0.5)
            paragraph.paragraph_format.left_indent = Inches(0)
            paragraph.paragraph_format.line_spacing = 2
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                set_run_font(run, size=12)

    # Format tables to Booktabs academic standard
    for table in doc.tables:
        tblPr = table._element.tblPr
        jc = tblPr.find(qn("w:jc"))
        if jc is None:
            tblPr.append(parse_xml(f'<w:jc {nsdecls("w")} w:val="center"/>'))
        else:
            jc.set(qn("w:val"), "center")

        # Booktabs borders: top 1.5pt, bottom 1.5pt, no vertical or inside borders
        old_bdr = tblPr.find(qn("w:tblBorders"))
        if old_bdr is not None:
            tblPr.remove(old_bdr)
        tblBorders = parse_xml(f'''
            <w:tblBorders {nsdecls("w")}>
                <w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>
                <w:left w:val="none"/>
                <w:bottom w:val="single" w:sz="12" w:space="0" w:color="000000"/>
                <w:right w:val="none"/>
                <w:insideH w:val="none"/>
                <w:insideV w:val="none"/>
            </w:tblBorders>
        ''')
        tblPr.append(tblBorders)

        # Generous cell margins (padding)
        old_mar = tblPr.find(qn("w:tblCellMar"))
        if old_mar is not None:
            tblPr.remove(old_mar)
        tblCellMar = parse_xml(f'''
            <w:tblCellMar {nsdecls("w")}>
                <w:top w:w="120" w:type="dxa"/>
                <w:bottom w:w="120" w:type="dxa"/>
                <w:left w:w="160" w:type="dxa"/>
                <w:right w:w="160" w:type="dxa"/>
            </w:tblCellMar>
        ''')
        tblPr.append(tblCellMar)

        num_rows = len(table.rows)
        for idx, row in enumerate(table.rows):
            trPr = row._tr.get_or_add_trPr()
            trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))

            # Header row formatting
            if idx == 0:
                trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))
                for cell in row.cells:
                    tcPr = cell._element.get_or_add_tcPr()
                    tcBorders = parse_xml(f'''
                        <w:tcBorders {nsdecls("w")}>
                            <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>
                            <w:top w:val="none"/>
                            <w:left w:val="none"/>
                            <w:right w:val="none"/>
                        </w:tcBorders>
                    ''')
                    tcPr.append(tcBorders)
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.font.bold = True

            # Total / Summary row formatting
            first_text = row.cells[0].text.strip().lower()
            if "total" in first_text and idx > 0:
                for cell in row.cells:
                    tcPr = cell._element.get_or_add_tcPr()
                    tcBorders = parse_xml(f'''
                        <w:tcBorders {nsdecls("w")}>
                            <w:top w:val="single" w:sz="6" w:space="0" w:color="000000"/>
                        </w:tcBorders>
                    ''')
                    tcPr.append(tcBorders)
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.font.bold = True

            # Keep small tables together on one page
            if num_rows <= 12 and idx < num_rows - 1:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        p.paragraph_format.keep_with_next = True

            # Cell text styling
            for cell in row.cells:
                tcPr = cell._element.get_or_add_tcPr()
                shd = tcPr.find(qn("w:shd"))
                if shd is not None:
                    tcPr.remove(shd)
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent = Inches(0)
                    p.paragraph_format.left_indent = Inches(0)
                    p.paragraph_format.line_spacing = 1.05
                    p.paragraph_format.space_after = Pt(2)
                    p.paragraph_format.space_before = Pt(2)
                    for r in p.runs:
                        set_run_font(r, size=9.5)

    if path.name == "title_page.docx":
        for p in doc.paragraphs:
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.first_line_indent = Inches(0)

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
        csl_path = OUT / "chicago-notes.csl"
        if not csl_path.exists():
            csl_path = ROOT / "chicago-notes.csl"
        args.extend([
            "--citeproc",
            f"--bibliography={OUT / 'references.bib'}",
            f"--csl={csl_path}",
        ])
    pypandoc.convert_file(
        str(src),
        to="docx",
        format="markdown+tex_math_single_backslash",
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

    pandoc_docx(OUT / "manuscript_anonymized.md", manuscript_docx, citeproc=True)
    postprocess_docx(manuscript_docx, anonymous=True)
    postprocess_footnotes_xml(manuscript_docx)
    export_pdf(manuscript_docx, manuscript_pdf)

    REFERENCE.unlink(missing_ok=True)
    refresh_manifest()
    print(f"rendered {manuscript_docx.name} and {manuscript_pdf.name}")


if __name__ == "__main__":
    main()
