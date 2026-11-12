# Connect the ERGO Dental plugin to ChatGPT

This guide gets the demo running in ChatGPT. It has two roles:

- **Host**: runs the MCP server on their machine and exposes it over HTTPS (sections 1–4).
- **Tester**: only adds the plugin in ChatGPT, using the host's URL (sections 5–6).

The server answers from public ERGO dental insurance documents only (see `knowledge/sources.yaml`). It has
**no login yet**: anyone with the URL can call it. Keep the tunnel running only while you test.

---

## 1. One-time setup (host)

Requirements: Windows, macOS or Linux; Python is installed by `uv`; ~3 GB free disk (embedding model).

1. **Get the code**

   ```powershell
   git clone https://github.com/mianowski/insurance-gpt-mcp-plugin.git
   cd insurance-gpt-mcp-plugin
   ```

2. **Install uv** (Python package manager), then open a new terminal:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
   curl -LsSf https://astral.sh/uv/install.sh | sh                                      # macOS / Linux
   ```

3. **Install dependencies and build the search index** (downloads the e5-large model, ~2.2 GB, once):

   ```powershell
   uv sync
   uv run python -m insurance_gpt.ingest index
   ```

   It ends with `152 chunks embedded with intfloat/multilingual-e5-large -> …`.
4. **Install ngrok** and connect it to your account (free at [ngrok.com](https://ngrok.com)):

   ```powershell
   winget install --id Ngrok.Ngrok -e --source winget   # Windows (then: ngrok update)
   brew install ngrok                                   # macOS
   ngrok config add-authtoken <your-authtoken>          # from the ngrok dashboard
   ```

5. **Recommended: claim your free static domain** in the ngrok dashboard → *Domains*
   (e.g. `your-name.ngrok-free.app`). Without it the URL changes on every ngrok restart and every tester
   has to add the plugin again.

## 2. Start the server (host, each session)

Terminal 1 — tell the server which public hostname to accept, then start it:

```powershell
# PowerShell
$env:IGPT_PUBLIC_HOSTS = "your-name.ngrok-free.app"
uv run insurance-gpt
```

```bash
# bash
IGPT_PUBLIC_HOSTS=your-name.ngrok-free.app uv run insurance-gpt
```

Wait for `Uvicorn running on http://127.0.0.1:8000` (a few seconds: it loads the model first).

> `IGPT_PUBLIC_HOSTS` is required. The server rejects requests for any other hostname (HTTP 421), which
> protects it against DNS rebinding. Put the hostname only, without `https://`. You can also set it in a
> `.env` file (copy `.env.example`).

## 3. Start the tunnel (host, each session)

Terminal 2:

```powershell
ngrok http 8000 --url your-name.ngrok-free.app
```

Without a static domain, run `ngrok http 8000`, copy the `https://….ngrok-free.app` address it shows,
and restart the server with that hostname in `IGPT_PUBLIC_HOSTS`.

Your plugin URL is: **`https://your-name.ngrok-free.app/mcp`** (note the `/mcp` at the end).

## 4. Check that it is reachable (host)

Open `https://your-name.ngrok-free.app/mcp` in a browser (if ngrok shows a warning page, click *Visit Site*):

| You see | Meaning |
| --- | --- |
| `{"jsonrpc":"2.0", … "Not Acceptable: Client must accept text/event-stream"}` | **OK**: the server is reachable; this is just a browser speaking to an MCP endpoint. |
| `Invalid Host header` | `IGPT_PUBLIC_HOSTS` doesn't match the tunnel hostname. |
| ngrok error page (`ERR_NGROK_…`) | The server isn't running on port 8000, or the tunnel points elsewhere. |
| `404 Not Found` | The URL is missing `/mcp`. |

For a closer look at the tools, use the MCP Inspector: `npx @modelcontextprotocol/inspector`, transport
*Streamable HTTP*, URL `http://127.0.0.1:8000/mcp`.

---

## 5. Add the plugin in ChatGPT (tester)

You need a ChatGPT plan that allows custom MCP servers (check your plan; menus may differ slightly).

1. Open **[chatgpt.com/plugins](https://chatgpt.com/plugins)** → click **+** → **Add custom MCP server**.
2. Fill in:
   - **Name:** `ERGO Dental (demo)`
   - **Server URL:** `https://your-name.ngrok-free.app/mcp` (from the host)
   - **Authentication:** *No authentication*
3. Accept the warning about custom servers → **Create as a plugin**.
4. Open your personal plugins (**[chatgpt.com/plugins?view=personal](https://chatgpt.com/plugins?view=personal)**),
   open the plugin and **install** it with **+**.

## 6. Use it (tester)

1. On the ChatGPT home page switch the tab from **Chat** to **Work** and start a new chat.
2. Type **`@`**, choose **ERGO Dental (demo)**, then ask your question.
3. For a clean demo:
   - start a **new chat for each question**, so earlier answers don't steer the next one;
   - **turn web search off** in the chat, so answers come only from the ERGO documents.

Example questions (German or English; the answer comes back in the language of the question):

| Question | Expected answer (source) |
| --- | --- |
| *Zahlt Zahnersatz Sofort für Implantate?* | No (brochure p. 10, Zahnersatz Sofort table) |
| *Zahlt Dental-Schutz 90 für Implantate?* | Yes, 90 % incl. statutory insurance share (brochure p. 9) |
| *Was kostet Dental-Schutz 100 für einen 35-Jährigen?* | Monthly premium for age 31–40, first 6 months half (brochure p. 10) |
| *Is there a waiting period?* | No waiting periods (brochure pp. 9–10) |
| *Wird die professionelle Zahnreinigung bezahlt?* | DVB once a year, DVB + DVE without limit (overview p. 2) |
| *How do I cancel my household insurance?* | Declined: not covered by these documents |

A good answer quotes the German source sentence and names document, section and page. Every answer ends
with: *"Informational only; the insurance contract and its full conditions are decisive."*

---

## After changes on the server

- **Code or documents changed** (`git pull`): stop the server (`Ctrl+C`), run
  `uv sync` and `uv run python -m insurance_gpt.ingest index`, start it again. The tunnel can keep running.
- **Tool descriptions or instructions changed**: ChatGPT may keep the old ones. Refresh the plugin in your
  personal plugins, or remove it and add it again with the same URL.
- **Tunnel URL changed** (no static domain): restart the server with the new `IGPT_PUBLIC_HOSTS` and add
  the plugin again with the new URL.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| ChatGPT can't connect, browser shows `Invalid Host header` | `IGPT_PUBLIC_HOSTS` doesn't match the tunnel hostname. Restart the server with the right hostname. |
| Browser shows `404` | URL is missing `/mcp`. |
| ngrok shows `ERR_NGROK_8012` / bad gateway | The server isn't running on port 8000 (terminal 1). |
| `python -m insurance_gpt…` fails with *No module named insurance_gpt* | Use `uv run …`, or activate the environment first (`.venv\Scripts\Activate.ps1`). |
| Server start takes long the first time | It's downloading the embedding model (~2.2 GB) because step 1.3 wasn't run. |
| `address already in use` on port 8000 | Another server is still running. Stop it, or start this one with `$env:IGPT_PORT = "8001"` and `ngrok http 8001`. |
| Answers mention other ERGO products or prices not in the documents | Web search is on in the chat: turn it off and start a new chat. |
| Answer in the wrong language | Start a new chat; the rule is "answer in the language of the question". |

## See what ChatGPT did (host)

Terminal 1 logs every tool call: the tool, the German search query ChatGPT sent, and which passages came
back, e.g.

```text
search_conditions query='Zahnersatz Sofort ZEZ Implantate' question='Zahlt Zahnersatz Sofort für Implantate?' doc_id=None -> ok ['ergo-zahn-broschuere-2022-07:broschuere:t12.r2@0.902', …]
```

The log contains the questions testers type. Don't use real personal or health data in the demo; log
redaction is still to be built (WBS 5.3).

## Stop

`Ctrl+C` in both terminals. Once the tunnel is down, the plugin URL no longer works.
