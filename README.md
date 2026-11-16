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
| Ingestion: PDFs → sections and tariff-table rows with page refs (WBS 2.2) | done, 152 chunks in `knowledge/chunks/` |
| Retrieval: hybrid search (e5-large + BM25, Qdrant), eval set (WBS 3.3) | done, hit@5 1.00, MRR 0.93 |
| MCP server (Streamable HTTP, `/mcp`): `list_documents`, `search_conditions`, `get_section` | done |
| Verified citation card: `show_citation` + widget (WBS 5.2) | done, works in ChatGPT |
| ChatGPT connection (custom plugin via ngrok) | done, see the setup guide |
| Packaged skill + conversation script (WBS 4.1), demo script (WBS 6.5) | next |

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically, pinned in `.python-version`)
- Docker (optional, for the container)

## Local development

```bash
uv sync                      # create .venv with all deps + dev tools
cp .env.example .env         # optional, runtime settings (host, port, public host) use the IGPT_ prefix
uv run insurance-gpt         # MCP server at http://127.0.0.1:8000/mcp
uv run pytest                # tests
uv run ruff check . && uv run ruff format .
```

GitHub Actions runs Ruff and pytest on every push and pull request. Retrieval tests that require the
large embedding model are skipped when the model is not available in the CI environment.


### Knowledge base

```bash
uv run python -m insurance_gpt.ingest build                     # PDFs -> knowledge/chunks/*.jsonl
uv run python -m insurance_gpt.ingest show ergo-zahn-broschuere-2022-07   # review chunks (--full: whole text)
uv run python -m insurance_gpt.ingest index                     # embed chunks (downloads e5-large, ~2.2 GB)
uv run python -m insurance_gpt.retrieval.evaluate               # search quality on tests/eval/questions.yaml
```

The model and the embedding cache live in `.data/` (not committed). The server builds the cache on first
start if `index` wasn't run; retrieval tests are skipped until the model is downloaded.

### Tuning answer quality

Every knob that changes how good the answers are lives in **[`tuning.yaml`](tuning.yaml)**: chunk sizes,
embedding model, search mode (hybrid / dense / BM25), prefetch, `top_k`, the relevance threshold, all texts
ChatGPT reads (rules, tool descriptions, guidance, disclaimer) and the evaluation targets. Workflow:

1. Change a value (or copy the file to try a variant).
2. `uv run python -m insurance_gpt.retrieval.evaluate [--tuning variant.yaml]`: prints the active settings,
   hit@1/hit@5/MRR, rejection of unrelated questions and whether the targets are met (exit code 1 if not).
3. After `chunking` changes run `ingest build` first and commit the new chunks; after embedding changes
   `ingest index` (or let the server re-embed on start). Restart the server; refresh the plugin in ChatGPT
   when `answer` texts changed.

The server uses another file with `IGPT_TUNING_FILE=path.yaml`. Unknown or missing keys fail at startup.

To add a document: put an entry in `knowledge/sources.yaml` (URL, sha256, `parts` with page ranges and
structure), run `build`, review with `show`, commit the PDF and the chunk file together.

### Try the server

- **MCP Inspector:** `npx @modelcontextprotocol/inspector`, transport *Streamable HTTP*,
  URL `http://127.0.0.1:8000/mcp`.
- **ChatGPT:** see [Connect to ChatGPT](#connect-to-chatgpt).

## Connect to ChatGPT

Full step-by-step guide (host and tester, checks, troubleshooting):
[docs/CHATGPT_PLUGIN_SETUP.md](docs/CHATGPT_PLUGIN_SETUP.md). Short version:

ChatGPT needs a public HTTPS URL. For development, tunnel the local server with ngrok (free account,
one free static domain, so the URL stays the same between sessions):

1. Install ngrok (`winget install ngrok.ngrok`), sign up at ngrok.com, then
   `ngrok config add-authtoken <token>`. Claim your free static domain in the ngrok dashboard (Domains).
2. Start the server and allow that domain as Host (other hosts are rejected):
   ```powershell
   $env:IGPT_PUBLIC_HOSTS = "<your-domain>.ngrok-free.app"
   python -m uv run insurance-gpt
   ```
3. In a second terminal: `ngrok http 8000 --url <your-domain>.ngrok-free.app`
4. In ChatGPT: chatgpt.com/plugins → **+** → *Add custom MCP server* → name `ERGO Dental (demo)`,
   URL `https://<your-domain>.ngrok-free.app/mcp`, authentication *None* → accept the warning →
   *Create as a plugin*. Install it from your personal plugins (chatgpt.com/plugins?view=personal).
5. Open a **Work** chat, type `@`, pick the plugin and ask, e.g. *"Zahlt Dental-Schutz 90 für Implantate?"*

The server has no authentication yet: only keep the tunnel running while you test.

## Docker

```bash
docker build -t insurance-gpt .
docker run --rm -p 8000:8000 insurance-gpt
```

## Layout

```text
tuning.yaml          all quality knobs: chunking, retrieval, texts for ChatGPT, evaluation targets
src/insurance_gpt/   server.py, config.py (runtime), tuning.py (loads tuning.yaml), sources.py, ingest/ (PDF -> chunks),
                     retrieval/ (search), tools/ (MCP tools)
knowledge/           sources.yaml (document list), raw/ (source PDFs, <doc_id>.pdf), chunks/ (*.jsonl)
tests/               pytest; eval/questions.yaml (retrieval eval set)
docs/                architecture
```

## License

Apache 2.0, see [LICENSE](LICENSE). Source documents remain the property of their publishers.
