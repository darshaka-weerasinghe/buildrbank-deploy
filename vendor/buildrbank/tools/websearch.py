"""Web search tool — live external data via Tavily.

Degrades gracefully: a missing key or a timeout returns a typed 'unavailable'
result the agent can voice honestly, instead of crashing a conversation.
"""
from __future__ import annotations

from ..config import load as load_config
from ..observability import observe


@observe(as_type="tool")
def web_search(query: str, max_results: int = 3) -> dict:
    """Search the live web for information the bank cannot know internally:
    today's exchange rates, market news, current external facts."""
    cfg = load_config()
    if not cfg.tavily_api_key:
        return {"ok": False, "reason": "web search is not configured", "results": []}
    try:
        from tavily import TavilyClient
        resp = TavilyClient(api_key=cfg.tavily_api_key).search(
            query=query, max_results=max_results, search_depth="basic", timeout=15
        )
        results = [{"title": r.get("title", ""), "content": r.get("content", "")[:600],
                    "url": r.get("url", "")} for r in resp.get("results", [])]
        return {"ok": True, "results": results}
    except Exception as exc:                       # network, quota, timeout
        return {"ok": False, "reason": f"web search failed: {type(exc).__name__}", "results": []}
