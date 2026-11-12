"""Knowledge tools: list_documents, search_conditions, get_section.

They return source passages with citation metadata; ChatGPT writes the answer from them.
"""

import logging
from functools import lru_cache
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from insurance_gpt.config import get_settings
from insurance_gpt.ingest.chunk import Chunk
from insurance_gpt.retrieval.search import Retriever

log = logging.getLogger("insurance_gpt.tools")

DISCLAIMER = "Informational only; the insurance contract and its full conditions are decisive."

# Conversation rules (WBS 4.1). Shared by the server instructions, tool descriptions and every search result,
# because ChatGPT may also have web search and general knowledge available and tends to mix them in.
ANSWER_RULES = (
    "Rules: (0) Answer in the language the user's question is written in (German question -> German answer), "
    "regardless of interface or account language. "
    "(1) Answer only from passages returned by search_conditions or get_section. "
    "(2) Do not add ERGO products, tariffs, prices, limits or rules from web search or general knowledge, "
    "not even as a suggestion; if the passages don't answer something, say that the available documents "
    "don't cover it. "
    "(3) Cite the passage whose text actually states the rule (its `citation`: part, Ziffer, page), and quote "
    "the decisive sentence verbatim in German, followed by a translation if the question is not in German. "
    "(4) Questions about other insurance types, other insurers, or the user's own contract, claim or policy "
    "number are out of scope: say so briefly, point to ERGO customer service or an adviser, and do not answer "
    "them from general knowledge or the web. "
    "(5) End with: " + DISCLAIMER
)


@lru_cache
def get_retriever() -> Retriever:
    return Retriever(get_settings())


class DocumentInfo(BaseModel):
    doc_id: str
    title: str
    issuer: str
    products: list[str]
    doc_type: str
    language: str
    edition: str
    official_source: bool
    url: str


class DocumentList(BaseModel):
    documents: list[DocumentInfo]
    scope_note: str


class Passage(BaseModel):
    chunk_id: str
    citation: str = Field(description="Reference to show the user, e.g. '…, Ziffer 1.2, S. 6'")
    document: str
    part: str
    section_title: str
    clause: str | None
    pages: str
    url: str = Field(description="PDF link opening at the cited page")
    text: str = Field(description="Verbatim source text (German)")
    relevance: float | None = None


class SearchResult(BaseModel):
    status: Literal["ok", "no_relevant_passage"]
    passages: list[Passage]
    guidance: str


class SectionResult(BaseModel):
    section: str
    passages: list[Passage]


def _passage(retriever: Retriever, chunk: Chunk, relevance: float | None = None) -> Passage:
    store = retriever.store
    return Passage(
        chunk_id=chunk.chunk_id,
        citation=store.citation(chunk),
        document=store.documents[chunk.doc_id].title,
        part=chunk.part_title,
        section_title=chunk.section_title,
        clause=chunk.clause,
        pages=store.pages(chunk),
        url=store.url(chunk),
        text=chunk.text,
        relevance=None if relevance is None else round(relevance, 3),
    )


def list_documents() -> DocumentList:
    """List the documents this plugin answers from: ERGO dental supplementary insurance only (tariff ZEK
    "Zahnersatz Sofort" and the Dental-Schutz 100 brochure).

    Call it when the user asks what is covered, or when a question might be about another product. Anything
    outside these documents is out of scope; do not answer it from general knowledge or the web.
    """
    documents = get_retriever().store.documents.values()
    log.info("list_documents")
    return DocumentList(
        documents=[
            DocumentInfo(**d.model_dump(mode="json", include=set(DocumentInfo.model_fields))) for d in documents
        ],
        scope_note=(
            "Only these ERGO dental insurance documents are covered. Questions about other insurance types "
            "(car, household, life, …), other insurers, or a customer's own contract or claim are out of scope: "
            "say so and do not answer them from general knowledge or web search."
        ),
    )


def search_conditions(
    query: Annotated[
        str,
        Field(
            description=(
                "Search query in GERMAN, the language of the documents. Translate the user's question and use "
                "the insurance terms the conditions would use, e.g. 'Implantate Leistung Ausschluss'."
            )
        ),
    ],
    question: Annotated[
        str | None, Field(description="The user's original question in their own language, if not German.")
    ] = None,
    doc_id: Annotated[str | None, Field(description="Restrict to one document (doc_id from list_documents).")] = None,
    top_k: Annotated[int, Field(ge=1, le=10, description="Number of passages to return.")] = 5,
) -> SearchResult:
    """Search the ERGO dental insurance documents (tariff ZEK, Dental-Schutz 100) and return the most relevant
    source passages with citations.

    Call this BEFORE answering any question about these products: coverage, exclusions, limits, waiting
    periods, cancellation, payments, procedures. Prefer it over web search. Passages are verbatim German text;
    answer in the user's language.
    """
    retriever = get_retriever()
    if doc_id and doc_id not in retriever.store.documents:
        raise ToolError(f"Unknown doc_id '{doc_id}'. Call list_documents for valid ids.")
    hits, relevant = retriever.search(query, question, doc_id, top_k)
    log.info(
        "search_conditions query=%r question=%r doc_id=%s -> %s %s",
        query,
        question,
        doc_id,
        "ok" if relevant else "no_relevant_passage",
        [f"{h.chunk.chunk_id}@{h.relevance:.3f}" for h in hits],
    )
    if not relevant:
        return SearchResult(
            status="no_relevant_passage",
            passages=[],
            guidance=(
                "The documents contain nothing relevant to this question. Tell the user the available ERGO dental "
                "insurance documents don't cover it and suggest ERGO customer service or an adviser. Do not answer "
                "from general knowledge or web search. " + DISCLAIMER
            ),
        )
    return SearchResult(
        status="ok",
        passages=[_passage(retriever, h.chunk, h.relevance) for h in hits],
        guidance=(
            "Use get_section when a passage is cut short or exclusions/limits may follow in the same section. "
            + ANSWER_RULES
        ),
    )


search_conditions.__doc__ += "\n    " + ANSWER_RULES


def get_section(
    chunk_id: Annotated[str, Field(description="chunk_id of a passage from search_conditions")],
) -> SectionResult:
    """Return the complete section a passage belongs to (all its clauses), e.g. to read the exclusions or
    limits that follow a benefit clause."""
    retriever = get_retriever()
    if chunk_id not in retriever.store.by_id:
        raise ToolError(f"Unknown chunk_id '{chunk_id}'. Use a chunk_id returned by search_conditions.")
    chunks = retriever.store.section(chunk_id)
    log.info("get_section chunk_id=%s -> %d passages", chunk_id, len(chunks))
    first = chunks[0]
    title = " ".join(filter(None, [first.section, first.section_title]))
    return SectionResult(
        section=f"{first.part_title} – {title}",
        passages=[_passage(retriever, c) for c in chunks],
    )
