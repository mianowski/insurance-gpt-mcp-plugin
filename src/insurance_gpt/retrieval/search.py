"""Hybrid search: dense (multilingual, cross-language) + BM25 (exact German terms), fused with RRF.

All knobs (models, mode, limits, relevance threshold) come from the `retrieval` section of tuning.yaml.
"""

from dataclasses import dataclass

import numpy as np
from qdrant_client import QdrantClient, models

from insurance_gpt.config import Settings
from insurance_gpt.ingest.chunk import Chunk
from insurance_gpt.retrieval.embed import Embedder
from insurance_gpt.retrieval.index import DENSE, SPARSE, build_collection, load_or_embed
from insurance_gpt.retrieval.store import KnowledgeStore
from insurance_gpt.tuning import Retrieval


@dataclass
class Hit:
    chunk: Chunk
    relevance: float  # best cosine similarity between the chunk and any query variant


class Retriever:
    def __init__(self, settings: Settings, tuning: Retrieval):
        self.settings = settings
        self.tuning = tuning
        self.store = KnowledgeStore(settings.sources_file, settings.chunks_dir)
        self.embedder = Embedder(tuning, settings.models_dir)
        arrays = load_or_embed(self.store.chunks, self.embedder, tuning, settings.index_dir)
        self._dense = {c.chunk_id: arrays["dense"][i] for i, c in enumerate(self.store.chunks)}
        self.client = QdrantClient(url=settings.qdrant_url) if settings.qdrant_url else QdrantClient(":memory:")
        build_collection(self.client, settings.collection, self.store.chunks, arrays)

    def search(
        self, query: str, question: str | None = None, doc_id: str | None = None, top_k: int | None = None
    ) -> tuple[list[Hit], bool]:
        """Return (hits, relevant). `relevant` is False when even the best hit is below min_relevance."""
        t = self.tuning
        top_k = top_k or t.top_k
        flt = (
            models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))])
            if doc_id
            else None
        )
        variants = [query, question] if t.search_with_question else [query]
        # Dense vectors are always computed: the relevance threshold is measured on them, whatever the mode.
        dense_queries = [self.embedder.query_dense(q) for q in dict.fromkeys(filter(None, variants))]
        prefetch = []
        if t.mode in ("hybrid", "dense"):
            prefetch += [
                models.Prefetch(query=vec.tolist(), using=DENSE, limit=t.prefetch_limit, filter=flt)
                for vec in dense_queries
            ]
        if t.mode in ("hybrid", "sparse"):
            sparse = self.embedder.query_sparse(query)
            prefetch.append(
                models.Prefetch(
                    query=models.SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist()),
                    using=SPARSE,
                    limit=t.prefetch_limit,
                    filter=flt,
                )
            )
        result = self.client.query_points(
            self.settings.collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        hits = []
        for point in result.points:
            chunk = self.store.by_id[point.payload["chunk_id"]]
            relevance = max(float(np.dot(self._dense[chunk.chunk_id], q)) for q in dense_queries)
            hits.append(Hit(chunk, relevance))
        relevant = any(h.relevance >= t.min_relevance for h in hits)
        return hits, relevant
