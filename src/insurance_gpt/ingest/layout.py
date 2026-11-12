"""PDF page → text lines in reading order, with the style info needed to find headings.

The ERGO documents use a two-column layout with occasional full-width rows (titles, intro text).
Reading order: within each horizontal band between full-width rows, the left column top-to-bottom,
then the right column. Brochures printed as two-page spreads are split into a left and a right region first.

Two steps: `extract_regions` gives the raw lines of each region (needed for table detection, where cells on
the same row must stay apart), `reading_order` merges same-row fragments and orders the rest.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pymupdf

BOLD_FONT_MARKERS = ("Bold", "Heavy", "Black")
# Private-use glyphs from symbol fonts used as list markers.
SYMBOL_MAP = str.maketrans({"": "•", "": "–", "": "•"})
# Any other private-use glyph is a list marker too (checkmarks, arrows).
PRIVATE_USE_RE = re.compile("[-]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SOFT_HYPHEN = "\u00ad"
LIGATURE_GAP_RE = re.compile(r"(?<=\w)(fi|fl|ff) (?=[a-zäöüß])")
SAME_ROW_TOLERANCE = 4.0
COLUMN_TOLERANCE = 10.0
# A line starting in the left half that reaches past this share of the page width spans both columns.
FULL_WIDTH_FRACTION = 0.7

Column = Literal["left", "right", "full"]


@dataclass
class Region:
    """A page, or one half of a two-page spread. Line x coordinates are relative to the region."""

    page: int
    index: int  # 0 = left half / whole page, 1 = right half
    width: float
    lines: list["Line"]


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
    block: int = -1  # PDF text block within the region; lines of one block belong together


def _clean_hyphens(text: str) -> str:
    """Soft hyphens: dropped inside a word, a real hyphen at line end (so it can be dehyphenated)."""
    text = CONTROL_RE.sub("", text).rstrip()
    if text.endswith(SOFT_HYPHEN):
        text = text[:-1] + "-"
    return text.replace(SOFT_HYPHEN, "")


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or any(m in span["font"] for m in BOLD_FONT_MARKERS)


def _column(x0: float, x1: float, width: float) -> Column:
    if x0 >= width / 2 - COLUMN_TOLERANCE:
        return "right"
    return "full" if x1 > width * FULL_WIDTH_FRACTION else "left"


def _region_lines(
    page: pymupdf.Page, page_no: int, clip: pymupdf.Rect, header_margin: float, footer_margin: float
) -> list[Line]:
    width = clip.width
    bottom = page.rect.height - footer_margin
    lines: list[Line] = []
    for block_no, block in enumerate(page.get_text("dict", clip=clip)["blocks"]):
        for raw in block.get("lines", []):
            spans = [s for s in raw["spans"] if s["text"].strip()]
            if not spans:
                continue
            x0, y0, x1, _ = raw["bbox"]
            x0, x1 = x0 - clip.x0, x1 - clip.x0
            if y0 < header_margin or y0 > bottom:
                continue
            text = "".join(s["text"] for s in raw["spans"]).translate(SYMBOL_MAP)
            # Soft hyphens: invisible inside a word, a real hyphen at the end of a line.
            text = _clean_hyphens(text)
            text = " ".join(PRIVATE_USE_RE.sub("•", text).split())
            # Ligatures (ﬁ, ﬂ) to plain letters; some PDFs also put a space after them ("Tariﬂ eistungen").
            text = LIGATURE_GAP_RE.sub(r"\1", unicodedata.normalize("NFKC", text))
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
                    block=block_no,
                )
            )
    return lines


def _merge_rows(lines: list[Line], width: float) -> list[Line]:
    """Join fragments on the same row of the same column, e.g. a section number and its title."""
    merged: list[Line] = []
    for line in sorted(lines, key=lambda ln: (ln.column != "right", ln.y0, ln.x0)):
        prev = next(
            (
                m
                for m in reversed(merged)
                if abs(m.y0 - line.y0) <= SAME_ROW_TOLERANCE
                and (m.column == "right") == (line.column == "right")
                and m.block == line.block
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


STACK_X_TOLERANCE = 6.0
STACK_GAP = 25.0


def _stack_order(lines: list[Line], width: float) -> list[Line]:
    """Keep stacked text blocks together (e.g. a tariff card: name, core benefits, specials), then order the
    stacks like lines: bands between full-width stacks, left column before right column."""
    blocks: dict[int, list[Line]] = {}
    for line in lines:
        blocks.setdefault(line.block, []).append(line)
    stacks: list[list[list[Line]]] = []
    for block in sorted(blocks.values(), key=lambda b: min(ln.y0 for ln in b)):
        block.sort(key=lambda ln: (ln.y0, ln.x0))
        x0, y0 = min(ln.x0 for ln in block), block[0].y0
        target = next(
            (
                st
                for st in stacks
                if abs(min(ln.x0 for ln in st[-1]) - x0) <= STACK_X_TOLERANCE
                and 0 <= y0 - st[-1][-1].y0 <= STACK_GAP + st[-1][-1].size * 1.5
            ),
            None,
        )
        if target is None:
            stacks.append([block])
        else:
            target.append(block)
    # Represent each stack by a synthetic first line for the column/band ordering.
    heads = []
    for st in stacks:
        st_lines = [ln for b in st for ln in b]
        head = st_lines[0]
        x0, x1 = min(ln.x0 for ln in st_lines), max(ln.x1 for ln in st_lines)
        heads.append((Line(head.page, x0, head.y0, x1, "", head.size, False, _column(x0, x1, width)), st_lines))
    order = _reading_order([h for h, _ in heads])
    by_head = {id(h): st_lines for h, st_lines in heads}
    return [ln for h in order for ln in by_head[id(h)]]


def reading_order(lines: list[Line], width: float) -> list[Line]:
    return _stack_order(_merge_rows(lines, width), width)


def extract_regions(
    pdf_path: Path,
    first_page: int,
    last_page: int,
    header_margin: float,
    footer_margin: float,
    split_spreads: bool = False,
) -> list[Region]:
    regions: list[Region] = []
    with pymupdf.open(pdf_path) as doc:
        for page_no in range(first_page, last_page + 1):
            page = doc[page_no - 1]
            rect = page.rect
            if split_spreads and rect.width > rect.height:
                mid = rect.x0 + rect.width / 2
                clips = [pymupdf.Rect(rect.x0, rect.y0, mid, rect.y1), pymupdf.Rect(mid, rect.y0, rect.x1, rect.y1)]
            else:
                clips = [rect]
            for index, clip in enumerate(clips):
                lines = _region_lines(page, page_no, clip, header_margin, footer_margin)
                regions.append(Region(page_no, index, clip.width, lines))
    return regions


def extract_lines(
    pdf_path: Path,
    first_page: int,
    last_page: int,
    header_margin: float,
    footer_margin: float,
    split_spreads: bool = False,
) -> list[Line]:
    regions = extract_regions(pdf_path, first_page, last_page, header_margin, footer_margin, split_spreads)
    return [line for region in regions for line in reading_order(region.lines, region.width)]
