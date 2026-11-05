"""MCP server entry point (Streamable HTTP at /mcp).

Only `list_documents` exists so far; search_conditions, get_section and show_citation follow in WBS 3.2/3.3.
"""

import logging

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from insurance_gpt.config import get_settings
from insurance_gpt.sources import load_manifest

INSTRUCTIONS = (
    "Answers questions about ERGO insurance terms and conditions using only the official documents "
    "in this knowledge base. Information is illustrative; the insurance contract is decisive."
)

settings = get_settings()
mcp = MCPServer("ERGO Insurance Terms", instructions=INSTRUCTIONS)


class DocumentInfo(BaseModel):
    doc_id: str
    title: str
    issuer: str
    products: list[str]
    doc_type: str
    language: str
    edition: str
    url: str


class DocumentList(BaseModel):
    documents: list[DocumentInfo]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def list_documents() -> DocumentList:
    """List the insurance documents this plugin can answer from (products, document type, edition).

    Use it to tell the user what is covered, and to recognise questions outside that scope.
    """
    manifest = load_manifest(settings.sources_file)
    return DocumentList(
        documents=[
            DocumentInfo(**d.model_dump(mode="json", include=set(DocumentInfo.model_fields)))
            for d in manifest.documents
        ]
    )


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    mcp.run(transport="streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
