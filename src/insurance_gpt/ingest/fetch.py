import hashlib
import logging
from pathlib import Path

import httpx

from insurance_gpt.sources import SourceDocument

log = logging.getLogger(__name__)


class HashMismatchError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_pdf(doc: SourceDocument, raw_dir: Path) -> Path:
    """Return knowledge/raw/<doc_id>.pdf, downloading it if missing, and verify its sha256."""
    path = raw_dir / f"{doc.doc_id}.pdf"
    if not path.exists():
        log.info("Downloading %s from %s", doc.doc_id, doc.url)
        raw_dir.mkdir(parents=True, exist_ok=True)
        response = httpx.get(str(doc.url), follow_redirects=True, timeout=60)
        response.raise_for_status()
        path.write_bytes(response.content)
    digest = sha256_of(path)
    if digest != doc.sha256:
        raise HashMismatchError(
            f"{path.name}: sha256 {digest} does not match sources.yaml ({doc.sha256}). "
            "The publisher may have changed the document; review it and update the manifest."
        )
    return path
