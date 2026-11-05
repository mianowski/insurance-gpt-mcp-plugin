"""Document manifest (knowledge/sources.yaml) — the versioned list of documents in the knowledge base."""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, HttpUrl


class SourceDocument(BaseModel):
    doc_id: str
    title: str
    issuer: str
    products: list[str]
    doc_type: Literal["terms", "product_info", "brochure", "faq"]
    language: Literal["de", "en"]
    edition: str
    url: HttpUrl
    official_source: bool
    retrieved: date
    sha256: str
    notes: str | None = None


class SourceManifest(BaseModel):
    version: int
    documents: list[SourceDocument]


def load_manifest(path: Path) -> SourceManifest:
    with path.open(encoding="utf-8") as f:
        return SourceManifest.model_validate(yaml.safe_load(f))
