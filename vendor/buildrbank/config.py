"""Central configuration. Every constant lives here, exactly once.

Loads `Week 11/.env`, validates required keys with named errors, and exposes
a frozen Config object. Nothing else in the package reads os.environ directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

WEEK_DIR = Path(__file__).resolve().parent.parent      # .../Week 11
DATA_DIR = WEEK_DIR / "data"                            # sqlite checkpoints etc.

REQUIRED_KEYS = (
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL", "SUPABASE_KEY",
    "QWEN_API_KEY",
    "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
)
OPTIONAL_KEYS = ("TAVILY_API_KEY",)                     # websearch degrades gracefully


@dataclass(frozen=True)
class Config:
    # models — one registry, imported everywhere
    answer_model: str = "claude-sonnet-4-6"             # customer-facing voice
    router_model: str = "claude-haiku-4-5"              # classification, temp 0
    judge_model: str = "claude-haiku-4-5"               # grading, temp 0
    embed_model: str = "text-embedding-v4"              # Qwen, matches Week 6 index
    embed_dim: int = 1536
    embed_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    # observability
    environment: str = field(default_factory=lambda: os.environ.get("BB_ENV", "week11"))

    # behaviour thresholds
    sop_match_floor: float = 0.30       # below this, no SOP is confidently matched
    sop_disambiguate_gap: float = 0.06  # top-2 closer than this -> ask a clarifying question
    slot_retry_limit: int = 2           # failed re-asks before polite escalation
    procedure_stack_depth: int = 2      # parked + active; a third preempt asks the customer
    recall_top_k: int = 3               # episodic/semantic memories loaded per turn
    rag_top_k: int = 4                  # kb chunks per policy answer

    # secrets (populated by load())
    anthropic_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    qwen_api_key: str = ""
    tavily_api_key: str = ""


_config: Config | None = None


def load() -> Config:
    """Load and validate configuration. Fails fast with the names of missing keys."""
    global _config
    if _config is not None:
        return _config

    load_dotenv(WEEK_DIR / ".env")
    missing = [k for k in REQUIRED_KEYS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing keys in {WEEK_DIR / '.env'}: {', '.join(missing)}. "
            "Copy .env.example and fill them in."
        )

    DATA_DIR.mkdir(exist_ok=True)
    _config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_key=os.environ["SUPABASE_KEY"],
        qwen_api_key=os.environ["QWEN_API_KEY"],
        tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
    )
    return _config
