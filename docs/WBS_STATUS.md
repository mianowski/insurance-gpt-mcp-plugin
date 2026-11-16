# WBS status — ChatGPT Plugin for Insurance Dental PoC

Status as of **2026-11-16**, against the team plan in `outsource/excel_plan.jpeg`.
Type: F = functionality development, C = configuration/content, V = validation/delivery.

Legend: ✅ done · 🟡 partly done · ⬜ not started · ➖ struck out in the plan

## Summary

| Status | Count | IDs |
| --- | --- | --- |
| ✅ Done | 7 | 1.4, 2.2, 3.1, 3.2, 3.3, 4.6, 5.2 (+ 1.1, 1.3 done before being struck out) |
| 🟡 Partly done | 9 | 1.2, 2.1, 4.1, 4.5, 5.1, 6.1, 6.2, 6.3, 6.5 |
| ⬜ Not started | 8 | 3.4, 3.5, 3.6, 4.2, 4.3, 4.4, 4.7, 5.3 |
| ➖ Struck out | 4 | 1.1, 1.3, 2.3, 6.4 |

The **knowledge path works end to end**: a customer asks in ChatGPT (DE or EN) and gets an answer with a
verbatim German quote, document, section and page. The **tariff path** (catalogue, matching, premium
calculation, configurator UI, admin panel) has not been started. It depends on 2.3, the machine-readable
tariff rules, which is struck out in the plan.

## Status per task

### 1. Scope and design

| ID | Task | Type | Deliverable | Status | Where we are |
| --- | --- | --- | --- | --- | --- |
| 1.1 | Define PoC scope, target users, market, language, and exclusions | C | Agreed scope and demo boundaries | ➖ ✅ | Agreed: public ERGO dental documents only, German and English, private demo hosting, moves to ERGO infrastructure if approved. |
| 1.2 | Define conversation scenarios and acceptance criteria | C | Happy paths, edge cases, and expected outcomes | 🟡 | `tests/eval/questions.yaml`: 16 in-scope DE/EN questions with the expected passages, plus 4 out-of-scope ones. Conversation script with 12 scenarios and their expected tool calls and answers, including follow-ups, clarifying questions, out-of-scope, personal data and prompt injection: `plugin/skills/ergo-dental-coverage/references/conversation-script.md`. **Missing:** acceptance criteria agreed with the team; running the new scenarios in ChatGPT. |
| 1.3 | Confirm workspace permissions and hosting/connectivity feasibility | C | Custom app can connect to a minimal MCP endpoint | ➖ ✅ | Done: the server is registered as a custom MCP plugin in ChatGPT (Work chat, via ngrok) and was tested in two rounds. |
| 1.4 | Create basic architecture design | C | — | ✅ | `docs/ARCHITECTURE.md`: decisions D1–D9, components, request flow, environments, security, open questions. |

### 2. Content

| ID | Task | Type | Deliverable | Status | Where we are |
| --- | --- | --- | --- | --- | --- |
| 2.1 | Collect and review product descriptions, conditions, FAQs, and pricing inputs from the ERGO DE website; define tariff combinations, matching rules, and pricing tables | C | Approved source pack or explicitly labelled demo pack; machine-readable rules and reference examples | 🟡 | **Source pack:** Grzegorz's 2 public PDFs (tariff overview 08/2024, product brochure with premiums as of 01.07.2022), listed in `knowledge/sources.yaml` with URL, edition and sha256, and labelled as public. **Missing:** team approval of the pack (are the 2022 premiums current enough?), FAQs, and machine-readable tariff combinations, matching rules and pricing tables. |
| 2.2 | Structure product knowledge and source references | C | Versioned knowledge files with section-level references | ✅ | `knowledge/chunks/*.jsonl` (152 passages) is committed and versioned. Each passage carries document, chapter, section, page and a PDF link. Tariff tables are split into one passage per row with all tariffs. A test fails if the committed chunks differ from a fresh build. |
| 2.3 | Define tariff combinations, matching rules, and pricing tables | C | Machine-readable rules and reference examples | ➖ ⬜ | Struck out in the plan, not started. The premium tables are only available as searchable text. 3.4–3.6 would need this. |

### 3. Backend

| ID | Task | Type | Deliverable | Status | Where we are |
| --- | --- | --- | --- | --- | --- |
| 3.1 | Set up repository, runtime, dependencies, and environment configuration | C | Reproducible local development setup | ✅ | uv + Python 3.12 + lock file, ruff, pytest, GitHub Actions CI, `.env.example`, Dockerfile (Docker build not tested yet). All quality settings are in one file, `tuning.yaml`. |
| 3.2 | Implement MCP server and tool schemas | F | Endpoint initializes and advertises the intended tools | ✅ | Python MCP SDK 2.x over Streamable HTTP at `/mcp`. Tools: `list_documents`, `search_conditions`, `get_section`, all read-only, with typed input and output schemas. |
| 3.3 | Implement knowledge retrieval | F | Questions return relevant passages and source metadata | ✅ | Hybrid search: multilingual-e5 for meaning plus BM25 for exact German terms, combined into one ranking. A relevance threshold filters out unrelated questions. Eval: hit@5 1.00, hit@1 0.88, MRR 0.93. |
| 3.4 | Implement tariff catalogue and combination validation | F | Valid options returned; invalid combinations rejected | ⬜ | Not started; needs 2.3. |
| 3.5 | Implement needs-to-option matching | F | Deterministic results with reasons and limitations | ⬜ | Not started; needs 2.3. |
| 3.6 | Implement illustrative premium calculation | F | Correct initial/subsequent prices for reference cases | ⬜ | Not started. Until then, premium questions are answered by quoting the brochure's premium table row (e.g. DS100 for age 31–40, first 6 months at half price), not calculated. |

### 4. ChatGPT experience

| ID | Task | Type | Deliverable | Status | Where we are |
| --- | --- | --- | --- | --- | --- |
| 4.1 | Configure tool descriptions (skills) and conversation guidance (script) | C | Appropriate tool use, follow-up questions, and fallback behavior | 🟡 | Rules (0)–(8) in `tuning.yaml`, used on chatgpt.com today: answer in the question's language, use only the passages, quote verbatim and show the card, decline out-of-scope questions, ask which tariff when the answer differs by tariff, ask for the age for premiums, search again for follow-ups, protect personal data, add the disclaimer. **Packaged skill:** `plugin/` (manifest, MCP server, skill `ergo-dental-coverage` with workflow and conversation script). **Missing:** running the new scenarios in ChatGPT; installing the full package (needs the ChatGPT desktop app or workspace publishing). |
| 4.2 | Develop embedded tariff configurator | F | Selectable coverage groups, comparison, price, and disclosures | ⬜ | Not started; needs 3.4–3.6. |
| 4.3 | Implement chat/UI state synchronization | F | Chat and configurator use the same current selection | ⬜ | Not started; needs 4.2. |
| 4.4 | Implement adviser link or simulated handoff | F/C | Button works without creating a real lead | ⬜ | Not started. Today the answer only tells the user in text to contact ERGO customer service or an adviser. |
| 4.5 | Implement loading, missing-data, invalid-input, and service-error states | F | Recoverable errors with understandable messages back to the LLM | 🟡 | Unknown document or passage ids return an error ChatGPT can recover from. Nothing relevant found returns `no_relevant_passage` with guidance. The model is loaded before the server accepts requests. **Missing:** handling of internal errors (e.g. index failure). The citation card shows a loading text until its data arrives; a quote that can't be verified returns an error with the closest source text, so ChatGPT can correct it. |
| 4.6 | Handling of out-of-scope input requests | F | LLM returns with out-of-scope info | ✅ | Unrelated questions (weather, claim status) are rejected by the relevance threshold. Other insurance products (car, household) are declined by ChatGPT, following the rules and the `scope_note`. Covered by the eval and checked in the ChatGPT test. |
| 4.7 | Administration panel within MCP for an admin user to adjust tariffs or specific information | F | Admin panel for marketing user | ⬜ | Not started. Content changes today: edit `knowledge/sources.yaml` or `tuning.yaml`, rebuild, restart. That's developer-only. |

### 5. Deployment and security

| ID | Task | Type | Deliverable | Status | Where we are |
| --- | --- | --- | --- | --- | --- |
| 5.1 | Configure hosting, HTTPS, endpoint access, and secrets handling | C | Approved, reachable test deployment | 🟡 | HTTPS via an ngrok tunnel from the host's machine. A hostname allowlist protects against DNS rebinding. Setup in `docs/CHATGPT_PLUGIN_SETUP.md`. **Missing:** a stable deployment (static domain or EU VM), approval, and secrets handling (no secrets used yet). |
| 5.2 | Register the custom app and configure UI resources/security policies | C | Tools and embedded UI work inside ChatGPT | ✅ | The tools work inside ChatGPT as a custom plugin. **Citation card built:** `show_citation` checks the quote against the source on the server and renders a card with the quote highlighted, the citation and a PDF link. The UI resource declares a CSP that allows no outside domains. Works in ChatGPT (2026-11-16): ChatGPT searched, then called `show_citation` with the right passage; the quote was verified on the first try and the card with the PDF button appeared. |
| 5.3 | Configure access restrictions, session expiry, and redacted logging | C | Test access controlled; unnecessary personal data not retained | ⬜ | Not started. There's no authentication: anyone with the URL can call the server. The logs keep testers' questions without redaction. Mitigation for now: run the tunnel only while testing, and use no real personal data. |

### 6. Validation and delivery

| ID | Task | Type | Deliverable | Status | Where we are |
| --- | --- | --- | --- | --- | --- |
| 6.1 | Unit-test pricing, matching, combinations, and knowledge retrieval | V | Reference cases pass | 🟡 | Knowledge retrieval: 25 tests, including table parsing on the real PDFs and the retrieval eval against the targets in `tuning.yaml`, all running in CI. Pricing, matching and combinations can't be tested yet (3.4–3.6). |
| 6.2 | Test complete journeys, UI/chat consistency, and session isolation | V | End-to-end scenarios pass | 🟡 | Two manual test rounds in ChatGPT: the second had correct answers, quotes and fallbacks, and the language rule was fixed after it. **Missing:** a repeatable test of full ChatGPT answers (does the answer use the right language, the right quote, stay in scope?), UI consistency, session isolation. |
| 6.3 | Test unsupported claims, prompt injection, and sensitive-data handling | V | Defined safety and fallback cases pass | 🟡 | Out-of-scope and unsupported questions are tested. **Missing:** prompt-injection and sensitive-data test cases. |
| 6.4 | Conduct product-owner review and user acceptance testing | V | Product content and demonstrated behavior accepted | ➖ | Struck out in the plan. |
| 6.5 | Prepare demo script, deployment instructions, and known-limitations list | V | Repeatable demonstration and handover package | 🟡 | Demo script with checklist, 7 steps, presenter notes and fixes: `docs/DEMO_SCRIPT.md`. Deployment instructions: `docs/CHATGPT_PLUGIN_SETUP.md`. Known limitations: `docs/ARCHITECTURE.md`. **Missing:** a dry run of the demo script in ChatGPT; a handover package. |

## Suggested next steps

1. **Decide whether the tariff path is in scope for the demo** (2.3 is struck out, but 3.4–3.6, 4.2, 4.3 and 4.7
   depend on it). If not, mark those rows out of scope too.
2. **Confirm the source pack (2.1):** are the brochure premiums (as of 01.07.2022) acceptable for the demo?
3. ~~Citation card + server-side quote check (5.2)~~ done, works in ChatGPT.
4. ~~Packaged skill and conversation script (4.1), demo script (6.5)~~ written; next: dry-run them in ChatGPT.
5. **Stable hosting with access control and redacted logs (5.1, 5.3)** before sharing the URL beyond the team.
6. **Grow the scenario set (1.2, 6.2, 6.3):** multi-turn, prompt injection, sensitive data; add an
   automated check of full ChatGPT answers.
