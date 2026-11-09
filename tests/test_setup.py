import asyncio

from insurance_gpt.config import get_settings
from insurance_gpt.server import mcp
from insurance_gpt.sources import load_manifest


def test_manifest_is_valid():
    manifest = load_manifest(get_settings().sources_file)
    ids = [d.doc_id for d in manifest.documents]
    assert len(ids) == len(set(ids)), "doc_id must be unique"
    assert all(len(d.sha256) == 64 for d in manifest.documents)


def test_server_advertises_read_only_tools():
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert set(tools) == {"list_documents", "search_conditions", "get_section"}
    assert all(t.annotations.read_only_hint for t in tools.values())
    assert tools["search_conditions"].input_schema["required"] == ["query"]
    assert "outputSchema" in tools["search_conditions"].model_dump(by_alias=True, exclude_none=True)
