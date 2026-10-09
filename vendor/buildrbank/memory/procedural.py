"""Procedural memory: the SOP store and matcher (Week 6 tier 4, made executable).

Discovery is semantic (match_procedures over description embeddings, seeded in
Week 6). Execution specs live in orchestration/sop_specs.py, versioned in code;
this module joins the two by SOP name.
"""
from __future__ import annotations

from ..config import load as load_config
from ..db import db
from ..observability import observe
from ..rag import embed


@observe(as_type="retriever")
def match_sops(query: str, k: int = 3) -> list[dict]:
    """Top-k candidate SOPs for a customer message, with similarity scores."""
    try:
        rows = db().rpc("match_procedures", {
            "query_embedding": embed(query), "match_count": k,
        }).execute()
        return rows.data or []
    except Exception:
        return []


def get_sop(name: str) -> dict | None:
    rows = db().table("mem_procedures").select("*").eq("name", name).execute()
    return rows.data[0] if rows.data else None


def pick_sop(query: str) -> dict:
    """Decide: confidently matched SOP, ambiguous top-2, or no match.

    Returns {"status": "match"|"ambiguous"|"none", ...} using the thresholds
    in config. The router turns 'ambiguous' into one clarifying question.
    """
    cfg = load_config()
    cands = match_sops(query, k=3)
    if not cands or cands[0].get("similarity", 0) < cfg.sop_match_floor:
        return {"status": "none", "candidates": cands}
    if (len(cands) > 1
            and cands[0]["similarity"] - cands[1]["similarity"] < cfg.sop_disambiguate_gap):
        return {"status": "ambiguous", "candidates": cands[:2]}
    return {"status": "match", "sop": cands[0], "candidates": cands}
