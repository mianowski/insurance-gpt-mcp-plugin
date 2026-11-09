"""Embedding cache + Qdrant collection.

Embeddings are cached in .data/index/<fingerprint>.npz, where the fingerprint covers the chunk texts and the
model. Any change to the knowledge base or the model produces a new fingerprint, so a stale index can't be
served. The Qdrant collection (in-memory by default) is loaded from that cache.
"""

import hashlib
import logging
import uuid
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

from insurance_gpt.ingest.chunk import Chunk
from insurance_gpt.retrieval.embed import SPARSE_MODEL, Embedder

log = logging.getLogger(__name__)

DENSE = "dense"
SPARSE = "bm25"


def embedding_text(chunk: Chunk) -> str:
    """What gets embedded: the chunk text with its headings, so short clauses keep their context."""
    heading = " – ".join(filter(None, [chunk.part_title, chunk.chapter, chunk.section_title, chunk.clause]))
    return f"{heading}\n{chunk.text}"


def fingerprint(chunks: list[Chunk], dense_model: str) -> str:
    h = hashlib.sha256(f"{dense_model}|{SPARSE_MODEL}|v1".encode())
    for chunk in chunks:
        h.update(f"{chunk.chunk_id}\0{embedding_text(chunk)}\0".encode())
    return h.hexdigest()[:16]


def load_or_embed(chunks: list[Chunk], embedder: Embedder, index_dir: Path) -> dict[str, np.ndarray]:
    path = index_dir / f"{fingerprint(chunks, embedder.dense_model)}.npz"
    if path.exists():
        cached = np.load(path)
        return {key: cached[key] for key in cached.files}
    log.info("Embedding %d chunks with %s (cache %s)", len(chunks), embedder.dense_model, path.name)
    texts = [embedding_text(c) for c in chunks]
    sparse = embedder.passages_sparse(texts)
    arrays = {
        "dense": embedder.passages_dense(texts),
        # Ragged sparse vectors stored flat: indices/values plus per-chunk offsets.
        "sparse_offsets": np.cumsum([0] + [len(s.indices) for s in sparse]),
        "sparse_indices": np.concatenate([s.indices for s in sparse]),
        "sparse_values": np.concatenate([s.values for s in sparse]),
    }
    index_dir.mkdir(parents=True, exist_ok=True)
    np.savez(path, **arrays)
    return arrays


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def build_collection(client: QdrantClient, collection: str, chunks: list[Chunk], arrays: dict[str, np.ndarray]) -> None:
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(
        collection,
        vectors_config={DENSE: models.VectorParams(size=arrays["dense"].shape[1], distance=models.Distance.COSINE)},
        sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    offsets = arrays["sparse_offsets"]
    points = [
        models.PointStruct(
            id=point_id(chunk.chunk_id),
            vector={
                DENSE: arrays["dense"][i].tolist(),
                SPARSE: models.SparseVector(
                    indices=arrays["sparse_indices"][offsets[i] : offsets[i + 1]].tolist(),
                    values=arrays["sparse_values"][offsets[i] : offsets[i + 1]].tolist(),
                ),
            },
            payload={"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id, "part_id": chunk.part_id},
        )
        for i, chunk in enumerate(chunks)
    ]
    client.upsert(collection, points=points)
