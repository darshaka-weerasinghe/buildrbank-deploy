"""Long-term memory: semantic facts and episodic history (Week 6 tiers 2-3).

Read path: recall_* feed the context-load stage each turn.
Write path: record_episode / maybe_extract_fact run in the memory-write stage.
All recalls are per-user (the RPCs take match_user_id).
"""
from __future__ import annotations

from ..config import load as load_config
from ..db import db
from ..observability import observe
from ..rag import embed


@observe(as_type="retriever")
def recall_facts(user_id: str, query: str, k: int | None = None) -> list[dict]:
    cfg = load_config()
    try:
        rows = db().rpc("match_facts", {
            "query_embedding": embed(query),
            "match_count": k or cfg.recall_top_k,
            "match_user_id": user_id,
        }).execute()
        return rows.data or []
    except Exception:
        return []


@observe(as_type="retriever")
def recall_episodes(user_id: str, query: str, k: int | None = None) -> list[dict]:
    cfg = load_config()
    try:
        rows = db().rpc("match_episodes", {
            "query_embedding": embed(query),
            "match_count": k or cfg.recall_top_k,
            "match_user_id": user_id,
        }).execute()
        return rows.data or []
    except Exception:
        return []


@observe()
def record_episode(user_id: str, session_id: str, summary: str,
                   topic_tags: list[str] | None = None, turn_count: int = 0,
                   turns: list | None = None) -> None:
    """One row per notable event (an SOP completing, an escalation, a session).

    mem_episodes.turns is NOT NULL, so we always store the exchange (or an empty
    list). Failures are non-fatal: a memory hiccup must never break a live turn.
    """
    try:
        db().table("mem_episodes").insert({
            "user_id": user_id, "session_id": session_id, "summary": summary,
            "summary_embedding": embed(summary),
            "topic_tags": topic_tags or [], "turn_count": turn_count,
            "turns": turns or [],
        }).execute()
    except Exception as exc:
        # surface the reason on the trace instead of hiding it, but keep the turn alive
        try:
            from ..observability import get_client
            get_client().update_current_span(level="WARNING",
                                             status_message=f"episode write failed: {exc}")
        except Exception:
            pass
