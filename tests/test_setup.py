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
    assert set(tools) == {"list_documents", "search_conditions", "get_section", "show_citation"}
    assert all(t.annotations.read_only_hint for t in tools.values())
    assert tools["search_conditions"].input_schema["required"] == ["query"]
    assert "outputSchema" in tools["search_conditions"].model_dump(by_alias=True, exclude_none=True)


def test_transport_security_accepts_only_local_and_public_hosts():
    from insurance_gpt.config import Settings
    from insurance_gpt.server import transport_security

    sec = transport_security(Settings(public_hosts="demo.ngrok-free.app, other.example.org"))
    assert sec.enable_dns_rebinding_protection
    assert {"demo.ngrok-free.app", "other.example.org", "localhost:*"} <= set(sec.allowed_hosts)
    assert "https://demo.ngrok-free.app" in sec.allowed_origins
    assert "evil.example.com" not in sec.allowed_hosts


def test_tools_carry_the_answer_rules():
    from insurance_gpt.tools.knowledge import ANSWER_RULES

    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert all(t.description for t in tools.values()), "every tool needs a description"
    assert ANSWER_RULES.startswith("Rules: (0) Answer in the language")
    assert ANSWER_RULES in tools["search_conditions"].description
    assert ANSWER_RULES in mcp.instructions
    query = tools["search_conditions"].input_schema["properties"]["query"]
    assert query["description"].startswith("Search query in GERMAN")
    texts = [mcp.instructions, *(t.description for t in tools.values())]
    assert not [t for t in texts if "{" in t], "unfilled placeholder in a text from tuning.yaml"


def test_tuning_file_is_strict(tmp_path):
    import pytest
    import yaml

    from insurance_gpt.tuning import load_tuning

    data = yaml.safe_load(get_settings().tuning_file.read_text(encoding="utf-8"))
    data["retrieval"]["min_relevanse"] = 0.5  # typo
    bad = tmp_path / "tuning.yaml"
    bad.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="min_relevanse"):
        load_tuning(bad)
