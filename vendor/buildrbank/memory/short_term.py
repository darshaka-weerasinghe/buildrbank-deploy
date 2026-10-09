"""Short-term memory: the conversation itself.

Two layers, deliberately:
- The LangGraph checkpointer (sqlite, keyed by thread_id) persists graph state
  between turns and across process restarts: turns, the procedure stack, slots.
- st_turns in Supabase mirrors the transcript for inspection and for building
  episodic memories at session end (the Week 6 pattern, kept).
"""
from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from ..config import DATA_DIR
from ..db import db

_CHECKPOINT_PATH = DATA_DIR / "checkpoints.sqlite"


def checkpointer() -> SqliteSaver:
    conn = sqlite3.connect(str(_CHECKPOINT_PATH), check_same_thread=False)
    return SqliteSaver(conn)


def append_turns(user_id: str, session_id: str, user_text: str, bot_text: str) -> None:
    """Mirror the exchange into st_turns (best effort — never breaks a turn)."""
    try:
        db().table("st_turns").insert([
            {"user_id": user_id, "session_id": session_id, "role": "user", "content": user_text},
            {"user_id": user_id, "session_id": session_id, "role": "assistant", "content": bot_text},
        ]).execute()
    except Exception:
        pass
