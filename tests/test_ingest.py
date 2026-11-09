import pytest

pytest.importorskip("pymupdf", reason="ingestion needs the rag extra: uv sync --extra rag")

from insurance_gpt.config import get_settings  # noqa: E402
from insurance_gpt.ingest.__main__ import build_document, chunks_path, read_chunks  # noqa: E402
from insurance_gpt.ingest.chunk import _split, join_lines  # noqa: E402
from insurance_gpt.ingest.fetch import HashMismatchError, ensure_pdf  # noqa: E402
from insurance_gpt.ingest.layout import Line  # noqa: E402
from insurance_gpt.sources import load_manifest  # noqa: E402


def _line(text: str, page: int = 1) -> Line:
    return Line(page=page, x0=0, y0=0, x1=0, text=text, size=9, bold=False, column="left")


def _docs():
    return {d.doc_id: d for d in load_manifest(get_settings().sources_file).documents}


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


def test_hash_mismatch_is_rejected(tmp_path):
    doc = _docs()["ergo-ds100-brochure-2026-02"]
    (tmp_path / f"{doc.doc_id}.pdf").write_bytes(b"not the brochure")
    with pytest.raises(HashMismatchError):
        ensure_pdf(doc, tmp_path)


@pytest.fixture(scope="module")
def zek():
    return {c.chunk_id: c for c in build_document(_docs()["ergo-zek-2025-04"], get_settings().knowledge_dir)}


def test_zek_implant_exclusion_is_cited_from_clause_1_2(zek):
    chunk = zek["ergo-zek-2025-04:avb:1.2"]
    assert chunk.page_start == chunk.page_end == 6
    assert chunk.text.startswith("Kein Versicherungsschutz besteht für:")
    assert "• Implantate (insbesondere Einbringung" in chunk.text


def test_zek_table_of_contents_does_not_leak_into_clauses(zek):
    clause_text = " ".join(c.text for c in zek.values() if c.part_id == "avb")
    assert "Was gilt für Mitteilungen" not in clause_text  # a TOC entry; it's section 6's title


def test_zek_headings_are_complete(zek):
    assert zek["ergo-zek-2025-04:avb:5.1"].section_title == (
        "Wann kann der Vertrag gekündigt werden bzw. wann endet der Vertrag?"
    )
    assert zek["ergo-zek-2025-04:avb:6.1"].chapter == "Weitere Regelungen"
    assert zek["ergo-zek-2025-04:ipid:h04"].section_title == "Was ist nicht versichert?"


def test_committed_chunks_match_a_fresh_build():
    settings = get_settings()
    for doc in _docs().values():
        committed = read_chunks(chunks_path(settings.knowledge_dir, doc.doc_id))
        assert committed == build_document(doc, settings.knowledge_dir), (
            f"knowledge/chunks/{doc.doc_id}.jsonl is stale: run `python -m insurance_gpt.ingest build`"
        )
