"""
The front door.

The agent is a Python library. You can call it from a script, but you cannot
visit it in a browser. This file is the missing piece: it puts an HTTP address
in front of the one function that matters.

    agent.turn(user_id, thread_id, message)  ->  reply

Three addresses:

    GET  /         the chat page
    POST /chat     send a message, get a reply
    GET  /health   is everything wired up?

That is the entire deployment. The agent itself is untouched.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

# ---------------------------------------------------------------------------
# THIS MUST COME FIRST.
# settings.configure() hands our settings to the agent package. The package
# reads some of them the moment it is imported, so the next import down has
# to happen after this line, not before it.
# ---------------------------------------------------------------------------
from app import settings

CONFIG = settings.configure()

# Only now is it safe to import the agent.
from buildrbank.app import build_app                            # noqa: E402
from buildrbank.orchestration.sop_specs import SOP_SPECS        # noqa: E402

from fastapi import FastAPI, HTTPException    # noqa: E402
from fastapi.responses import HTMLResponse    # noqa: E402
from pydantic import BaseModel, Field         # noqa: E402


PAGE = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")

# Built once when the server starts, and reused for every message.
# Building one per request would open a new database connection every time
# and never close it - the server would run out of file handles.
AGENT = None


@asynccontextmanager
async def lifespan(api: FastAPI):
    """Runs once at startup, and once at shutdown."""
    global AGENT
    print("-" * 60)
    for k, v in settings.summary(CONFIG).items():
        print(f"  {k:<14} {v}")
    print("-" * 60)

    AGENT = build_app()
    print("  agent ready -> http://localhost:8000")
    print("-" * 60)

    yield

    # Shutdown: push any recordings still waiting in the background.
    if AGENT is not None:
        AGENT.close()


api = FastAPI(title="BuildrBank", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # Who is speaking. The seeded database knows these three emails:
    #   isuru@example.com, nehara@example.com, yasiru@example.com
    user_id: str = "demo-user"
    email: str | None = None
    # Which conversation this belongs to. Send the same thread_id back each
    # time and the agent remembers; send a new one and it starts fresh.
    thread_id: str | None = None


class ChatReply(BaseModel):
    reply: str
    thread_id: str
    route: str = ""
    procedures: list = []
    # What happened inside the agent this turn: a procedure started, got
    # parked, a slot was filled. The console on the right of the page
    # renders these so you can watch the machinery work.
    events: list = []
    elapsed_ms: int = 0


@api.get("/", response_class=HTMLResponse)
def home() -> str:
    """The chat page."""
    return PAGE


@api.post("/chat", response_model=ChatReply)
def chat(body: ChatRequest) -> ChatReply:
    """One message in, one reply out.

    Note this is `def`, not `async def`, and that is deliberate. The agent
    does slow, ordinary, blocking work - it waits on models and on the
    database. FastAPI runs a plain `def` on a background thread, so one slow
    message does not freeze everyone else's. An `async def` here would.
    """
    thread_id = body.thread_id or f"web-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    try:
        result = AGENT.turn(
            user_id=body.user_id,
            thread_id=thread_id,
            text=body.message,
            email=body.email,
        )
    except Exception as exc:
        # The agent crashes a turn if the database or a model is unreachable.
        # Better to say so plainly than to return a blank page.
        raise HTTPException(
            status_code=502,
            detail=f"The agent could not finish that turn: {type(exc).__name__}: {exc}",
        ) from exc

    return ChatReply(
        reply=result.reply,
        thread_id=thread_id,
        route=result.route,
        procedures=result.procedures,
        events=result.events,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


@api.get("/sops")
def sops() -> dict:
    """The procedures this agent can run, and the steps inside each one.

    Read straight out of the agent's own definitions, so the page can show
    a real step list instead of a guess. Nothing here is written by us.
    """
    out = {}
    for name, spec in SOP_SPECS.items():
        out[name] = {
            "title": spec.get("title", name),
            "steps": [
                {"kind": step.get("kind", ""),
                 "slot": step.get("slot") or step.get("save_as") or "",
                 "tool": step.get("tool", "")}
                for step in spec.get("steps", [])
            ],
        }
    return out


@api.get("/health")
def health() -> dict:
    """What this server is configured to do. Safe to show - no keys in here."""
    return {"status": "ok" if AGENT is not None else "starting",
            **settings.summary(CONFIG)}
