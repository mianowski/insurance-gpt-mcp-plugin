"""Knowledge store: the committed chunks plus the manifest, with citation labels and PDF deep links."""

import re
from pathlib import Path

from insurance_gpt.ingest.chunk import Chunk
from insurance_gpt.sources import SourceDocument, load_manifest

TABLE_ROW_RE = re.compile(r"[.]r[0-9]+$")


def read_chunks(path: Path) -> list[Chunk]:
    with path.open(encoding="utf-8") as f:
        return [Chunk.model_validate_json(line) for line in f if line.strip()]


def section_key(chunk: Chunk) -> str:
    """Chunks with the same key form one section: "doc:part:4" for numbered parts, the whole table for table
    rows ("doc:part:t2.r5" -> "doc:part:t2"), else the heading id."""
    base = chunk.chunk_id.split("#")[0]
    if chunk.section is not None:
        return f"{chunk.doc_id}:{chunk.part_id}:{chunk.section}"
    return TABLE_ROW_RE.sub("", base)


class KnowledgeStore:
    def __init__(self, sources_file: Path, chunks_dir: Path):
        manifest = load_manifest(sources_file)
        self.documents: dict[str, SourceDocument] = {d.doc_id: d for d in manifest.documents}
        self.chunks: list[Chunk] = []
        for doc_id in self.documents:
            self.chunks.extend(read_chunks(chunks_dir / f"{doc_id}.jsonl"))
        self.by_id: dict[str, Chunk] = {c.chunk_id: c for c in self.chunks}

    def section(self, chunk_id: str) -> list[Chunk]:
        key = section_key(self.by_id[chunk_id])
        return [c for c in self.chunks if section_key(c) == key]

    def citation(self, chunk: Chunk) -> str:
        """Human-readable reference, e.g. 'Versicherungsbedingungen – Tarif ZEK, Ziffer 1.2, S. 6'."""
        if chunk.clause or chunk.section:
            where = f"Ziffer {chunk.clause or chunk.section}"
        else:
            title = chunk.section_title.rstrip(":")
            where = f"„{chunk.chapter} – {title}“" if chunk.chapter else f"„{title}“"
        return f"{chunk.part_title}, {where}, {self.pages(chunk)}"

    @staticmethod
    def pages(chunk: Chunk) -> str:
        if chunk.page_start == chunk.page_end:
            return f"S. {chunk.page_start}"
        return f"S. {chunk.page_start}–{chunk.page_end}"

    def url(self, chunk: Chunk) -> str:
        return f"{self.documents[chunk.doc_id].url}#page={chunk.page_start}"
