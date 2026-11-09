"""PDF page → text lines in reading order, with the style info needed to find headings.

The ERGO documents use a two-column layout with occasional full-width rows (titles, intro text).
Reading order: within each horizontal band between full-width rows, the left column top-to-bottom,
then the right column.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pymupdf

BOLD_FONT_MARKERS = ("Bold", "Heavy", "Black")
# Private-use glyphs from symbol fonts used as list markers.
SYMBOL_MAP = str.maketrans({"": "•", "": "–", "": "•"})
# Any other private-use glyph is a list marker too (checkmarks, arrows).
PRIVATE_USE_RE = re.compile("[-]")
SAME_ROW_TOLERANCE = 4.0
COLUMN_TOLERANCE = 10.0
# A line starting in the left half that reaches past this share of the page width spans both columns.
FULL_WIDTH_FRACTION = 0.7

Column = Literal["left", "right", "full"]


@dataclass
class Line:
    page: int  # 1-based page number in the PDF
    x0: float
    y0: float
    x1: float
    text: str
    size: float  # font size of the first non-blank span
    bold: bool  # every non-blank span is bold
    column: Column


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or any(m in span["font"] for m in BOLD_FONT_MARKERS)


def _column(x0: float, x1: float, width: float) -> Column:
    if x0 >= width / 2 - COLUMN_TOLERANCE:
        return "right"
    return "full" if x1 > width * FULL_WIDTH_FRACTION else "left"


def _page_lines(page: pymupdf.Page, page_no: int, header_margin: float, footer_margin: float) -> list[Line]:
    width = page.rect.width
    bottom = page.rect.height - footer_margin
    lines: list[Line] = []
    for block in page.get_text("dict")["blocks"]:
        for raw in block.get("lines", []):
            spans = [s for s in raw["spans"] if s["text"].strip()]
            if not spans:
                continue
            x0, y0, x1, _ = raw["bbox"]
            if y0 < header_margin or y0 > bottom:
                continue
            text = "".join(s["text"] for s in raw["spans"]).translate(SYMBOL_MAP)
            text = " ".join(PRIVATE_USE_RE.sub("•", text).split())
            lines.append(
                Line(
                    page=page_no,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    text=text,
                    size=round(spans[0]["size"], 1),
                    bold=all(_is_bold(s) for s in spans),
                    column=_column(x0, x1, width),
                )
            )
    return _merge_rows(lines, width)


def _merge_rows(lines: list[Line], width: float) -> list[Line]:
    """Join fragments on the same row of the same column, e.g. a section number and its title."""
    merged: list[Line] = []
    for line in sorted(lines, key=lambda ln: (ln.column != "right", ln.y0, ln.x0)):
        prev = next(
            (
                m
                for m in reversed(merged)
                if abs(m.y0 - line.y0) <= SAME_ROW_TOLERANCE and (m.column == "right") == (line.column == "right")
            ),
            None,
        )
        if prev is None:
            merged.append(line)
            continue
        if prev.x0 <= line.x0:
            prev.text = f"{prev.text} {line.text}"
        else:
            prev.text, prev.size = f"{line.text} {prev.text}", line.size  # style of the leftmost fragment
        prev.x0, prev.x1 = min(prev.x0, line.x0), max(prev.x1, line.x1)
        prev.bold = prev.bold and line.bold
        prev.column = _column(prev.x0, prev.x1, width)
    return merged


def _reading_order(lines: list[Line]) -> list[Line]:
    ordered: list[Line] = []
    band: list[Line] = []

    def flush() -> None:
        for column in ("left", "right"):
            ordered.extend(sorted((ln for ln in band if ln.column == column), key=lambda ln: ln.y0))
        band.clear()

    for line in sorted(lines, key=lambda ln: ln.y0):
        if line.column == "full":
            flush()
            ordered.append(line)
        else:
            band.append(line)
    flush()
    return ordered


def extract_lines(
    pdf_path: Path, first_page: int, last_page: int, header_margin: float, footer_margin: float
) -> list[Line]:
    with pymupdf.open(pdf_path) as doc:
        lines: list[Line] = []
        for page_no in range(first_page, last_page + 1):
            lines.extend(_reading_order(_page_lines(doc[page_no - 1], page_no, header_margin, footer_margin)))
        return lines
