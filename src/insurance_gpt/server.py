"""MCP server entry point (Streamable HTTP at /mcp)."""

import logging

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from insurance_gpt.config import Settings, get_settings
from insurance_gpt.tools import knowledge

TEXTS = knowledge.TEXTS
INSTRUCTIONS = TEXTS.render(TEXTS.server_instructions)

settings = get_settings()
mcp = MCPServer("ERGO Insurance Terms", instructions=INSTRUCTIONS)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
# Tool descriptions live in tuning.yaml (answer.tools), next to the rules they repeat.
for tool in (knowledge.list_documents, knowledge.search_conditions, knowledge.get_section):
    description = TEXTS.render(getattr(TEXTS.tools, tool.__name__))
    mcp.tool(annotations=READ_ONLY, description=description)(tool)


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
