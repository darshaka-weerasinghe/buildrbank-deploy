"""The procedure runner: a deterministic SOP engine with an LLM voice.

The engine owns WHERE we are (active SOP, step index, slots, retries).
The LLM owns HOW it sounds (phrasing questions, extracting answers).
The model never decides to skip a step.

Per turn the runner triages the customer message five ways:
  slot_answer   fill the pending slot, advance the engine
  sop_question  answer from the SOP itself (the spec is a readable document)
  side_question answer inline via the shared toolbox, then re-anchor
  new_intent    hand the turn back to the router (frame gets parked)
  exit          close the procedure politely

Frames are plain dicts living in graph state, persisted by the checkpointer,
so procedures survive restarts and can be parked and resumed with slots intact.
Action results are re-fetched on resume: slots persist, world-state refreshes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import anthropic

from ..config import load as load_config
from ..observability import observe, record_generation
from ..tools import crm, knowledge, websearch
from . import prompts
from .guardrails import gate_slot
from .sop_specs import SOP_SPECS

TOOL_REGISTRY = {
    "crm.get_wire_status": crm.get_wire_status,
    "crm.get_customer_profile": crm.get_customer_profile,
    "crm.find_transaction": crm.find_transaction,
    "knowledge.search_policy": knowledge.search_policy,
    "websearch.web_search": websearch.web_search,
}

VALIDATORS = {
    "wire_ref": re.compile(r"\b(WIRE-\d{3,})\b", re.I),
    "any_ref":  re.compile(r"\b([A-Z]{2,6}-\d{3,})\b", re.I),
    "last4":    re.compile(r"\b(\d{4})\b"),
    "amount":   re.compile(r"\b([\d][\d,]{4,})\b"),
    "months":   re.compile(r"\b(\d{1,2})\b"),
    "yes_no":   re.compile(r"\b(yes|yeah|ok|okay|proceed|go ahead|confirm|do it|no|don'?t|stop|cancel)\b", re.I),
    "free":     re.compile(r"(\S.{2,})", re.S),
}

_YES = re.compile(r"\b(yes|yeah|yep|ok|okay|proceed|go ahead|confirm|do it|sure|please do)\b", re.I)
_NO = re.compile(r"\b(no|nope|don'?t|do not|stop|cancel|never ?mind|not now|forget it)\b", re.I)

# only these patterns are specific enough to harvest from an unrelated message.
# months (\d{1,2}) and last4 (\d{4}) match stray digits, so they are collected only
# when explicitly asked, never opportunistically.
HARVEST_SAFE = {"wire_ref", "any_ref", "amount"}

# a customer pushing the current action along, not asking a factual question
_URGING = re.compile(r"\b(block|freeze|cancel|recall|dispute|do it|go ahead|right away|"
                     r"immediately|now|hurry|asap|quick(?:ly)?|please just|urgent)\b", re.I)
_ASKING = re.compile(r"\b(how much|how long|how many|what(?:'?s| is| are| does| will| happens)"
                     r"|do you charge|is there a (?:fee|charge|cost|penalty))\b", re.I)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=load_config().anthropic_api_key, max_retries=5)


# ---------------------------------------------------------------- frames

def new_frame(sop_name: str) -> dict:
    spec = SOP_SPECS[sop_name]
    return {"sop": sop_name, "title": spec["title"], "idx": 0, "slots": {},
            "saved": {}, "notes": [], "retries": {}, "pending": None,
            "status": "active", "summary": ""}


def resolve(expr, frame: dict, ctx: dict):
    """Resolve "$path" values from slots, saved results, or customer context."""
    if not isinstance(expr, str) or not expr.startswith("$"):
        return expr
    path = expr[1:].split(".")
    if path[0] == "ctx":
        node = ctx
        path = path[1:]
    elif path[0] in frame["slots"]:
        node = frame["slots"]
    else:
        node = frame["saved"]
    for part in path:
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


def _eval_branch(on: str, frame: dict, ctx: dict):
    m = re.match(r"days_since\((\$[\w.]+)\)\s*<=\s*(\d+)", on)
    if m:
        raw = resolve(m.group(1), frame, ctx)
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - ts).days
            return str(days <= int(m.group(2)))
        except Exception:
            return "False"
    return str(resolve(on, frame, ctx))


# ---------------------------------------------------------------- engine

@observe(name="sop_advance")
def advance(frame: dict, ctx: dict) -> dict:
    """Run steps until the SOP needs the customer, escalates, or closes."""
    steps = SOP_SPECS[frame["sop"]]["steps"]
    while frame["idx"] < len(steps) and frame["status"] == "active":
        step = steps[frame["idx"]]
        kind = step["kind"]

        if kind in ("collect", "confirm"):
            if step["slot"] in frame["slots"]:
                frame["idx"] += 1
                continue
            frame["pending"] = {"slot": step["slot"], "ask_for": step["ask_for"],
                                "validate": step.get("validate", "free"), "kind": kind}
            return frame

        if kind == "note":
            frame["notes"].append(step["note"])
            frame["idx"] += 1

        elif kind == "action":
            args = {k: resolve(v, frame, ctx) for k, v in step["args"].items()}
            frame["saved"][step["save_as"]] = TOOL_REGISTRY[step["tool"]](**args)
            frame["idx"] += 1

        elif kind == "branch":
            value = _eval_branch(step["on"], frame, ctx)
            case = step["cases"].get(value, step.get("default", {"note": ""}))
            if case.get("note"):
                frame["notes"].append(case["note"])
            if case.get("reask"):
                slot = case["reask"]
                frame["slots"].pop(slot, None)
                frame["retries"][slot] = frame["retries"].get(slot, 0) + 1
                if frame["retries"][slot] > load_config().slot_retry_limit:
                    frame["status"] = "escalated"
                    frame["notes"].append("This is handed to a human colleague who will "
                                          "call back shortly; nothing further is needed now.")
                    return frame
                for i, s in enumerate(SOP_SPECS[frame["sop"]]["steps"]):
                    if s.get("slot") == slot:
                        frame["idx"] = i
                        break
                continue
            if case.get("escalate"):
                frame["status"] = "escalated"
                return frame
            if case.get("end"):
                frame["status"] = "done"
                frame["summary"] = frame["notes"][-1] if frame["notes"] else frame["title"]
                return frame
            frame["idx"] += 1

        elif kind == "close":
            frame["status"] = "done"
            frame["summary"] = step["summary"].format(**{**frame["slots"]})
            frame["idx"] += 1
            return frame

    return frame


def opportunistic_fill(frame: dict, message: str) -> None:
    """Harvest slots the message already contains, but only from unambiguous patterns.

    A wire reference or a 5+ digit amount in the text is clearly an answer; a bare
    1-2 digit number is not (it matches stray digits inside an amount), so loose
    validators are collected only when the step explicitly asks for them.
    """
    for step in SOP_SPECS[frame["sop"]]["steps"]:
        if step["kind"] == "collect" and step["slot"] not in frame["slots"]:
            if step.get("validate", "free") not in HARVEST_SAFE:
                continue
            m = VALIDATORS[step["validate"]].search(message)
            if m:
                gated = gate_slot(m.group(1))
                if gated["ok"]:
                    frame["slots"][step["slot"]] = gated["value"]


def prepare_resume(frame: dict) -> None:
    """Slots persist; world-state refreshes. Re-run action steps behind the cursor."""
    steps = SOP_SPECS[frame["sop"]]["steps"]
    for i, step in enumerate(steps[:frame["idx"]]):
        if step["kind"] == "action":
            frame["saved"].pop(step["save_as"], None)
            frame["idx"] = min(frame["idx"], i)
    frame["status"] = "active"
    frame["notes"].append(f"Resuming: {frame['title']} — everything already provided is kept.")


# ---------------------------------------------------------------- turn handling

@observe(name="sop_triage")
def triage(frame: dict, message: str) -> dict:
    """Classify the customer's message relative to the pending step."""
    pending = frame.get("pending")
    if pending:  # deterministic fast path: does the message satisfy the validator?
        rx = VALIDATORS.get(pending["validate"], VALIDATORS["free"])
        if pending["kind"] == "confirm":
            m = VALIDATORS["yes_no"].search(message)
            if m:
                return {"type": "slot_answer", "value": m.group(1)}
        elif pending["validate"] in ("wire_ref", "any_ref", "last4", "amount"):
            # a specific reference/number anywhere in the message IS the answer,
            # even inside a long or angry sentence. These patterns don't false-match.
            m = rx.search(message)
            if m:
                return {"type": "slot_answer", "value": m.group(1)}

    cfg = load_config()
    resp = _client().messages.create(
        model=cfg.router_model, max_tokens=150, temperature=0,
        messages=[{"role": "user", "content": prompts.compile(
            "bb-triage", sop_title=frame["title"],
            pending_ask=(pending or {}).get("ask_for", "nothing right now"),
            message=message)}],
    )
    record_generation(cfg.router_model, resp.usage)
    try:
        out = json.loads(re.search(r"\{.*\}", resp.content[0].text, re.S).group(0))
        if out.get("type") in ("slot_answer", "sop_question", "side_question",
                               "new_intent", "exit"):
            return out
    except Exception:
        pass
    # A pending free-text slot with no clear question defaults to treating the reply
    # as the answer, not re-asking. Re-asking a customer who just answered is the worst tone.
    if pending and pending.get("validate") == "free":
        return {"type": "slot_answer", "value": message.strip()}
    return {"type": "sop_question", "value": ""}


@observe(name="sop_voice", as_type="generation")
def voice(frame: dict, digression: str = "") -> str:
    """Phrase the engine's current position as natural conversation."""
    cfg = load_config()
    if frame["status"] == "done":
        ask = ("nothing more is needed. Confirm the outcome in ONE short warm sentence "
               "using only these facts and inventing nothing (no relationship manager, "
               "no follow-up unless stated here): " + frame["summary"])
    elif frame["status"] == "escalated":
        ask = "nothing. In one short line, say a colleague will take over from here"
    elif frame.get("pending"):
        ask = frame["pending"]["ask_for"]
    else:
        ask = "nothing"
    notes, frame["notes"] = frame["notes"], []      # notes are consumed once
    resp = _client().messages.create(
        model=cfg.answer_model, max_tokens=350,
        messages=[{"role": "user", "content": prompts.compile(
            "bb-voice", sop_title=frame["title"],
            notes=" | ".join(notes) or "none",
            digression=digression or "none", ask=ask)}],
    )
    record_generation(cfg.answer_model, resp.usage)
    return resp.content[0].text


def _sop_self_answer(frame: dict, question: str) -> str:
    """Answer a question about this procedure from the spec itself, in plain words.

    Only ever reference the IMMEDIATE next need, never enumerate future steps, so
    details like replacement pricing do not leak before their step is reached.
    """
    pending = frame.get("pending")
    nxt = pending["ask_for"] if pending else "nothing more from you"
    if _ASKING.search(question):                 # only search on a genuine cost/detail question
        hits = knowledge.search_policy(question, top_k=2)
        policy = " ".join(h.get("content", "")[:250] for h in hits)
        return (f"The customer asked about cost. Relevant policy: {policy}. "
                f"Then continue: you still need {nxt}.")
    return (f"The customer asked about the process. In one line, say what {frame['title'].lower()} "
            f"involves, and that next you need {nxt}.")


@observe(name="procedure_turn")
def handle_turn(frame: dict, message: str, ctx: dict) -> dict:
    """One customer turn inside an active SOP.

    Returns {"reply": str|None, "frame": frame, "handoff": str|None}.
    handoff means: park me, send this message back through the router.
    """
    t = triage(frame, message)

    # a customer urging the current action ("block it now", "just do it") is not really
    # a question, however it gets triaged: reassure and re-ask the pending slot.
    if t["type"] in ("sop_question", "side_question") and \
            _URGING.search(message) and not _ASKING.search(message):
        frame["notes"].append("Reassure them you are on it.")
        return {"reply": voice(frame), "frame": frame, "handoff": None}

    if t["type"] == "slot_answer":
        pending = frame["pending"]
        gated = gate_slot(str(t.get("value") or message))
        if not gated["ok"]:
            frame["retries"][pending["slot"]] = frame["retries"].get(pending["slot"], 0) + 1
            frame["notes"].append("That answer looked like instructions rather than the "
                                  "information needed, so it was not accepted.")
            if frame["retries"][pending["slot"]] > load_config().slot_retry_limit:
                frame["status"] = "escalated"
            return {"reply": voice(frame), "frame": frame, "handoff": None}
        value = gated["value"]
        if pending["kind"] == "confirm":
            if _NO.search(value):                       # explicit decline only
                frame["status"] = "done"
                frame["summary"] = f"{frame['title']}: customer chose not to proceed."
                frame["notes"].append("Understood, nothing is changed on the account.")
                return {"reply": voice(frame), "frame": frame, "handoff": None}
            if not _YES.search(value):                  # neither yes nor no: re-ask, never assume
                frame["retries"][pending["slot"]] = frame["retries"].get(pending["slot"], 0) + 1
                if frame["retries"][pending["slot"]] > load_config().slot_retry_limit:
                    frame["status"] = "escalated"
                    return {"reply": voice(frame), "frame": frame, "handoff": None}
                frame["notes"].append("I just need a yes or no to go ahead.")
                return {"reply": voice(frame), "frame": frame, "handoff": None}
            value = "yes"
        frame["slots"][pending["slot"]] = value
        frame["pending"] = None
        opportunistic_fill(frame, message)   # same message may answer later slots too
        advance(frame, ctx)
        return {"reply": voice(frame), "frame": frame, "handoff": None}

    if t["type"] == "sop_question":
        return {"reply": voice(frame, digression=_sop_self_answer(frame, message)),
                "frame": frame, "handoff": None}

    if t["type"] == "side_question":
        # a customer urging the current action ("block it now", "just do it", "hurry")
        # is not a real question; do not search policy, just re-ask what is pending
        if _URGING.search(message) and not _ASKING.search(message):
            frame["notes"].append("Reassure them you are on it.")
            return {"reply": voice(frame), "frame": frame, "handoff": None}
        hits = knowledge.search_policy(message, top_k=2)
        digression = " ".join(h.get("content", "")[:300] for h in hits) or \
            "No internal answer found; offer to follow up."
        return {"reply": voice(frame, digression=digression), "frame": frame, "handoff": None}

    if t["type"] == "exit":
        frame["status"] = "abandoned"
        frame["summary"] = f"{frame['title']}: abandoned by customer mid-procedure."
        frame["notes"].append("The request is closed with no changes made; it can be "
                              "restarted any time.")
        return {"reply": voice(frame), "frame": frame, "handoff": None}

    # new_intent: the graph parks this frame and re-routes the message
    return {"reply": None, "frame": frame, "handoff": message}


def start(sop_name: str, first_message: str, ctx: dict) -> dict:
    """Open a new frame, harvest what the first message already contains, advance."""
    frame = new_frame(sop_name)
    opportunistic_fill(frame, first_message)
    advance(frame, ctx)
    return {"reply": voice(frame), "frame": frame, "handoff": None}
