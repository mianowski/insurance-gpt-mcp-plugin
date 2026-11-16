"""Quote verification and the citation card. No embedding model needed: they run in CI."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from insurance_gpt.retrieval.verify import closest_sentence, context, find_quote
from insurance_gpt.server import mcp
from insurance_gpt.tools.citation import WIDGET_URI

TEXT = (
    "Wir leisten für Zahnersatz. Das gilt z. B. für Kronen und Brücken bis zu einem Höchstbetrag von 1.000 Euro "
    "im ersten Jahr.\nKein Schutz für:\n• Implantate,\n• Bleaching."
)
IMPLANTS_ROW = "ergo-zahn-broschuere-2022-07:broschuere:t12.r2"  # "Implantate / Zahnersatz Sofort (ZEZ): Nein."


def _quoted(quote: str, text: str = TEXT) -> list[str]:
    match = find_quote(quote, text)
    return [text[start:end] for start, end in match.spans] if match else []


# --- verification ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        "Das gilt z. B. für Kronen und Brücken",
        "„das gilt z. B. für Kronen   und Brücken“",  # case, typographic quotes, whitespace
        "Kein Schutz für: Implantate",  # line break and list bullet
        "Das gilt z. B. für Kronen und Brücken bis zu einem Höchstbetrag von 1.000 Euro im ersten Jahr",
    ],
)
def test_quotes_with_cosmetic_differences_are_verified(quote):
    assert _quoted(quote)


@pytest.mark.parametrize(
    "quote",
    [
        "Das gilt z. B. für Kronen und Implantate",  # changed word
        "Das gilt für Kronen und Brücken",  # dropped words without "…"
        "Wir leisten für Implantate.",
        "Brücken … Das gilt",  # pieces in the wrong order
    ],
)
def test_changed_quotes_are_rejected(quote):
    assert not _quoted(quote)


def test_ellipsis_matches_pieces_in_order():
    assert _quoted("Das gilt … für Kronen und Brücken […] im ersten Jahr.") == [
        "Das gilt",
        "für Kronen und Brücken",
        "im ersten Jahr.",  # the sentence's full stop is part of the quote
    ]


def test_closest_sentence_helps_the_model_correct_a_quote():
    assert closest_sentence("Das gilt für Kronen und Implantate", TEXT).startswith("Das gilt z. B. für Kronen")
    assert closest_sentence("Wie wird das Wetter morgen?", TEXT) is None


def test_context_cuts_long_passages_at_sentence_boundaries():
    long = TEXT * 3
    segments = context(long, find_quote("Kronen und Brücken", long).spans, reach=40)
    assert [s.text for s in segments if s.highlight] == ["Kronen und Brücken"]
    assert segments[0].text.startswith("Das gilt z. B. für")  # whole sentence start, within reach
    assert segments[-1].text.endswith(" …")  # cut inside the sentence


def test_context_shows_short_passages_whole():
    segments = context(TEXT, find_quote("Implantate", TEXT).spans, reach=160)
    assert "".join(s.text for s in segments) == TEXT


# --- the tool and the widget --------------------------------------------------------------------------------


def _card(args: dict) -> dict:
    return asyncio.run(mcp.call_tool("show_citation", args)).structured_content


def test_card_shows_the_source_text_not_the_models_quote():
    card = _card({"chunk_id": IMPLANTS_ROW, "quote": "„zahnersatz sofort (ZEZ): nein“", "language": "en"})
    assert card["verified"] and card["quote"] == "Zahnersatz Sofort (ZEZ): Nein."
    assert card["citation"] == "Produktbroschüre Zahn-Zusatzversicherungen, „Sofortschutz – Implantate“, S. 10"
    assert card["url"].endswith("#page=10") and card["edition"] == "Beiträge Stand 01.07.2022"
    assert [s["text"] for s in card["context"]] == ["Implantate\n", "Zahnersatz Sofort (ZEZ): Nein."]
    assert not card["corrected_chunk_id"]


def test_quote_from_another_passage_is_cited_where_it_is():
    card = _card(
        {"chunk_id": "ergo-zahn-broschuere-2022-07:broschuere:t12.r1", "quote": "Zahnersatz Sofort (ZEZ): Nein."}
    )
    assert card["chunk_id"] == IMPLANTS_ROW and card["corrected_chunk_id"]


@pytest.mark.parametrize(
    ("quote", "message"),
    [
        ("Zahnersatz Sofort (ZEZ): Ja.", "not found verbatim.*Zahnersatz Sofort \\(ZEZ\\): Nein"),
        ("Nein.", "too short"),
    ],
)
def test_unverifiable_quotes_are_tool_errors_with_a_hint(quote, message):
    with pytest.raises(ToolError, match=message):
        _card({"chunk_id": IMPLANTS_ROW, "quote": quote})


def test_unknown_chunk_is_a_tool_error():
    with pytest.raises(ToolError, match="Unknown chunk_id"):
        _card({"chunk_id": "nope", "quote": "Zahnersatz Sofort (ZEZ): Nein."})


def test_show_citation_is_linked_to_the_widget():
    tools = {t.name: t.model_dump(by_alias=True, exclude_none=True) for t in asyncio.run(mcp.list_tools())}
    meta = tools["show_citation"]["_meta"]
    assert meta["ui"]["resourceUri"] == meta["openai/outputTemplate"] == WIDGET_URI
    assert all("_meta" not in tools[name] for name in ("list_documents", "search_conditions", "get_section"))
    (resource,) = [r for r in asyncio.run(mcp.list_resources()) if str(r.uri) == WIDGET_URI]
    assert resource.mime_type == "text/html;profile=mcp-app"
    (content,) = asyncio.run(mcp.read_resource(WIDGET_URI))
    html = content.content
    assert "ui/initialize" in html and "ui/notifications/tool-result" in html
    assert "innerHTML" not in html, "card data is untrusted: render text nodes only"
    assert "<script src" not in html and "<link" not in html, "the widget must be self-contained (CSP)"
