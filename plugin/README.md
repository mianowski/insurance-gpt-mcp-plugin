# ERGO Dental plugin package

The packaged ChatGPT plugin: our MCP server plus the skill that tells ChatGPT how to run the conversation
(WBS 4.1). Format: [OpenAI plugin docs](https://developers.openai.com/plugins/build/plugins).

```text
plugin/
├── plugin.json                         manifest: name, version, display texts
├── mcp.json                            the MCP server URL (…/mcp)
└── skills/ergo-dental-coverage/
    ├── SKILL.md                        conversation workflow: steps, tool order, follow-ups, limits
    ├── agents/openai.yaml              the skill's MCP tool dependency (same URL)
    └── references/conversation-script.md   expected flow per scenario (WBS 1.2)
```

## Where the conversation rules live

| Where | Used by | Contains |
| --- | --- | --- |
| `tuning.yaml` → `answer` (server instructions, tool descriptions, rules (0)–(8)) | every MCP client, including the custom MCP plugin added on chatgpt.com | the hard rules: sources only, verbatim quote, `show_citation`, scope, personal data, follow-ups |
| `skills/ergo-dental-coverage/SKILL.md` | ChatGPT when the plugin is installed as a package | the same rules as a step-by-step workflow, plus answer format and examples |

The server rules alone already give the behaviour in the conversation script; the skill makes it more
consistent. When you change a rule, change it in both places.

## Install

Set your server URL first: replace `https://your-name.ngrok-free.app/mcp` in `mcp.json` and
`skills/ergo-dental-coverage/agents/openai.yaml`.

**Option 1: chatgpt.com, server only (what we use now).** Add the custom MCP server as described in
[`docs/CHATGPT_PLUGIN_SETUP.md`](../docs/CHATGPT_PLUGIN_SETUP.md). The rules from `tuning.yaml` apply; the
skill file isn't loaded.

**Option 2: ChatGPT desktop app, full package (local marketplace).**

1. Copy the `plugin` folder to `%USERPROFILE%\.codex\plugins\ergo-dental`.
2. Create or extend `%USERPROFILE%\.agents\plugins\marketplace.json`:

   ```json
   {
     "name": "personal",
     "plugins": [
       {
         "name": "ergo-dental",
         "source": { "source": "local", "path": "./.codex/plugins/ergo-dental" },
         "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
         "category": "Productivity"
       }
     ]
   }
   ```

3. Restart the ChatGPT desktop app; the plugin appears in the Plugins Directory. Install it there.

**Option 3: share in a workspace.** A workspace admin can publish a personal plugin to selected roles:
ChatGPT Plugins → **Personal** → ⋯ → **Publish**.

The menus follow OpenAI's documentation of 2026-11; check it if they differ.

## Test

Run the scenarios in `references/conversation-script.md`, each in a new chat. For each: did ChatGPT call
the tools in the listed order, answer in the question's language, quote verbatim, show one card, and stay
within the documents? The server log (`.data/server.log` or the server terminal) shows every tool call.
