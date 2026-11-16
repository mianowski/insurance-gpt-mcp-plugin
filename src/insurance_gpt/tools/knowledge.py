"""Knowledge tools: list_documents, search_conditions, get_section.

They return source passages with citation metadata; ChatGPT writes the answer from them. Every text ChatGPT
reads (tool descriptions, rules, guidance) comes from the `answer` section of tuning.yaml.
"""

import logging
from functools import lru_cache
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from insurance_gpt.config import get_settings
from insurance_gpt.ingest.chunk import Chunk
from insurance_gpt.retrieval.search import Retriever
from insurance_gpt.tuning import get_tuning

log = logging.getLogger("insurance_gpt.tools")

TEXTS = get_tuning().answer
# Conversation rules (WBS 4.1), sent in the server instructions, the search_conditions description and every
# search result.
ANSWER_RULES = TEXTS.rules_text


@lru_cache
def get_retriever() -> Retriever:
    return Retriever(get_settings(), get_tuning().retrieval)


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
    documents = get_retriever().store.documents.values()
    products = list(dict.fromkeys(p for d in documents for p in d.products))
    log.info("list_documents")
    return DocumentList(
        documents=[
            DocumentInfo(**d.model_dump(mode="json", include=set(DocumentInfo.model_fields))) for d in documents
        ],
        scope_note=TEXTS.scope_note.replace("{products}", ", ".join(products)),
    )


def search_conditions(
    query: Annotated[
        str,
        Field(description=TEXTS.tools.search_query),
    ],
    question: Annotated[
        str | None, Field(description="The user's original question in their own language, if not German.")
    ] = None,
    doc_id: Annotated[str | None, Field(description="Restrict to one document (doc_id from list_documents).")] = None,
    top_k: Annotated[
        int, Field(ge=1, le=get_tuning().retrieval.max_top_k, description="Number of passages to return.")
    ] = get_tuning().retrieval.top_k,
) -> SearchResult:
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
            guidance=TEXTS.render(TEXTS.no_result_guidance),
        )
    return SearchResult(
        status="ok",
        passages=[_passage(retriever, h.chunk, h.relevance) for h in hits],
        guidance=TEXTS.render(TEXTS.result_guidance),
    )


def get_section(
    chunk_id: Annotated[str, Field(description="chunk_id of a passage from search_conditions")],
) -> SectionResult:
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
