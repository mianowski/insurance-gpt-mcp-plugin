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
            "query": "Zahnersatz Sofort ZEZ Implantate",
            "question": "Does Zahnersatz Sofort cover implants?",
            "doc_id": "ergo-zahn-broschuere-2022-07",
        },
    )
    assert not result.is_error
    data = result.structured_content
    assert data["status"] == "ok"
    row = data["passages"][0]
    assert row["chunk_id"] == "ergo-zahn-broschuere-2022-07:broschuere:t12.r2"
    assert row["citation"] == "Produktbroschüre Zahn-Zusatzversicherungen, „Sofortschutz – Implantate“, S. 10"
    assert row["url"].endswith(".pdf.coredownload.pdf#page=10")
    assert "Zahnersatz Sofort (ZEZ): Nein." in row["text"]
    assert all(p["chunk_id"].startswith("ergo-zahn-broschuere-2022-07:") for p in data["passages"])


def test_unrelated_question_returns_no_passages(retriever):
    data = _call("search_conditions", {"query": "Wetter morgen Berlin"}).structured_content
    assert data["status"] == "no_relevant_passage"
    assert data["passages"] == []


def test_get_section_returns_the_whole_table(retriever):
    row_id = "ergo-zahntarife-uebersicht-2024-08:uebersicht:t2.r2"  # Implantate in the Dental-Schutz table
    data = _call("get_section", {"chunk_id": row_id}).structured_content
    ids = [p["chunk_id"] for p in data["passages"]]
    assert row_id in ids and len(ids) > 5
    assert all(i.startswith("ergo-zahntarife-uebersicht-2024-08:uebersicht:t2.r") for i in ids)


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
    assert {d["doc_id"] for d in data["documents"]} == {
        "ergo-zahntarife-uebersicht-2024-08",
        "ergo-zahn-broschuere-2022-07",
    }
    assert "out of scope" in data["scope_note"] and "DS100" in data["scope_note"]
