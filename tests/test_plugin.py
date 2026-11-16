"""The plugin package (plugin/) stays consistent with the server."""

import asyncio
import json
import re

import yaml

from insurance_gpt.config import PROJECT_ROOT
from insurance_gpt.server import mcp

PLUGIN = PROJECT_ROOT / "plugin"
SKILL_DIR = PLUGIN / "skills" / "ergo-dental-coverage"


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, f"{path} needs a YAML frontmatter"
    return yaml.safe_load(match.group(1)), match.group(2)


def test_manifests_are_valid_and_point_to_the_same_server():
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", manifest["name"])
    servers = json.loads((PLUGIN / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    (server,) = servers.values()
    assert server["type"] == "streamable-http" and server["url"].endswith("/mcp")
    deps = yaml.safe_load((SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    (tool,) = deps["dependencies"]["tools"]
    assert tool["url"] == server["url"] and tool["value"] in servers


def test_skill_names_the_real_tools():
    meta, body = _frontmatter(SKILL_DIR / "SKILL.md")
    assert meta["name"] == SKILL_DIR.name
    assert 50 < len(meta["description"]) <= 1024
    tools = {t.name for t in asyncio.run(mcp.list_tools())}
    mentioned = set(re.findall(r"`([a-z_]+)`", body)) & tools
    assert mentioned == tools, f"skill mentions {sorted(mentioned)}, server has {sorted(tools)}"


def test_skill_references_exist():
    _, body = _frontmatter(SKILL_DIR / "SKILL.md")
    for ref in re.findall(r"`(references/[^`]+)`", body):
        assert (SKILL_DIR / ref).is_file(), ref
