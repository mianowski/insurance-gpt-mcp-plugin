# insurance-gpt-mcp-plugin

ChatGPT plugin (MCP server) that answers customer questions about ERGO insurance terms and conditions
and backs each answer with a **verified, quoted citation** (document, section, page, link).

PoC / demo only: it uses **public** documents. Architecture and decisions are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

| Part | State |
| --- | --- |
| Repo, runtime, config, Docker (WBS 3.1) | done |
| Source pack manifest `knowledge/sources.yaml` (WBS 2.1) | 2 documents; doc A still needs an official ergo.de URL |
| Ingestion: PDFs → section-aware chunks with page refs (WBS 2.2) | done, 79 chunks in `knowledge/chunks/` |
| MCP server (Streamable HTTP, `/mcp`) | running, `list_documents` tool only |
| Retrieval (embeddings + Qdrant), citations, widget, skill | next |

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically, pinned in `.python-version`)
- Docker (optional, for the container)

## Local development

```bash
uv sync                      # create .venv with all deps + dev tools
cp .env.example .env         # optional, settings use the IGPT_ prefix
uv run insurance-gpt         # MCP server at http://127.0.0.1:8000/mcp
uv run pytest                # tests
uv run ruff check . && uv run ruff format .
```

Ingestion and retrieval dependencies (PDF parsing, embeddings, Qdrant) are an optional extra:
`uv sync --extra rag`.

### Knowledge base

```bash
uv run python -m insurance_gpt.ingest build                     # PDFs -> knowledge/chunks/*.jsonl
uv run python -m insurance_gpt.ingest show ergo-zek-2025-04     # review chunks (--full for whole text)
```

To add a document: put an entry in `knowledge/sources.yaml` (URL, sha256, `parts` with page ranges and
structure), run `build`, review with `show`, commit the PDF and the chunk file together.

### Try the server

- **MCP Inspector:** `npx @modelcontextprotocol/inspector`, transport *Streamable HTTP*,
  URL `http://127.0.0.1:8000/mcp`.
- **ChatGPT:** expose the server over HTTPS (e.g. `ngrok http 8000 --url <your-static-domain>`), then
  chatgpt.com/plugins → **+** → *Add custom MCP server* → URL `https://<domain>/mcp`, no auth →
  *Create as a plugin*; install it from your personal plugins and use it in a **Work** chat with `@`.

## Docker

```bash
docker build -t insurance-gpt .
docker run --rm -p 8000:8000 insurance-gpt
```

## Layout

```text
src/insurance_gpt/   server.py (MCP tools), config.py, sources.py (manifest model), ingest/ (PDF -> chunks)
knowledge/           sources.yaml (document list), raw/ (source PDFs, <doc_id>.pdf), chunks/ (*.jsonl)
tests/               pytest
docs/                architecture
```

## License

Apache 2.0, see [LICENSE](LICENSE). Source documents remain the property of their publishers.
