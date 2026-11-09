"""MCP server entry point (Streamable HTTP at /mcp)."""

import logging

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from insurance_gpt.config import get_settings
from insurance_gpt.tools import knowledge

INSTRUCTIONS = (
    "Answers customer questions about ERGO dental insurance using only the official documents in this "
    "knowledge base. Always search before answering, answer only from returned passages, cite them, and "
    "say when the documents don't cover a question. Information is illustrative; the contract is decisive."
)

settings = get_settings()
mcp = MCPServer("ERGO Insurance Terms", instructions=INSTRUCTIONS)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
for tool in (knowledge.list_documents, knowledge.search_conditions, knowledge.get_section):
    mcp.tool(annotations=READ_ONLY)(tool)


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    knowledge.get_retriever()  # load the model and index before accepting requests
    mcp.run(transport="streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
