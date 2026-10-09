"""Supabase client for the live Week 6 backend. One client, lazily built."""
from __future__ import annotations

from supabase import Client, create_client

from . import config

_db: Client | None = None


def db() -> Client:
    global _db
    if _db is None:
        cfg = config.load()
        _db = create_client(cfg.supabase_url, cfg.supabase_key)
    return _db
