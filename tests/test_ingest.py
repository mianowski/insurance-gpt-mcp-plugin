import re

import pytest

from insurance_gpt.config import get_settings
from insurance_gpt.ingest.__main__ import build_document, chunks_path, read_chunks
from insurance_gpt.ingest.chunk import _numbered_units, _split, join_lines
from insurance_gpt.ingest.fetch import HashMismatchError, ensure_pdf
from insurance_gpt.ingest.layout import Line
from insurance_gpt.ingest.tables import find_tables
from insurance_gpt.sources import load_manifest

OVERVIEW = "ergo-zahntarife-uebersicht-2024-08"
BROCHURE = "ergo-zahn-broschuere-2022-07"
HEADERS = re.compile(r"^(Dental-(Schutz|Vorsorge)|Zahnersatz Sofort|DS[0-9])")


def _line(text: str, page: int = 1, x0: float = 0, y0: float = 0, bold: bool = False, size: float = 9) -> Line:
    return Line(page=page, x0=x0, y0=y0, x1=x0 + 6 * len(text), text=text, size=size, bold=bold, column="left")


def _docs():
    return {d.doc_id: d for d in load_manifest(get_settings().sources_file).documents}


# --- text joining and splitting -------------------------------------------------------------------------


def test_join_lines_dehyphenates_but_keeps_real_hyphens():
    text, _ = join_lines([_line("Zahnersatz-"), _line("versorgung des Ober-"), _line("und Unterkiefers")])
    assert text == "Zahnersatzversorgung des Ober- und Unterkiefers"


def test_join_lines_keeps_list_items_on_own_lines_and_tracks_pages():
    text, offsets = join_lines([_line("Kein Schutz für:"), _line("• Implantate,", page=2)])
    assert text == "Kein Schutz für:\n• Implantate,"
    assert offsets == [(0, 1), (17, 2)]


def test_split_never_cuts_after_abbreviations():
    sentence = "Das gilt z. B. für Kronen bzw. Brücken (z. B. Keramik). "
    text = sentence * 40
    spans = _split(text)
    assert len(spans) > 1
    assert spans[0][0] == 0 and spans[-1][1] == len(text)
    for start, end in spans:
        assert text[start:end].strip().endswith("Keramik).")


def test_numbered_terms_skip_toc_and_split_clauses():
    lines = [
        _line("1 Welche Leistungen erbringen wir?"),  # table of contents entry (not bold)
        _line("1 Welche Leistungen erbringen wir?", bold=True),
        _line("1.1 Wir leisten für Zahnersatz."),
        _line("1.2 Kein Versicherungsschutz besteht für:"),
        _line("• Implantate"),
    ]
    units = [u for u in _numbered_units(lines) if u.lines]
    assert [(u.section, u.clause) for u in units] == [("1", "1.1"), ("1", "1.2")]
    assert units[0].section_title == "Welche Leistungen erbringen wir?"


def test_hash_mismatch_is_rejected(tmp_path):
    doc = _docs()[BROCHURE]
    (tmp_path / f"{doc.doc_id}.pdf").write_bytes(b"not the brochure")
    with pytest.raises(HashMismatchError):
        ensure_pdf(doc, tmp_path)


# --- tariff tables (synthetic geometry) ------------------------------------------------------------------


def _table(rows: list[tuple[float, str, list[str]]], labels_centred: bool = False) -> list[Line]:
    """Header "Dental-Schutz 75 | Dental-Schutz 90" at x=200/350, codes below, rows of label + cells."""
    lines = [
        _line("Tarifleistungen", x0=50, y0=100, bold=True),
        _line("Dental-Schutz 75", x0=200, y0=100, bold=True),
        _line("Dental-Schutz 90", x0=350, y0=100, bold=True),
        _line("DS75", x0=200, y0=112),
        _line("DS75 + DS90", x0=350, y0=112),
    ]
    for y, label, cells in rows:
        cell_lines = [c.split("|") for c in cells]
        height = max(len(c) for c in cell_lines) * 12
        lines.append(_line(label, x0=50, y0=y + (height - 12) / 2 if labels_centred else y))
        for x, parts in zip((200, 350), cell_lines, strict=True):
            lines += [_line(part, x0=x, y0=y + 12 * i) for i, part in enumerate(parts) if part]
    return lines


def test_table_rows_keep_cells_with_their_tariff():
    lines = _table([(130, "Implantate", ["75 %", "90 %"]), (160, "Wartezeiten", ["Keine Wartezeiten.", ""])])
    tables, rest = find_tables(lines, HEADERS, page=1, region=0)
    assert rest == []
    (table,) = tables
    assert table.label_header == "Tarifleistungen"
    assert table.columns == ["Dental-Schutz 75 (DS75)", "Dental-Schutz 90 (DS75 + DS90)"]
    assert table.rows[0] == ("Implantate", ["75 %", "90 %"])
    # Text only under the first tariff is a merged cell for all tariffs.
    assert table.rows[1] == ("Wartezeiten", ["Keine Wartezeiten.", "Keine Wartezeiten."])


def test_table_multiline_cells_with_centred_labels():
    lines = _table(
        [(130, "Zahnersatz", ["75 % für|Kronen und|Brücken", "90 % für|Kronen"]), (180, "Inlays", ["Ja.", "Ja."])],
        labels_centred=True,
    )
    (table,) = find_tables(lines, HEADERS, page=1, region=0)[0]
    assert table.rows == [
        ("Zahnersatz", ["75 % für Kronen und Brücken", "90 % für Kronen"]),
        ("Inlays", ["Ja.", "Ja."]),
    ]


def test_tariff_cards_side_by_side_are_not_a_table():
    lines = [
        _line("Dental-Schutz 75", x0=50, y0=100, bold=True),
        _line("DS75", x0=50, y0=112),
        _line("Dental-Schutz 90", x0=250, y0=90, bold=True),
        _line("DS75 + DS90", x0=250, y0=102),
        _line("Kernleistung:", x0=250, y0=120, bold=True),
    ]
    tables, rest = find_tables(lines, HEADERS, page=1, region=0)
    assert tables == [] and len(rest) == len(lines)


# --- the real source documents ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def chunks():
    knowledge = get_settings().knowledge_dir
    return {c.chunk_id: c for doc in _docs().values() for c in build_document(doc, knowledge)}


def _row(chunks, doc_id: str, section_title: str, contains: str):
    found = [
        c for c in chunks.values() if c.doc_id == doc_id and c.section_title == section_title and contains in c.text
    ]
    assert found, f"no chunk '{section_title}' containing '{contains}' in {doc_id}"
    return found[0]


def test_overview_implant_row_names_every_tariff(chunks):
    row = _row(chunks, OVERVIEW, "Tarifleistungen: Implantate", "Wie Zahnersatz")
    assert row.page_start == 3
    assert row.chapter == "Zahnersatz mit unseren Dental-Schutz Tarifen"
    for tariff in ("Dental-Schutz 75 (DS75)", "Dental-Schutz 90 (DS75 + DS90)", "Dental-Schutz 100"):
        assert f"{tariff}" in row.text
    assert "Stand 08/2024" in row.text  # the table's footnote travels with every row


def test_brochure_tables(chunks):
    assert "Zahnersatz Sofort (ZEZ): Nein." in _row(chunks, BROCHURE, "Implantate", "Zahnersatz Sofort").text
    premiums = _row(chunks, BROCHURE, "Eintrittsalter: 21 – 25", "DS75")
    assert "DS75: 5,00 €" in premiums.text and "Monatliche Beiträge" in premiums.text
    waiting = _row(chunks, BROCHURE, "Wartezeiten", "Dental-Schutz 100")
    assert "Dental-Schutz 100 (DS75 + DS90 + DS100): Keine Wartezeiten." in waiting.text


def test_tariff_cards_are_coherent_sections(chunks):
    card = _row(chunks, OVERVIEW, "Dental-Schutz 90", "Kernleistung")
    assert "90 % inkl. GKV." in card.text
    assert "75 % inkl. GKV." not in card.text  # the neighbouring DS75 card must not bleed in


def test_committed_chunks_match_a_fresh_build(chunks):
    settings = get_settings()
    for doc in _docs().values():
        committed = read_chunks(chunks_path(settings.knowledge_dir, doc.doc_id))
        assert committed == [c for c in chunks.values() if c.doc_id == doc.doc_id], (
            f"knowledge/chunks/{doc.doc_id}.jsonl is stale: run `python -m insurance_gpt.ingest build`"
        )
