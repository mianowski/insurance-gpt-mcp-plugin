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
    # numbered: "1 Title" bold headings with "1.2" clauses (terms).
    # headings: sections start at bold text >= heading_min_size (not "Label:" lines) or any text >= title_min_size.
    # mixed: headings, plus tariff comparison tables (header row matching table_headers) chunked row by row.
    structure: Literal["numbered", "headings", "mixed"]
    heading_min_size: float = 0.0
    title_min_size: float | None = None
    table_headers: str | None = None  # regex for tariff names in table header cells


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
    # Brochures printed as two-page spreads: landscape pages are parsed as a left and a right half.
    split_spreads: bool = False
    notes: str | None = None


class SourceManifest(BaseModel):
    version: int
    documents: list[SourceDocument]


def load_manifest(path: Path) -> SourceManifest:
    with path.open(encoding="utf-8") as f:
        return SourceManifest.model_validate(yaml.safe_load(f))
