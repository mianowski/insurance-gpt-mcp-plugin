"""Tariff comparison tables → one record per row, each cell tied to its tariff column.

A table starts at a header row: at least two bold cells naming tariffs (`table_headers` regex from the
manifest), or one such cell with a tariff code line directly below it. Cells are assigned geometrically:
a line belongs to the column whose header starts closest to its left. Row labels are the text left of the
first column; within a column, value lines are grouped into blocks at vertical gaps and each block goes to
the row whose label is closest to its centre (labels may be top-aligned or vertically centred). The table
ends at the next header row, at text much larger than the table text, or at a large vertical gap.
"""

import re
import statistics
from dataclasses import dataclass, field

from insurance_gpt.ingest.layout import Line, Region, reading_order

ROW_TOLERANCE = 3.0  # lines this close vertically are on the same row
COLUMN_SLACK = 12.0  # a cell may start this far left of its column header
LABEL_GAP = 8.0  # label column ends this far left of the first tariff column
CODE_RE = re.compile(r"^(DS|DV|ZE|KF)[A-Z0-9 +]*$")  # tariff code line under a header: "DS75 + DS90"


@dataclass
class Table:
    page: int
    region: int
    y0: float
    label_header: str | None  # e.g. "Tarifleistungen", "Eintrittsalter"
    columns: list[str]  # "Dental-Schutz 90 (DS75 + DS90)"
    rows: list[tuple[str, list[str]]] = field(default_factory=list)  # (label, cell text per column)
    y1: float = 0.0  # last body line
    size: float = 0.0  # font size of the table text


@dataclass
class TableInfo:
    """A table with its context: the title above it and the small-print notes next to or below it."""

    table: Table
    title: str | None
    notes: list[str]


NOTE_REACH = 25.0  # small print up to this far below a table belongs to it


def extract_part(regions: list[Region], header_re: re.Pattern):
    """Split regions into narrative lines (reading order) and tables with their titles and notes."""
    narrative: list[Line] = []
    infos: list[TableInfo] = []
    for region in regions:
        tables, rest = find_tables(region.lines, header_re, region.page, region.index)
        taken: set[int] = set()
        for table in tables:
            # Title: the nearest larger text above the table, including its wrapped lines.
            above = sorted(
                (ln for ln in rest if ln.y0 < table.y0 and table.y0 - ln.y0 < 150 and ln.size > table.size + 0.5),
                key=lambda ln: ln.y0,
            )
            title_lines = above[-1:]
            for ln in reversed(above[:-1]):
                if abs(ln.size - title_lines[0].size) < 0.5 and title_lines[0].y0 - ln.y0 <= ln.size * 1.6:
                    title_lines.insert(0, ln)
            title = " ".join(ln.text for ln in title_lines) or None
            notes = [ln for ln in rest if ln.size < table.size - 0.5 and table.y0 <= ln.y0 <= table.y1 + NOTE_REACH]
            taken |= {id(ln) for ln in notes}
            unique_notes = list({ln.text: ln for ln in sorted(notes, key=lambda ln: ln.y0)}.values())
            note_text = _join(unique_notes)
            infos.append(TableInfo(table, title, [note_text] if note_text else []))
        remaining = [ln for ln in rest if id(ln) not in taken]
        narrative.extend(reading_order(remaining, region.width))
    return narrative, infos


def _rows(lines: list[Line]) -> list[list[Line]]:
    rows: list[list[Line]] = []
    for line in sorted(lines, key=lambda ln: (ln.y0, ln.x0)):
        if rows and abs(rows[-1][0].y0 - line.y0) <= ROW_TOLERANCE:
            rows[-1].append(line)
        else:
            rows.append([line])
    return rows


def _join(lines: list[Line]) -> str:
    from insurance_gpt.ingest.chunk import join_lines  # local import: chunk imports this module

    ordered = sorted(lines, key=lambda ln: (round(ln.y0 / ROW_TOLERANCE), ln.x0))
    # Fragments on the same row ("•" + "75 %") are one line of text.
    merged: list[Line] = []
    for line in ordered:
        if merged and abs(merged[-1].y0 - line.y0) <= ROW_TOLERANCE:
            prev = merged[-1]
            merged[-1] = Line(
                prev.page, prev.x0, prev.y0, line.x1, f"{prev.text} {line.text}", prev.size, prev.bold, prev.column
            )
        else:
            merged.append(line)
    text, _ = join_lines(merged)
    return text.replace("• ", "").strip() if text.count("•") == 1 else text.strip()


def _is_code_row(row: list[Line]) -> bool:
    return all(CODE_RE.match(ln.text) for ln in row)


def _header_candidates(rows: list[list[Line]], header_re: re.Pattern) -> list[tuple[int, list[Line]]]:
    found = []
    for i, row in enumerate(rows):
        if found and found[-1][0] == i - 1 and _is_code_row(row):
            continue  # the code line under a header row, not a header of its own
        cells = [ln for ln in row if ln.bold and header_re.match(ln.text)]
        if len(cells) >= 2:
            found.append((i, cells))
        elif len(cells) == 1 and i + 1 < len(rows):
            below = [ln for ln in rows[i + 1] if CODE_RE.match(ln.text) and abs(ln.x0 - cells[0].x0) < COLUMN_SLACK]
            if below and rows[i + 1][0].y0 - cells[0].y0 < 2 * cells[0].size:
                found.append((i, cells))
    return found


def _blocks(lines: list[Line], pitch: float) -> list[list[Line]]:
    """Group lines into vertically contiguous blocks; a gap > 1.35 line pitch starts a new block."""
    blocks: list[list[Line]] = []
    for line in sorted(lines, key=lambda ln: ln.y0):
        if blocks and line.y0 - blocks[-1][-1].y0 <= pitch * 1.35:
            blocks[-1].append(line)
        else:
            blocks.append([line])
    return blocks


def _line_pitch(labels: list[Line], values: list[Line], col_x: list[float], size: float) -> float:
    """Spacing between wrapped lines of one cell: the smallest gap that occurs at least twice within a column.

    Not the median: in tables of one-line cells most gaps are row gaps, which must stay larger than the pitch.
    """
    columns = [labels] + [[ln for ln in values if _column_of(ln, col_x) == c] for c in range(len(col_x))]
    gaps = []
    for column in columns:
        ys = sorted({round(ln.y0, 1) for ln in column})
        gaps += [round(b - a, 0) for a, b in zip(ys, ys[1:], strict=False) if b - a > ROW_TOLERANCE]
    repeated = sorted(g for g in set(gaps) if gaps.count(g) >= 2)
    pitch = repeated[0] if repeated else (statistics.median(gaps) if gaps else size * 1.4)
    return min(max(pitch, size * 1.1), size * 2)


def _split_aligned(label_rows: list[list[Line]], values: list[Line]) -> list[list[Line]]:
    """Split label blocks where each line is its own row: the line has a value on the same baseline and the
    previous line's aligned value is a finished statement ("Nein.", "100 %."). Rows spaced as tightly as wrapped
    text are otherwise indistinguishable from multi-line labels."""

    def aligned(label: Line) -> Line | None:
        return next((v for v in values if abs(v.y0 - label.y0) <= 1.0), None)

    result: list[list[Line]] = []
    for block in label_rows:
        current = [block[0]]
        for prev, line in zip(block, block[1:], strict=False):
            prev_value, value = aligned(prev), aligned(line)
            if prev_value and value and prev_value.text.rstrip().endswith("."):
                result.append(current)
                current = [line]
            else:
                current.append(line)
        result.append(current)
    return result


def _split_sentences(block: list[Line]) -> list[list[Line]]:
    """Split a block of cell lines after lines ending a sentence when the next line starts a new one."""
    parts = [[block[0]]]
    for prev, line in zip(block, block[1:], strict=False):
        if prev.text.rstrip().endswith(".") and (line.text[:1].isupper() or line.text[:1].isdigit()):
            parts.append([line])
        else:
            parts[-1].append(line)
    return parts


def _nearest(centres: list[float], y: float) -> int:
    return min(range(len(centres)), key=lambda k: abs(centres[k] - y))


def _centre(lines: list[Line]) -> float:
    return (lines[0].y0 + lines[-1].y0) / 2


def _column_of(line: Line, col_x: list[float]) -> int:
    return max((i for i, x in enumerate(col_x) if line.x0 >= x - COLUMN_SLACK), default=0)


def _columns_covered(line: Line, col_x: list[float]) -> range:
    """Columns a cell line belongs to: its own, plus every further column it reaches into (merged cells such
    as "Keine Wartezeiten." printed once across all tariffs)."""
    first = _column_of(line, col_x)
    last = max((i for i, x in enumerate(col_x) if line.x1 > x + COLUMN_SLACK), default=first)
    return range(first, max(first, last) + 1)


def find_tables(lines: list[Line], header_re: re.Pattern, page: int, region: int) -> tuple[list[Table], list[Line]]:
    """Return the tables in a region and the lines that are not part of any table."""
    rows = _rows(lines)
    headers = _header_candidates(rows, header_re)
    used: set[int] = set()
    tables: list[Table] = []
    for h, (row_i, cells) in enumerate(headers):
        cells = sorted(cells, key=lambda ln: ln.x0)
        col_x = [c.x0 for c in cells]
        size = cells[0].size
        names = [c.text for c in cells]
        header_ids = {id(c) for c in rows[row_i]}
        label_header = " ".join(ln.text for ln in rows[row_i] if ln.x1 < col_x[0] - LABEL_GAP / 2) or None
        start = row_i + 1
        # Tariff codes under the names: "Dental-Schutz 90" + "DS75 + DS90".
        if start < len(rows) and _is_code_row(rows[start]):
            for code in rows[start]:
                i = min(range(len(col_x)), key=lambda k: abs(col_x[k] - code.x0))
                names[i] = f"{names[i]} ({code.text})"
                header_ids.add(id(code))
            start += 1
        next_header = headers[h + 1][0] if h + 1 < len(headers) else len(rows)

        body: list[Line] = []
        last_y = rows[row_i][0].y0
        for row in rows[start:next_header]:
            if row[0].y0 - last_y > max(30.0, 4 * size):
                break  # large gap: the table is over
            if any(ln.size > size * 1.3 for ln in row):
                break  # a title: the table is over
            body.extend(ln for ln in row if ln.size >= size - 0.6)  # smaller text = footnote, not a cell
            last_y = row[0].y0
        labels = [ln for ln in body if ln.x0 < col_x[0] - LABEL_GAP]
        if not labels or any(ln.bold and header_re.match(ln.text) for ln in labels):
            continue  # no row labels, or a tariff name where labels would be: tariff cards, not a table
        values = [ln for ln in body if ln.x0 >= col_x[0] - LABEL_GAP]

        pitch = _line_pitch(labels, values, col_x, size)
        label_rows = _split_aligned(_blocks(labels, pitch), values)
        centres = [_centre(row) for row in label_rows]
        cells_by_row: list[list[list[Line]]] = [[[] for _ in col_x] for _ in label_rows]
        for c in range(len(col_x)):
            in_col = [ln for ln in values if c in _columns_covered(ln, col_x)]
            for block in _blocks(in_col, pitch):
                rows_hit = {_nearest(centres, ln.y0) for ln in block}
                spans_rows = len(rows_hit) > 1 and any(block[0].y0 <= centres[k] <= block[-1].y0 for k in rows_hit)
                # Cells of neighbouring rows can touch: split such a block at sentence ends, then place each part.
                for part in _split_sentences(block) if spans_rows else [block]:
                    cells_by_row[_nearest(centres, _centre(part))][c].extend(part)

        table = Table(page, region, cells[0].y0, label_header, names, y1=max(ln.y0 for ln in body), size=size)
        for row, row_cells in zip(label_rows, cells_by_row, strict=True):
            texts = [_join(cell) for cell in row_cells]
            if len(texts) > 1 and texts[0] and not any(texts[1:]):
                # Text only under the first tariff is a cell merged across all tariffs ("Keine Wartezeiten.").
                # A value genuinely limited to one tariff sits in a later column (e.g. Bleaching only in Premium).
                texts = [texts[0]] * len(texts)
            table.rows.append((_join(row), texts))
        tables.append(table)
        used |= header_ids | {id(ln) for ln in body}
    rest = [ln for ln in lines if id(ln) not in used]
    return tables, rest
