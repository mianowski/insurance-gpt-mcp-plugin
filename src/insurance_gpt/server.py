"""MCP server entry point (Streamable HTTP at /mcp)."""

import logging

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from insurance_gpt.config import Settings, get_settings
from insurance_gpt.tools import knowledge

INSTRUCTIONS = (
    "Answers customer questions about ERGO dental supplementary insurance (tariff ZEK, Dental-Schutz 100) from "
    "the official documents in this knowledge base. Always call search_conditions before answering such a "
    "question, and use these documents instead of web search. " + knowledge.ANSWER_RULES
)

settings = get_settings()
mcp = MCPServer("ERGO Insurance Terms", instructions=INSTRUCTIONS)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
for tool in (knowledge.list_documents, knowledge.search_conditions, knowledge.get_section):
    mcp.tool(annotations=READ_ONLY)(tool)


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
