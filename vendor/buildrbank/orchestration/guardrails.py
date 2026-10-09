"""Guardrails: gates, not routes.

context gate  — screens retrieved content (kb chunks, web results) before the
                model reads it. Injection arrives through documents too.
slot gate     — screens values the customer supplies into procedure slots.
output gate   — final PII / leak scan on every answer, every path.

Blocked material is dropped or redacted and the event is flagged on the trace
(level WARNING) so attacks are visible in the dashboard, never silent.
"""
from __future__ import annotations

import re

from ..observability import get_client, observe

_INJECTION = re.compile(
    r"(ignore (all |your |previous |prior )*(instructions|rules|prompts)"
    r"|disregard (the|your|all).{0,30}(instructions|rules)"
    r"|system prompt|you are now|act as (if|a|an)\b"
    r"|reveal.{0,30}(customer|account|password|key)"
    r"|list.{0,30}(customers|accounts)\b)",
    re.IGNORECASE,
)
_ACC = re.compile(r"ACC-\d{4,}")


def _flag(reason: str) -> None:
    try:
        get_client().update_current_span(level="WARNING", status_message=reason)
    except Exception:
        pass


@observe(as_type="guardrail")
def gate_context(chunks: list[dict], text_key: str = "content") -> list[dict]:
    """Drop retrieved items that carry instruction-shaped payloads."""
    clean = []
    for c in chunks:
        if _INJECTION.search(str(c.get(text_key, ""))):
            _flag(f"context gate: dropped poisoned item ({str(c.get(text_key))[:80]!r})")
        else:
            clean.append(c)
    return clean


@observe(as_type="guardrail")
def gate_slot(value: str) -> dict:
    """Screen a customer-supplied slot value. Injection through answers is real."""
    if _INJECTION.search(value or ""):
        _flag(f"slot gate: rejected injected slot value ({value[:80]!r})")
        return {"ok": False, "reason": "that answer contains instructions, not information"}
    return {"ok": True, "value": value.strip()}


@observe(as_type="guardrail")
def gate_output(text: str) -> str:
    """Redact anything account-shaped leaving the system, on every path."""
    if _ACC.search(text):
        _flag("output gate: redacted account number in answer")
        text = _ACC.sub("[account on file]", text)
    return text
