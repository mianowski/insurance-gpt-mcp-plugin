"""show_citation: verify a quote against the source passage and render it as a citation card (widget).

The card shows the server's copy of the source text, never the model's: what the user sees highlighted is
guaranteed to be in the document. A quote that isn't in the passage is a ToolError carrying the closest
source sentence, so the model can correct itself instead of the user seeing a failed card.
"""

import logging
from functools import lru_cache
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from insurance_gpt.config import get_settings
from insurance_gpt.ingest.chunk import Chunk
from insurance_gpt.retrieval.store import KnowledgeStore
from insurance_gpt.retrieval.verify import QuoteMatch, closest_sentence, context, find_quote
from insurance_gpt.tools.knowledge import TEXTS
from insurance_gpt.tuning import get_tuning

log = logging.getLogger("insurance_gpt.tools")

WIDGET_URI = "ui://widget/citation-v1.html"  # a cache key for ChatGPT: bump the version on breaking changes


@lru_cache
def get_store() -> KnowledgeStore:
    """The chunks and manifest only: verifying a quote needs no embedding model."""
    settings = get_settings()
    return KnowledgeStore(settings.sources_file, settings.chunks_dir)


class Segment(BaseModel):
    text: str
    highlight: bool


class CitationCard(BaseModel):
    verified: bool
    chunk_id: str
    citation: str
    document: str
    edition: str
    official_source: bool
    section_title: str
    pages: str
    url: str = Field(description="PDF link opening at the cited page")
    quote: str = Field(description="The verified quote, exactly as in the source (omissions shown as […])")
    context: list[Segment] = Field(description="Source text around the quote; highlight = the quoted words")
    translation: str | None
    language: Literal["de", "en"]
    corrected_chunk_id: bool = Field(description="True if the quote was found in another passage than requested")


def _locate(chunk: Chunk, quote: str) -> tuple[Chunk, QuoteMatch | None, bool]:
    """The quote's match in the requested passage, else in another one (same document first)."""
    match = find_quote(quote, chunk.text)
    if match:
        return chunk, match, False
    others = sorted(get_store().chunks, key=lambda c: c.doc_id != chunk.doc_id)
    for other in others:
        if other is not chunk and (match := find_quote(quote, other.text)):
            return other, match, True
    return chunk, None, False


def show_citation(
    chunk_id: Annotated[str, Field(description="chunk_id of the passage the quote comes from")],
    quote: Annotated[str, Field(description=TEXTS.tools.show_citation_quote)],
    translation: Annotated[
        str | None, Field(description="Your translation of the quote if the user's question is not in German.")
    ] = None,
    language: Annotated[
        Literal["de", "en"], Field(description="Language of the user's question (labels on the card).")
    ] = "de",
) -> CitationCard:
    store = get_store()
    if chunk_id not in store.by_id:
        raise ToolError(f"Unknown chunk_id '{chunk_id}'. Use a chunk_id returned by search_conditions.")
    settings = get_tuning().citation
    chunk, match, corrected = _locate(store.by_id[chunk_id], quote)
    if match is None:
        closest = closest_sentence(quote, chunk.text)
        log.info("show_citation chunk_id=%s quote=%r -> not found (closest %r)", chunk_id, quote, closest)
        if closest:
            hint = f"The closest source text is: «{closest}». "
        else:
            text = chunk.text if len(chunk.text) <= 800 else chunk.text[:800] + " …"
            hint = f"The passage text is: «{text}». "
        raise ToolError(
            f"The quote was not found verbatim in passage '{chunk_id}'. {hint}Quote the passage text exactly "
            "(German, unchanged; use … for omissions) and call show_citation again."
        )
    if match.length < settings.min_quote_chars:
        raise ToolError("The quote is too short to prove the answer. Quote the whole decisive sentence.")
    log.info("show_citation chunk_id=%s quote=%r -> verified in %s", chunk_id, quote, chunk.chunk_id)
    doc = store.documents[chunk.doc_id]
    return CitationCard(
        verified=True,
        chunk_id=chunk.chunk_id,
        citation=store.citation(chunk),
        document=doc.title,
        edition=doc.edition,
        official_source=doc.official_source,
        section_title=chunk.section_title,
        pages=store.pages(chunk),
        url=store.url(chunk),
        quote=" […] ".join(chunk.text[start:end] for start, end in match.spans),
        context=[
            Segment(text=s.text, highlight=s.highlight)
            for s in context(chunk.text, match.spans, settings.context_chars)
        ],
        translation=translation,
        language=language,
        corrected_chunk_id=corrected,
    )
