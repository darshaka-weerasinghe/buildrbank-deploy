"""Knowledge tool — vector retrieval over the BuildrBank handbook."""
from __future__ import annotations

from ..observability import observe
from ..rag import search_chunks

_BANK_SOURCE = "bank_handbook.txt"     # kb_chunks is shared with other labs — always filter


@observe(as_type="tool")
def search_policy(query: str, top_k: int = 4) -> list[dict]:
    """Semantic search over the BuildrBank policy handbook. Use for questions about
    fees, rates, limits, timelines, and account rules. Returns policy excerpts
    with similarity scores."""
    hits = search_chunks(query, k=12)
    return [h for h in hits if h.get("source") == _BANK_SOURCE][:top_k]
