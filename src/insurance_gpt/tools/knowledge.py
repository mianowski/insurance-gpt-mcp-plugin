"""Knowledge tools: list_documents, search_conditions, get_section.

They return source passages with citation metadata; ChatGPT writes the answer from them.
"""

from functools import lru_cache
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from insurance_gpt.config import get_settings
from insurance_gpt.ingest.chunk import Chunk
from insurance_gpt.retrieval.search import Retriever

DISCLAIMER = "Informational only; the insurance contract and its full conditions are decisive."


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
    """List the insurance documents this plugin can answer from (products, document type, edition).

    Use it to tell the user what is covered and to recognise questions about other products or insurers,
    which are out of scope.
    """
    documents = get_retriever().store.documents.values()
    return DocumentList(
        documents=[
            DocumentInfo(**d.model_dump(mode="json", include=set(DocumentInfo.model_fields))) for d in documents
        ],
        scope_note=(
            "Only these ERGO dental insurance documents are covered. Questions about other insurance types "
            "(car, household, life, …), other insurers, or a customer's own contract or claim are out of scope."
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
    """Search the ERGO insurance conditions and return the most relevant source passages with citations.

    Call this for every question about coverage, exclusions, limits, waiting periods, cancellation,
    payments or procedures. Answer only from the returned passages, cite them by their `citation`, and say
    so when they do not answer the question. Passages are in German; answer in the user's language.
    """
    retriever = get_retriever()
    if doc_id and doc_id not in retriever.store.documents:
        raise ToolError(f"Unknown doc_id '{doc_id}'. Call list_documents for valid ids.")
    hits, relevant = retriever.search(query, question, doc_id, top_k)
    if not relevant:
        return SearchResult(
            status="no_relevant_passage",
            passages=[],
            guidance=(
                "The documents contain nothing relevant to this question. Tell the user it is not covered by the "
                "available ERGO dental insurance documents; do not answer from general knowledge. " + DISCLAIMER
            ),
        )
    return SearchResult(
        status="ok",
        passages=[_passage(retriever, h.chunk, h.relevance) for h in hits],
        guidance=(
            "Answer only from these passages and cite the ones you rely on. If they don't answer the question, "
            "say so. Use get_section to read a whole section when a passage is cut short. " + DISCLAIMER
        ),
    )


def get_section(
    chunk_id: Annotated[str, Field(description="chunk_id of a passage from search_conditions")],
) -> SectionResult:
    """Return the complete section a passage belongs to (all its clauses), e.g. to read the exclusions or
    limits that follow a benefit clause."""
    retriever = get_retriever()
    if chunk_id not in retriever.store.by_id:
        raise ToolError(f"Unknown chunk_id '{chunk_id}'. Use a chunk_id returned by search_conditions.")
    chunks = retriever.store.section(chunk_id)
    first = chunks[0]
    title = " ".join(filter(None, [first.section, first.section_title]))
    return SectionResult(
        section=f"{first.part_title} – {title}",
        passages=[_passage(retriever, c) for c in chunks],
    )
