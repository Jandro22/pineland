"""Structural QA for the rendered anonymous submission package."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import fitz
from docx import Document


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "submission"
PDF = OUT / "manuscript_anonymized.pdf"
DOCX = OUT / "manuscript_anonymized.docx"

IDENTIFIER = re.compile(r"Alejandro|Grenier|Virginia Tech|vt\.edu", re.I)
RAW_CITATION = re.compile(r"\[@|@\w")


def fail(msg: str, errors: list[str]) -> None:
    errors.append(msg)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    errors: list[str] = []
    notes: list[str] = []

    if not PDF.exists() or not DOCX.exists():
        raise SystemExit("rendered anonymous DOCX/PDF are missing")

    pdf = fitz.open(PDF)
    if pdf.page_count == 0:
        fail("PDF has zero pages", errors)

    page_texts: list[str] = []
    image_rects: list[tuple[int, tuple[float, float, float, float]]] = []
    orphan_candidates: list[tuple[int, float, str]] = []
    unexpected_footer_numbers: list[tuple[int, str]] = []
    out_of_page: list[tuple[int, tuple[float, float, float, float], str]] = []
    tiny_text: list[tuple[int, float, str]] = []

    for page_index, page in enumerate(pdf, start=1):
        if abs(page.rect.width - 612.0) > 0.5 or abs(page.rect.height - 792.0) > 0.5:
            fail(f"page {page_index} is not US Letter", errors)

        text = page.get_text()
        page_texts.append(text)
        if len(text.strip()) < 40:
            fail(f"page {page_index} is unexpectedly blank/near-blank", errors)

        blocks = page.get_text("blocks")
        for block in blocks:
            x0, y0, x1, y1, block_text, *_ = block
            if x0 < -0.5 or y0 < -0.5 or x1 > page.rect.width + 0.5 or y1 > page.rect.height + 0.5:
                out_of_page.append(
                    (page_index, (x0, y0, x1, y1), " ".join(block_text.split())[:80])
                )

            cleaned = " ".join(block_text.split())
            if y0 > 700 and re.match(
                r"^(Abstract|[1-9]\.\s|Data, Code|Disclosure|References)", cleaned
            ):
                orphan_candidates.append((page_index, y0, cleaned[:100]))

        # ScholarOne requires unpaginated manuscript (pagination injected by ScholarOne).
        # Check that no standalone page numbers are present in the footer margin.
        footer_text = " ".join(
            block[4].strip() for block in blocks if block[1] > 745
        )
        if re.search(r"^\d+$", footer_text.strip()):
            unexpected_footer_numbers.append((page_index, footer_text))

        page_dict = page.get_text("dict")
        for block in page_dict["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if text and span["size"] < 8.8:
                        # Word legitimately shrinks fraction numerators,
                        # denominators, superscripts, and subscripts inside
                        # equations (standard 8.52pt for 12pt body equations)
                        # and footnote references/callouts (6.9-8.0pt).
                        font = span.get("font", "")
                        is_math_or_fn = bool(
                            "Math" in font
                            or any(ord(c) > 0x2000 for c in text)
                            or re.search(r"[\\{}_=>^+\-*/()]", text)
                            or re.fullmatch(r"[A-Za-z]+-[A-Za-z]+", text)
                            or text.isdigit()
                            or re.fullmatch(r"[0-9, ]+", text)
                            or text in {
                                "fg", "log", "cmd", "pres", "move", "patrol",
                                "combat", "depot", "1/5", "ON", "OFF", "opt",
                            }
                        )
                        if not is_math_or_fn:
                            tiny_text.append(
                                (page_index, span["size"], text[:50])
                            )

        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                image_rects.append(
                    (page_index, (rect.x0, rect.y0, rect.x1, rect.y1))
                )
                if (
                    rect.x0 < -0.5
                    or rect.y0 < -0.5
                    or rect.x1 > page.rect.width + 0.5
                    or rect.y1 > page.rect.height + 0.5
                ):
                    fail(f"image on page {page_index} extends outside page bounds", errors)

        # Ensure 100% black and white / grayscale text (no blue accents)
        for b in page_dict["blocks"]:
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    color = span.get("color", 0)
                    r = (color >> 16) & 255
                    g = (color >> 8) & 255
                    b_col = color & 255
                    if not (r == g == b_col):
                        fail(f"non-grayscale text detected on page {page_index}: RGB({r},{g},{b_col}) in {span['text'][:30]}", errors)

        # Ensure 100% black and white / grayscale drawings
        for d in page.get_drawings():
            for key in ("color", "fill"):
                val = d.get(key)
                if val and len(val) >= 3:
                    r, g, b_val = val[:3]
                    if not (abs(r - g) < 1e-3 and abs(g - b_val) < 1e-3):
                        fail(f"non-grayscale vector drawing on page {page_index}: {key}={val}", errors)

    all_text = "\n".join(page_texts)
    if RAW_CITATION.search(all_text):
        fail("raw Pandoc citation token remains in PDF", errors)
    if IDENTIFIER.search(all_text):
        fail("identifying author string remains in anonymous PDF", errors)
    for number in range(1, 6):
        if f"Figure {number}." not in all_text:
            fail(f"Figure {number} caption missing from PDF text", errors)
        if f"Table {number}." not in all_text:
            fail(f"Table {number} caption missing from PDF text", errors)

    if out_of_page:
        fail(f"{len(out_of_page)} text blocks extend outside page bounds", errors)
    if unexpected_footer_numbers:
        fail(
            "unintended footer page numbers detected on pages: "
            + ", ".join(f"{p} ({t})" for p, t in unexpected_footer_numbers),
            errors,
        )
    if tiny_text:
        fail(
            f"{len(tiny_text)} text spans are smaller than 8.8 pt: {tiny_text[:12]}",
            errors,
        )
    if len(image_rects) < 5:
        fail(f"only {len(image_rects)} embedded image placements detected", errors)

    # Check for no bibliography section
    if re.search(r"\n#+\s*References\b", all_text, re.I):
        fail("bibliography heading found in PDF", errors)
    isolated_ref = [
        b[4].strip()
        for page in pdf
        for b in page.get_text("blocks")
        if b[4].strip() == "References"
    ]
    if isolated_ref:
        fail("isolated 'References' heading block found in PDF", errors)

    # Check abstract word count
    abstract_m = re.search(r"Abstract\s*\n+(.*?)(?=\n1\.\s|\Z)", all_text, re.S)
    if abstract_m:
        ab_words = len(abstract_m.group(1).strip().split())
        if ab_words > 150:
            fail(f"abstract word count ({ab_words}) exceeds 150 words", errors)
        notes.append(f"abstract words: {ab_words}")

    # Inspect all XML parts, not just core properties, for blind-review leaks and footnotes.
    with zipfile.ZipFile(DOCX) as archive:
        xml = "\n".join(
            archive.read(name).decode("utf-8", "ignore")
            for name in archive.namelist()
            if name.endswith(".xml")
        )
        if "word/footnotes.xml" not in archive.namelist():
            fail("DOCX does not contain word/footnotes.xml", errors)
        else:
            fn_xml = archive.read("word/footnotes.xml").decode("utf-8")
            fn_count = len(re.findall(r'<w:footnote[^>]*w:id="[1-9][0-9]*"', fn_xml))
            if fn_count == 0:
                fail("zero footnotes detected in word/footnotes.xml", errors)
            notes.append(f"numbered footnotes: {fn_count}")

    if IDENTIFIER.search(xml):
        fail("identifying author string remains in anonymous DOCX XML", errors)
    if RAW_CITATION.search(xml):
        fail("raw Pandoc citation token remains in anonymous DOCX XML", errors)

    doc = Document(DOCX)
    props = doc.core_properties
    for field in ("author", "last_modified_by", "subject", "keywords"):
        if getattr(props, field):
            fail(f"anonymous DOCX core property {field} is not blank", errors)

    notes.append(f"pages: {pdf.page_count}")
    notes.append(f"embedded image placements: {len(image_rects)}")
    notes.append(f"orphan heading candidates: {orphan_candidates or 'none'}")

    if errors:
        print("FAIL submission QA")
        for error in errors:
            print(f"- {error}")
        for note in notes:
            print(f"- {note}")
        sys.exit(1)

    print("PASS submission QA")
    for note in notes:
        print(f"- {note}")


if __name__ == "__main__":
    main()
