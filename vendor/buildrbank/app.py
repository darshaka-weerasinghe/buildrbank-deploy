"""The front door. Phase 2 wraps this in FastAPI + Docker, unchanged.

    from buildrbank.app import build_app
    app = build_app()
    print(app.turn("yousuf", "support-001", "Where is WIRE-30621?").reply)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .memory.short_term import checkpointer
from .observability import conversation, flush, observe
from .orchestration.graph import build_graph


@dataclass
class TurnResult:
    reply: str
    route: str
    procedures: list = field(default_factory=list)
    events: list = field(default_factory=list)


class BuildrBank:
    def __init__(self):
        self.graph = build_graph(checkpointer=checkpointer())

    @observe(name="bb-turn")
    def _invoke(self, payload: dict, thread_id: str) -> dict:
        return self.graph.invoke(payload, config={"configurable": {"thread_id": thread_id}})

    def turn(self, user_id: str, thread_id: str, text: str,
             email: str | None = None, tags: list[str] | None = None) -> TurnResult:
        """One customer turn. thread_id is both memory key and Langfuse session."""
        with conversation(user_id=user_id, thread_id=thread_id, tags=tags):
            payload = {"user_id": user_id, "thread_id": thread_id, "message": text}
            if email:
                payload["user_email"] = email
            out = self._invoke(payload, thread_id)
        return TurnResult(
            reply=out.get("reply", ""),
            route=out.get("route", ""),
            procedures=[{k: f.get(k) for k in ("sop", "status", "idx", "slots")}
                        for f in out.get("procedures") or []],
            events=out.get("events") or [],
        )

    def close(self):
        flush()


def build_app() -> BuildrBank:
    return BuildrBank()
