"""BuildrBank Knowledge over MCP — thin wrapper over the shared knowledge tool."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

from buildrbank.tools import knowledge

mcp = FastMCP("buildrbank-knowledge")


@mcp.tool()
def search_policy(query: str, top_k: int = 4) -> str:
    """Semantic search over the BuildrBank policy handbook: fees, rates,
    limits, timelines, account rules. Returns excerpts with similarity scores."""
    return json.dumps(knowledge.search_policy(query, top_k=top_k), default=str)


if __name__ == "__main__":
    mcp.run()
