"""Reading-ordered lines → section-aware chunks.

`numbered` parts (terms, customer information): a bold line "<n> <title>" opens section n, a line starting
with "<n>.<m>" opens clause n.m inside it. Text before the first clause becomes the section's own chunk.
Bold lines without a number between sections are chapter titles ("Beitrag und Vertragslaufzeit").

`headings` parts (information sheet, brochure): a bold line with font size >= heading_min_size opens a
section; consecutive heading lines are one heading.
"""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from insurance_gpt.ingest.layout import Line
from insurance_gpt.sources import DocumentPart, SourceDocument

SECTION_RE = re.compile(r"^(\d{1,2})\s+(\S.*)$")
CLAUSE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})(?![\d,])\s*(.*)$")
# Words after a line-break hyphen that mean the hyphen is real ("Ober- und Unterkiefer").
KEEP_HYPHEN_BEFORE = {"und", "oder", "bzw.", "sowie", "bis"}
MAX_CHUNK_CHARS = 1400
TARGET_CHUNK_CHARS = 900
SENTENCE_END_RE = re.compile(r"[.;:!?]\s+(?=[A-ZÄÖÜ•–(!X])")
ABBREVIATIONS = {"bzw.", "z.", "B.", "ggf.", "u.", "a.", "d.", "h.", "Nr.", "Abs.", "ca.", "usw.", "vgl."}
# Text before the first heading shorter than this is just the document title.
MIN_PREAMBLE_CHARS = 120


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    part_id: str
    part_title: str
    chapter: str | None
    section: str | None  # "1" for numbered parts, None for heading-structured parts
    section_title: str
    clause: str | None  # "1.2"
    page_start: int
    page_end: int
    text: str


@dataclass
class _Unit:
    chapter: str | None
    section: str | None
    section_title: str
    clause: str | None
    lines: list[Line] = field(default_factory=list)


LIST_MARKERS = ("•", "–", "X ", "! ")


def join_lines(lines: list[Line]) -> tuple[str, list[tuple[int, int]]]:
    """Join PDF lines into running text, undoing line-break hyphenation and keeping list items apart.

    Returns the text and (offset, page) for each line, so any span of the text can be mapped to pages.
    """
    out = ""
    offsets: list[tuple[int, int]] = []
    for line in lines:
        text = line.text
        if not out:
            pass
        elif text.startswith(LIST_MARKERS) or out.endswith(":"):
            out += "\n"
        elif out.endswith("-") and text[:1].islower() and text.split()[0] not in KEEP_HYPHEN_BEFORE:
            out = out[:-1]
        else:
            out += " "
        offsets.append((len(out), line.page))
        out += text
    return out, offsets


def _title_complete(title: str) -> bool:
    # Not ".": titles contain abbreviations ("bzw.", "z. B.").
    return title.rstrip().endswith(("?", ":"))


def _can_be_chapter(line: Line) -> bool:
    """Chapter titles are plain word labels, not list items, (bold) sentences or dated references."""
    return (
        not line.text.startswith(("-", "–", "•"))
        and not line.text.endswith((".", ",", ";", ":"))
        and not any(ch.isdigit() for ch in line.text)
    )


def _classify_numbered(lines: list[Line]) -> list[str]:
    """Label each line: heading, heading_cont, toc, chapter or body.

    - heading: bold "<n> <title>"; following bold lines continue it until the title ends ("?", ":").
    - toc: table-of-contents entry, i.e. a non-bold "<n> <title>" plus its wrapped lines up to the "?".
    - chapter: bold unnumbered label lines directly before a heading; the same before a toc entry are toc.
    - body: everything else, including bold paragraphs inside a clause.
    """
    kinds = ["body"] * len(lines)
    i = 0
    while i < len(lines):
        line = lines[i]
        if SECTION_RE.match(line.text) and line.bold:
            kinds[i] = "heading"
            title, j = line.text, i + 1
            while j < len(lines) and j - i <= 3 and lines[j].bold and not _title_complete(title):
                kinds[j] = "heading_cont"
                title += f" {lines[j].text}"
                j += 1
            i = j
        elif SECTION_RE.match(line.text):
            kinds[i], j = "toc", i + 1
            while not _title_complete(lines[j - 1].text) and j < len(lines) and j - i <= 3:
                kinds[j] = "toc"
                j += 1
            i = j
        else:
            i += 1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].bold and kinds[i] == "body":
            following = kinds[i + 1] if i + 1 < len(lines) else "body"
            if following in ("heading", "chapter") and _can_be_chapter(lines[i]):
                kinds[i] = "chapter"
            elif following == "toc":
                kinds[i] = "toc"
    return kinds


def _numbered_units(lines: list[Line]) -> list[_Unit]:
    units = [_Unit(chapter=None, section=None, section_title="Einleitung", clause=None)]
    chapter: list[str] = []
    current_chapter: str | None = None
    for line, kind in zip(lines, _classify_numbered(lines), strict=True):
        current = units[-1]
        clause = CLAUSE_RE.match(line.text)
        if kind == "toc":
            continue
        if kind == "chapter":
            chapter.append(line.text)
        elif kind == "heading":
            current_chapter = " ".join(chapter) if chapter else current_chapter
            chapter = []
            section = SECTION_RE.match(line.text)
            units.append(_Unit(current_chapter, section[1], section[2], None))
        elif kind == "heading_cont":
            current.section_title += f" {line.text}"
        elif clause and current.section == clause[1]:
            units.append(
                _Unit(current_chapter, current.section, current.section_title, f"{clause[1]}.{clause[2]}")
            )
            if clause[3]:
                units[-1].lines.append(_with_text(line, clause[3]))
        else:
            current.lines.append(line)
    return units


def _heading_units(lines: list[Line], min_size: float) -> list[_Unit]:
    units = [_Unit(chapter=None, section=None, section_title="Einleitung", clause=None)]
    prev_heading = False
    for line in lines:
        is_heading = line.bold and line.size >= min_size
        if is_heading and prev_heading:
            units[-1].section_title += f" {line.text}"
        elif is_heading:
            units.append(_Unit(chapter=None, section=None, section_title=line.text, clause=None))
        else:
            units[-1].lines.append(line)
        prev_heading = is_heading
    return units


def _with_text(line: Line, text: str) -> Line:
    return Line(line.page, line.x0, line.y0, line.x1, text, line.size, line.bold, line.column)


def _split(text: str) -> list[tuple[int, int]]:
    """(start, end) spans cutting an oversized text at sentence ends into pieces of ~TARGET_CHUNK_CHARS."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [(0, len(text))]
    cuts = [
        m.end()
        for m in SENTENCE_END_RE.finditer(text)
        if text[: m.start() + 1].split()[-1].lstrip('("„') not in ABBREVIATIONS
    ]
    spans, start = [], 0
    for prev, cut in zip([0, *cuts], [*cuts, len(text)], strict=True):
        if cut - start > TARGET_CHUNK_CHARS and prev > start:
            spans.append((start, prev))
            start = prev
    spans.append((start, len(text)))
    return spans


def _page_at(offsets: list[tuple[int, int]], pos: int) -> int:
    return [page for offset, page in offsets if offset <= pos][-1]


def chunk_part(doc: SourceDocument, part: DocumentPart, lines: list[Line]) -> list[Chunk]:
    units = (
        _numbered_units(lines)
        if part.structure == "numbered"
        else _heading_units(lines, part.heading_min_size)
    )
    chunks: list[Chunk] = []
    heading_no = 0
    for unit in units:
        if not unit.lines:
            continue
        text, offsets = join_lines(unit.lines)
        if unit is units[0] and len(text) < MIN_PREAMBLE_CHARS:
            continue
        if unit.section is None:
            heading_no += 1
        key = unit.clause or unit.section or f"h{heading_no:02d}"
        pieces = _split(text)
        for i, (start, end) in enumerate(pieces, start=1):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}:{part.part_id}:{key}" + (f"#{i}" if len(pieces) > 1 else ""),
                    doc_id=doc.doc_id,
                    part_id=part.part_id,
                    part_title=part.title,
                    chapter=unit.chapter,
                    section=unit.section,
                    section_title=" ".join(unit.section_title.split()),
                    clause=unit.clause,
                    page_start=_page_at(offsets, start),
                    page_end=_page_at(offsets, end - 1),
                    text=text[start:end].strip(),
                )
            )
    return chunks
