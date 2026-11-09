"""Dense (multilingual) and sparse (BM25, German stemming) embeddings via fastembed, run locally on CPU."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fastembed import SparseEmbedding, SparseTextEmbedding, TextEmbedding

SPARSE_MODEL = "Qdrant/bm25"


@dataclass(frozen=True)
class DenseModelSpec:
    query_prefix: str = ""
    passage_prefix: str = ""


# Models we have evaluated; e5 models are trained with "query: " / "passage: " prefixes.
DENSE_MODELS = {
    "intfloat/multilingual-e5-large": DenseModelSpec("query: ", "passage: "),
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": DenseModelSpec(),
}


class Embedder:
    def __init__(self, dense_model: str, models_dir: Path):
        if dense_model not in DENSE_MODELS:
            raise ValueError(f"Unsupported embedding model {dense_model}; known: {sorted(DENSE_MODELS)}")
        self.dense_model = dense_model
        self.spec = DENSE_MODELS[dense_model]
        self._dense = TextEmbedding(dense_model, cache_dir=str(models_dir))
        self._sparse = SparseTextEmbedding(SPARSE_MODEL, cache_dir=str(models_dir), language="german")

    def passages_dense(self, texts: list[str]) -> np.ndarray:
        return _normalize(np.array(list(self._dense.embed([self.spec.passage_prefix + t for t in texts]))))

    def passages_sparse(self, texts: list[str]) -> list[SparseEmbedding]:
        return list(self._sparse.embed(texts))

    def query_dense(self, text: str) -> np.ndarray:
        return _normalize(np.array(list(self._dense.embed([self.spec.query_prefix + text]))))[0]

    def query_sparse(self, text: str) -> SparseEmbedding:
        return next(iter(self._sparse.query_embed(text)))


def _normalize(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
