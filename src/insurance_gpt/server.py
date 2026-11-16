"""MCP server entry point (Streamable HTTP at /mcp)."""

import logging
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from insurance_gpt.config import Settings, get_settings
from insurance_gpt.tools import citation, knowledge

TEXTS = knowledge.TEXTS
INSTRUCTIONS = TEXTS.render(TEXTS.server_instructions)

settings = get_settings()
mcp = MCPServer("ERGO Insurance Terms", instructions=INSTRUCTIONS)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
# The citation card: show_citation's result is rendered by this HTML resource (MCP Apps; ChatGPT alias).
WIDGET_MIME = "text/html;profile=mcp-app"
CITATION_META = {
    "ui": {"resourceUri": citation.WIDGET_URI},
    "openai/outputTemplate": citation.WIDGET_URI,
    "openai/toolInvocation/invoking": "Checking the quote…",
    "openai/toolInvocation/invoked": "Source shown.",
}

# Tool descriptions live in tuning.yaml (answer.tools), next to the rules they repeat.
for tool, meta in (
    (knowledge.list_documents, None),
    (knowledge.search_conditions, None),
    (knowledge.get_section, None),
    (citation.show_citation, CITATION_META),
):
    description = TEXTS.render(getattr(TEXTS.tools, tool.__name__))
    mcp.tool(annotations=READ_ONLY, description=description, meta=meta)(tool)


@mcp.resource(
    citation.WIDGET_URI,
    name="citation-card",
    description="Verified quote with its source: document, section, page and a link to the PDF.",
    mime_type=WIDGET_MIME,
    # Self-contained HTML: no external scripts, styles or API calls, so the CSP allows nothing extra.
    meta={"ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}}},
)
def citation_widget() -> str:
    return (Path(__file__).parent / "widgets" / "citation.html").read_text(encoding="utf-8")


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """Accept localhost plus the configured public hostnames; reject other Host headers."""
    hosts = settings.public_host_list
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "127.0.0.1", "localhost", *hosts],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "https://chatgpt.com",
            *(f"https://{h}" for h in hosts),
        ],
    )


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    knowledge.get_retriever()  # load the model and index before accepting requests
    mcp.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        transport_security=transport_security(settings),
    )


if __name__ == "__main__":
    main()
