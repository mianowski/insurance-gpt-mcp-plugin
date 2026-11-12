"""Ingestion CLI.

uv run python -m insurance_gpt.ingest build [--doc DOC_ID]   # PDFs → knowledge/chunks/<doc_id>.jsonl
uv run python -m insurance_gpt.ingest show DOC_ID [--full]    # review the chunks of one document
uv run python -m insurance_gpt.ingest index                   # embed chunks → .data/index (search cache)
"""

import argparse
import logging
import re
import sys
from pathlib import Path

from insurance_gpt.config import get_settings
from insurance_gpt.ingest.chunk import Chunk, chunk_part
from insurance_gpt.ingest.fetch import ensure_pdf
from insurance_gpt.ingest.layout import extract_lines, extract_regions
from insurance_gpt.ingest.tables import extract_part
from insurance_gpt.retrieval.store import read_chunks
from insurance_gpt.sources import SourceDocument, load_manifest


def chunks_path(knowledge_dir: Path, doc_id: str) -> Path:
    return knowledge_dir / "chunks" / f"{doc_id}.jsonl"


def build_document(doc: SourceDocument, knowledge_dir: Path) -> list[Chunk]:
    pdf = ensure_pdf(doc, knowledge_dir / "raw")
    chunks: list[Chunk] = []
    for part in doc.parts:
        pages = (pdf, part.first_page, part.last_page, doc.header_margin, doc.footer_margin, doc.split_spreads)
        if part.structure == "mixed":
            regions = extract_regions(*pages)
            lines, tables = extract_part(regions, re.compile(part.table_headers or "$^"))
            chunks.extend(chunk_part(doc, part, lines, tables))
        else:
            chunks.extend(chunk_part(doc, part, extract_lines(*pages)))
    ids = [c.chunk_id for c in chunks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"{doc.doc_id}: duplicate chunk ids {sorted(duplicates)}")
    return chunks


def write_chunks(chunks: list[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + "\n")


def cmd_build(args: argparse.Namespace) -> None:
    settings = get_settings()
    manifest = load_manifest(settings.sources_file)
    docs = [d for d in manifest.documents if args.doc in (None, d.doc_id)]
    if not docs:
        sys.exit(f"Unknown doc_id: {args.doc}")
    for doc in docs:
        chunks = build_document(doc, settings.knowledge_dir)
        path = chunks_path(settings.knowledge_dir, doc.doc_id)
        write_chunks(chunks, path)
        sizes = sorted(len(c.text) for c in chunks)
        print(
            f"{doc.doc_id}: {len(chunks)} chunks "
            f"(chars min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}) -> {path}"
        )


def cmd_show(args: argparse.Namespace) -> None:
    settings = get_settings()
    for chunk in read_chunks(chunks_path(settings.knowledge_dir, args.doc_id)):
        pages = f"p.{chunk.page_start}" + (f"-{chunk.page_end}" if chunk.page_end != chunk.page_start else "")
        where = " ".join(filter(None, [chunk.section, chunk.section_title]))
        print(f"[{chunk.chunk_id}] {pages} | {chunk.chapter or '-'} | {where} | {len(chunk.text)} chars")
        print("    " + (chunk.text if args.full else chunk.text[:160]).replace("\n", "\n    "))


def cmd_index(args: argparse.Namespace) -> None:
    from insurance_gpt.retrieval.embed import Embedder
    from insurance_gpt.retrieval.index import fingerprint, load_or_embed
    from insurance_gpt.retrieval.store import KnowledgeStore

    settings = get_settings()
    store = KnowledgeStore(settings.sources_file, settings.chunks_dir)
    load_or_embed(store.chunks, Embedder(settings.embedding_model, settings.models_dir), settings.index_dir)
    name = fingerprint(store.chunks, settings.embedding_model)
    print(f"{len(store.chunks)} chunks embedded with {settings.embedding_model} -> {settings.index_dir / name}.npz")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m insurance_gpt.ingest")
    sub = parser.add_subparsers(required=True)
    build = sub.add_parser("build", help="parse source PDFs and write chunk files")
    build.add_argument("--doc", help="only this doc_id")
    build.set_defaults(func=cmd_build)
    show = sub.add_parser("show", help="print the chunks of one document")
    show.add_argument("doc_id")
    show.add_argument("--full", action="store_true", help="print full chunk text")
    show.set_defaults(func=cmd_show)
    index = sub.add_parser("index", help="embed all chunks into the search index cache")
    index.set_defaults(func=cmd_index)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
