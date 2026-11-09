"""Retrieval and tool tests. They need the embedding model in .data/models (downloaded on the first
`python -m insurance_gpt.ingest index`, ~2.2 GB) and are skipped without it."""

import asyncio

import pytest

from insurance_gpt.config import get_settings

MODEL_DIR = get_settings().models_dir / "models--Qdrant--multilingual-e5-large-onnx"
pytestmark = pytest.mark.skipif(
    not MODEL_DIR.exists(), reason="embedding model not downloaded: run python -m insurance_gpt.ingest index"
)


@pytest.fixture(scope="module")
def retriever():
    from insurance_gpt.tools.knowledge import get_retriever

    return get_retriever()


def _call(tool: str, args: dict):
    from insurance_gpt.server import mcp

    return asyncio.run(mcp.call_tool(tool, args))


def test_eval_set_meets_targets(retriever):
    from insurance_gpt.retrieval.evaluate import evaluate

    report = evaluate(retriever)
    misses = [o.id for o in report.in_scope if not (o.rank and o.relevant)]
    assert report.hit_at(report.k) >= 0.9, f"missed: {misses}"
    assert report.mrr >= 0.85
    assert report.rejection_rate == 1.0, [o.id for o in report.search_rejects if o.relevant]


def test_search_returns_citable_passages(retriever):
    result = _call(
        "search_conditions",
        {
            "query": "Implantate Leistung Ausschluss",
            "question": "Does ZEK pay for implants?",
            "doc_id": "ergo-zek-2025-04",
        },
    )
    assert not result.is_error
    data = result.structured_content
    assert data["status"] == "ok"
    exclusion = next(p for p in data["passages"] if p["chunk_id"] == "ergo-zek-2025-04:avb:1.2")
    assert exclusion["citation"] == "Versicherungsbedingungen – Vertragsgrundlage Tarif ZEK, Ziffer 1.2, S. 6"
    assert exclusion["url"].endswith(".pdf#page=6")
    assert "Implantate" in exclusion["text"]
    assert all(p["chunk_id"].startswith("ergo-zek-2025-04:") for p in data["passages"])


def test_unrelated_question_returns_no_passages(retriever):
    data = _call("search_conditions", {"query": "Wetter morgen Berlin"}).structured_content
    assert data["status"] == "no_relevant_passage"
    assert data["passages"] == []


def test_get_section_returns_all_clauses(retriever):
    data = _call("get_section", {"chunk_id": "ergo-zek-2025-04:avb:1.2"}).structured_content
    ids = [p["chunk_id"] for p in data["passages"]]
    assert ids[0] == "ergo-zek-2025-04:avb:1.1#1"
    assert "ergo-zek-2025-04:avb:1.5" in ids
    assert all(i.startswith("ergo-zek-2025-04:avb:1.") for i in ids)


@pytest.mark.parametrize(
    ("tool", "args"),
    [("get_section", {"chunk_id": "nope"}), ("search_conditions", {"query": "x", "doc_id": "nope"})],
)
def test_invalid_ids_raise_tool_errors(retriever, tool, args):
    """ToolError reaches the client as an isError result with this message, so the model can recover."""
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="Unknown .* 'nope'"):
        _call(tool, args)


def test_list_documents(retriever):
    data = _call("list_documents", {}).structured_content
    assert {d["doc_id"] for d in data["documents"]} == {"ergo-zek-2025-04", "ergo-ds100-brochure-2026-02"}
    assert "out of scope" in data["scope_note"]
