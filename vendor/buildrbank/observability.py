"""Langfuse factory: masking, environment, sessions, flush.

One client for the whole system. Everything the model sees or says is traced;
account numbers are masked client-side before anything leaves the machine.
"""
from __future__ import annotations

import re
from contextlib import contextmanager

from langfuse import Langfuse, get_client, observe, propagate_attributes  # noqa: F401 (re-exported)

from . import config

# Load .env at import time so @observe works even when a tool is used standalone
# (e.g. an MCP server importing tools/ directly, before any client is built).
from dotenv import load_dotenv as _ld
_ld(config.WEEK_DIR / ".env")

_ACC_RE = re.compile(r"ACC-\d{4,}")


def mask_pii(data):
    """Client-side mask: runs on every traced input/output before upload."""
    if isinstance(data, str):
        return _ACC_RE.sub("[REDACTED-ACCOUNT]", data)
    if isinstance(data, dict):
        return {k: mask_pii(v) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_pii(v) for v in data]
    return data


_lf: Langfuse | None = None


def lf() -> Langfuse:
    """The process-wide Langfuse client (also initialises the @observe client)."""
    global _lf
    if _lf is None:
        cfg = config.load()
        _lf = Langfuse(mask=mask_pii, environment=cfg.environment)
    return _lf


@contextmanager
def conversation(user_id: str, thread_id: str, tags: list[str] | None = None):
    """Wrap one turn: every trace inside carries the session and user.

    thread_id doubles as the Langfuse session_id, so a multi-turn procedure
    reads as one session in the dashboard.
    """
    lf()  # ensure client exists before any @observe fires
    with propagate_attributes(user_id=user_id, session_id=thread_id, tags=tags or []):
        yield


def record_generation(model: str, usage) -> None:
    """Attach model + token usage to the current @observe(as_type='generation') span."""
    get_client().update_current_generation(
        model=model,
        usage_details={"input": usage.input_tokens, "output": usage.output_tokens},
    )


def flush() -> None:
    lf().flush()
