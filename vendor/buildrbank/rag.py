"""Embeddings + pgvector retrieval. The one kitchen, three diners:
tools/knowledge.py, memory recall, and the guardrail context gate all use this.
"""
from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from . import config
from .db import db
from .observability import observe


@lru_cache(maxsize=1)
def _embed_client() -> OpenAI:
    cfg = config.load()
    return OpenAI(api_key=cfg.qwen_api_key, base_url=cfg.embed_base_url)


@observe(as_type="embedding")
def embed(text: str) -> list[float]:
    """Qwen text-embedding-v4 at 1536 dims — the exact space Week 6 indexed."""
    cfg = config.load()
    resp = _embed_client().embeddings.create(
        model=cfg.embed_model, input=text, dimensions=cfg.embed_dim
    )
    return resp.data[0].embedding


@observe(as_type="retriever")
def search_chunks(query: str, k: int | None = None) -> list[dict]:
    """Semantic search over kb_chunks via the Week 6 match_kb_chunks RPC."""
    cfg = config.load()
    rows = db().rpc("match_kb_chunks", {
        "query_embedding": embed(query),
        "match_count": k or cfg.rag_top_k,
    }).execute()
    return rows.data or []
