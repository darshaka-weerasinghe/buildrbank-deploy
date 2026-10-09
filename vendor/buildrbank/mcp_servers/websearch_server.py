"""BuildrBank Websearch over MCP — thin wrapper over the shared web search tool."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

from buildrbank.tools import websearch

mcp = FastMCP("buildrbank-websearch")


@mcp.tool()
def web_search(query: str, max_results: int = 3) -> str:
    """Search the live web for information the bank cannot know internally:
    today's exchange rates, market news, current external facts."""
    return json.dumps(websearch.web_search(query, max_results=max_results), default=str)


if __name__ == "__main__":
    mcp.run()
