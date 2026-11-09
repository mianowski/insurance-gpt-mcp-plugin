"""Document manifest (knowledge/sources.yaml) — the versioned list of documents in the knowledge base."""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, HttpUrl


class DocumentPart(BaseModel):
    """A logical document inside a PDF (one PDF can bundle e.g. product info sheet + terms)."""

    part_id: str
    title: str
    first_page: int
    last_page: int
    # numbered: "1 Title" bold headings with "1.2" clauses (terms); headings: bold text >= heading_min_size
    structure: Literal["numbered", "headings"]
    heading_min_size: float = 0.0


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
    parts: list[DocumentPart]
    # Lines this close to the top/bottom page edge (pt) are running headers/footers and are dropped.
    header_margin: float = 40.0
    footer_margin: float = 45.0
    notes: str | None = None


class SourceManifest(BaseModel):
    version: int
    documents: list[SourceDocument]


def load_manifest(path: Path) -> SourceManifest:
    with path.open(encoding="utf-8") as f:
        return SourceManifest.model_validate(yaml.safe_load(f))
