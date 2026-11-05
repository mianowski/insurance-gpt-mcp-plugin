import asyncio

from insurance_gpt.config import get_settings
from insurance_gpt.server import mcp
from insurance_gpt.sources import load_manifest


def test_manifest_is_valid():
    manifest = load_manifest(get_settings().sources_file)
    ids = [d.doc_id for d in manifest.documents]
    assert len(ids) == len(set(ids)), "doc_id must be unique"
    assert all(len(d.sha256) == 64 for d in manifest.documents)


def test_server_advertises_tools():
    tools = asyncio.run(mcp.list_tools())
    assert "list_documents" in {t.name for t in tools}


def test_list_documents_returns_manifest():
    result = asyncio.run(mcp.call_tool("list_documents", {}))
    assert not result.is_error
    assert {d["doc_id"] for d in result.structured_content["documents"]} == {
        "ergo-zek-2025-04",
        "ergo-ds100-brochure-2026-02",
    }
