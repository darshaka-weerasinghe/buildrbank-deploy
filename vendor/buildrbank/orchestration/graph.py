"""The BuildrBank graph: context load → sticky check → runner | router →
specialists → judge → output gate → memory write.

Edges are control flow; capability access is by import (the one-way street).
State is persisted per thread_id by the sqlite checkpointer, which is what
makes procedures survive across turns and process restarts.
"""
from __future__ import annotations

import json
import re
from typing import Any, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

from ..config import load as load_config
from ..memory import long_term, procedural, short_term
from ..observability import observe, record_generation
from ..tools import crm, knowledge, websearch
from . import procedure_runner, prompts
from .guardrails import gate_context, gate_output
from .judge import score_trace, verdict
from .sop_specs import SOP_SPECS


class BBState(TypedDict, total=False):
    # per-conversation (persisted by the checkpointer)
    user_id: str
    user_email: str
    ctx: dict            # profile prefetch: name, segment, kyc_status, email
    history: list        # [(user, bot), ...] capped
    procedures: list     # stack of runner frames
    pending_disambiguation: list   # SOP candidates asked about last turn (persisted)
    last_done: str       # SOP that completed last turn (persisted one turn)
    # per-turn (overwritten every invoke)
    dis_candidates: list  # candidates carried into this turn's router
    recent_done: str      # last_done surfaced for this turn's router
    message: str
    recall: dict         # episodic + semantic memories loaded this turn
    route: str
    evidence: str
    reply: str
    judged: bool
    events: list


def _llm() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=load_config().anthropic_api_key, max_retries=5)


# a bare acknowledgement vs a genuinely new request (used to suppress redundant restarts)
_ACK = re.compile(r"\b(yes|yeah|yep|ok|okay|confirm(?:ed)?|go ahead|do it|please do|sure|"
                  r"thanks|thank you|great|perfect|all good|that'?s all|done)\b", re.I)
_NEW_REQUEST = re.compile(r"\b(another|different|new|again|also|one more|second|this time)\b", re.I)


# ---------------------------------------------------------------- nodes

@observe(name="context_load")
def context_load(state: BBState) -> dict:
    """The read path: restore who this is and what we remember, before thinking."""
    ctx = dict(state.get("ctx") or {})
    if not ctx.get("profile_loaded") and state.get("user_email"):
        prof = crm.get_customer_profile(state["user_email"])
        if prof.get("found"):
            ctx.update({"email": state["user_email"], "name": prof.get("full_name"),
                        "segment": prof.get("segment"), "kyc_status": prof.get("kyc_status")})
        ctx["profile_loaded"] = True
    user_id = state.get("user_id", "anon")
    msg = state.get("message", "")
    recall = {
        "episodes": long_term.recall_episodes(user_id, msg),
        "facts": long_term.recall_facts(user_id, msg),
    }
    # Age parked frames. A frame parked before this turn is no longer part of a live
    # switch. If nothing is actively being worked on, an idle parked frame is orphaned:
    # count it down and abandon it after a couple of turns so a thread never stays jammed.
    procs = state.get("procedures") or []
    has_active = any(p.get("status") == "active" for p in procs)
    kept, expired = [], []
    for p in procs:
        if p.get("status") == "parked":
            p["just_parked"] = False
            if not has_active:
                p["dormant"] = p.get("dormant", 0) + 1
                if p["dormant"] > 2:
                    expired.append({"type": "abandoned", "sop": p["sop"],
                                    "summary": f"{SOP_SPECS[p['sop']]['title']}: closed after "
                                               "being left idle across several turns",
                                    "slots": dict(p.get("slots", {}))})
                    continue
            else:
                p["dormant"] = 0
        kept.append(p)

    # sticky disambiguation: carry last turn's candidates forward for one turn,
    # then reset the persisted flag so it can never linger across the conversation
    incoming_dis = state.get("pending_disambiguation") or []
    return {"ctx": ctx, "recall": recall, "reply": "", "judged": False,
            "events": expired, "route": "", "evidence": "",
            "pending_disambiguation": None, "dis_candidates": incoming_dis,
            "procedures": kept,
            "last_done": None, "recent_done": state.get("last_done")}


def sticky_route(state: BBState) -> str:
    procs = state.get("procedures") or []
    if procs and procs[-1].get("status") == "active":
        return "runner"
    return "router"


@observe(name="runner")
def runner(state: BBState) -> dict:
    procs = list(state.get("procedures") or [])
    frame = procs[-1]
    out = procedure_runner.handle_turn(frame, state["message"], state.get("ctx", {}))
    events = list(state.get("events") or [])

    if out["handoff"] is not None:                    # new intent: park and re-route
        frame["status"] = "parked"
        frame["just_parked"] = True                   # parked THIS turn, part of a live switch
        procs[-1] = frame
        events.append({"type": "parked", "sop": frame["sop"]})
        return {"procedures": procs, "events": events, "route": "handoff"}

    procs[-1] = out["frame"]
    reply = out["reply"]
    last_done = None
    if out["frame"]["status"] in ("done", "escalated", "abandoned"):
        closed = procs.pop()
        last_done = closed["sop"]                       # remember it for one turn
        events.append({"type": closed["status"], "sop": closed["sop"],
                       "summary": closed.get("summary", ""),
                       "slots": dict(closed.get("slots", {}))})
        if procs and procs[-1]["status"] == "parked":  # offer the parked one back
            resumed = procs[-1]
            procedure_runner.prepare_resume(resumed)
            procedure_runner.advance(resumed, state.get("ctx", {}))
            reply = reply + "\n\n" + procedure_runner.voice(resumed)
            last_done = None                            # a procedure is active again
    return {"procedures": procs, "reply": reply, "events": events,
            "route": "runner", "last_done": last_done}


def _select_sop(message: str, candidates: list) -> dict:
    """Stage two of matching: the LLM picks the right SOP from the embedding shortlist.

    Embeddings put semantically-adjacent procedures (wire recall / dispute / fraud)
    within a hair of each other, so a raw similarity gap disambiguates far too often.
    The LLM reads the message against each candidate's real trigger and decides.
    Returns {"kind": "one", "sop": name} | {"kind": "ambiguous", "candidates": [..]}
            | {"kind": "none"}.
    """
    cfg = load_config()
    lines = []
    for c in candidates:
        spec = SOP_SPECS.get(c["name"], {})
        lines.append(f"- {c['name']}: {spec.get('title', c['name'])} "
                     f"(use when: {c.get('context_when', c.get('description', ''))})")
    resp = _llm().messages.create(
        model=cfg.router_model, max_tokens=80, temperature=0,
        messages=[{"role": "user", "content":
                   f"The customer wants to carry out a banking procedure. Pick the ONE "
                   f"that best matches their message. Ignore eligibility wording like "
                   f"'VIP' in the descriptions; just match the intent.\n\n"
                   f"Customer message: {message}\n\n"
                   f"Candidate procedures:\n" + "\n".join(lines) + "\n\n"
                   "Reply with the best match. Only if two fit genuinely equally and you "
                   "truly cannot tell, say ambiguous with the two names. Say none only if "
                   "the message matches NONE of them at all.\n"
                   'Reply ONLY as JSON: {"choice": "<procedure name>|ambiguous|none", '
                   '"pair": ["<name>", "<name>"]}'}],
    )
    record_generation(cfg.router_model, resp.usage)
    valid = {c["name"] for c in candidates}
    top = candidates[0]
    try:
        out = json.loads(re.search(r"\{.*\}", resp.content[0].text, re.S).group(0))
        choice = str(out.get("choice", "")).strip()
        if choice in valid:
            return {"kind": "one", "sop": choice}
        if choice == "ambiguous":
            pair = [p for p in out.get("pair", []) if p in valid][:2]
            if len(pair) == 2:
                return {"kind": "ambiguous", "candidates": pair}
        # 'none' or garbage: trust the embedding when it is reasonably confident,
        # since the router already established this is a procedure request.
        if top.get("similarity", 0) >= 0.45:
            return {"kind": "one", "sop": top["name"]}
        if choice == "none":
            return {"kind": "none"}
    except Exception:
        pass
    return {"kind": "one", "sop": top["name"]}   # fall back to embedding top-1


def _resolve_disambiguation(message: str, candidates: list) -> str | None:
    """The customer answered a 'is this X or Y?' question. Which SOP did they pick?"""
    cfg = load_config()
    titles = {c: SOP_SPECS[c]["title"] for c in candidates if c in SOP_SPECS}
    if not titles:
        return None
    options = "\n".join(f"- {name}: {title}" for name, title in titles.items())
    resp = _llm().messages.create(
        model=cfg.router_model, max_tokens=60, temperature=0,
        messages=[{"role": "user", "content":
                   f"The customer was asked to choose between these processes:\n{options}\n\n"
                   f"Their reply: {message}\n\n"
                   "Which one did they mean? Reply ONLY with the exact process name from the "
                   'list, or "neither" if their reply picks none of them.'}],
    )
    record_generation(cfg.router_model, resp.usage)
    pick = resp.content[0].text.strip().strip('"').lower()
    for name in titles:
        if name in pick:
            return name
    return None


@observe(name="router", as_type="generation")
def router(state: BBState) -> dict:
    cfg = load_config()

    # a disambiguation question was asked last turn: resolve it before re-routing
    if state.get("dis_candidates"):
        choice = _resolve_disambiguation(state["message"], state["dis_candidates"])
        if choice:
            procs = list(state.get("procedures") or [])
            events = list(state.get("events") or [])
            out = procedure_runner.start(choice, state["message"], state.get("ctx", {}))
            procs.append(out["frame"])
            events.append({"type": "started", "sop": choice, "via": "disambiguation"})
            return {"route": "direct", "reply": out["reply"], "procedures": procs,
                    "events": events}
        # unclear pick: fall through to normal routing (flag already cleared)

    resp = _llm().messages.create(
        model=cfg.router_model, max_tokens=100, temperature=0,
        messages=[{"role": "user",
                   "content": prompts.compile("bb-router", message=state["message"])}],
    )
    record_generation(cfg.router_model, resp.usage)
    try:
        route = json.loads(re.search(r"\{.*\}", resp.content[0].text, re.S).group(0))["route"]
    except Exception:
        route = "policy"
    if route not in ("procedure", "policy", "transactions", "websearch", "smalltalk", "refuse"):
        route = "policy"

    if route != "procedure":
        return {"route": route}

    # procedure intent. Two-stage match: embeddings shortlist, the LLM confirms which.
    cands = [c for c in procedural.match_sops(state["message"], k=3)
             if c.get("similarity", 0) >= cfg.sop_match_floor]
    procs = list(state.get("procedures") or [])
    events = list(state.get("events") or [])

    if not cands:
        return {"route": "policy"}        # nothing close: answer as a question instead

    decision = _select_sop(state["message"], cands)

    # guard: a bare acknowledgement of the procedure that just finished ("yes, confirm
    # the cancellation" right after it was cancelled) must not start a redundant one.
    if (decision.get("kind") == "one" and decision.get("sop") == state.get("recent_done")
            and _ACK.search(state["message"]) and not _NEW_REQUEST.search(state["message"])):
        return {"route": "smalltalk"}

    if decision["kind"] == "one":
        # a genuinely new request means the customer has moved on from anything parked
        # in an earlier turn: abandon those stale frames. Keep only a frame parked THIS
        # turn (a live switch, to be resumed) so the stack never jams on old procedures.
        kept = []
        for p in procs:
            if p.get("status") == "parked" and not p.get("just_parked"):
                events.append({"type": "abandoned", "sop": p["sop"],
                               "summary": f"{SOP_SPECS[p['sop']]['title']}: not resumed, "
                                          "closed when the customer moved on",
                               "slots": dict(p.get("slots", {}))})
            else:
                kept.append(p)
        procs = kept
        out = procedure_runner.start(decision["sop"], state["message"], state.get("ctx", {}))
        procs.append(out["frame"])
        events.append({"type": "started", "sop": decision["sop"]})
        return {"route": "direct", "reply": out["reply"], "procedures": procs, "events": events}

    if decision["kind"] == "ambiguous":
        a, b = decision["candidates"][:2]
        events.append({"type": "disambiguate", "candidates": [a, b]})
        return {"route": "direct", "events": events,
                "pending_disambiguation": [a, b], "reply":
                f"I can help with that. Quick check so I start the right process: "
                f"is this about {SOP_SPECS[a]['title'].lower()}, "
                f"or {SOP_SPECS[b]['title'].lower()}?"}

    return {"route": "policy"}        # LLM saw no real procedure intent


def route_after_router(state: BBState) -> str:
    r = state.get("route", "policy")
    if r in ("direct", "runner"):
        return "output_gate"
    return {"policy": "answer_policy", "transactions": "answer_transactions",
            "websearch": "answer_live", "smalltalk": "smalltalk",
            "refuse": "refuse", "handoff": "router"}.get(r, "answer_policy")


@observe(name="standalone_question", as_type="generation")
def _standalone(state: BBState) -> str:
    """Rewrite a follow-up into a standalone question, with Sri Lankan context.

    'And the Indian rupee?' after a rate question must become
    'INR to LKR exchange rate today', not an encyclopedia lookup.
    """
    msg = state["message"]
    history = state.get("history") or []
    if not history and len(msg.split()) > 6:
        return msg
    cfg = load_config()
    recent = " | ".join(f"cust: {u[:80]} / agent: {b[:80]}" for u, b in history[-2:]) or "none"
    resp = _llm().messages.create(
        model=cfg.router_model, max_tokens=80, temperature=0,
        messages=[{"role": "user", "content":
                   f"Conversation so far: {recent}\nNew customer message: {msg}\n\n"
                   "Rewrite the new message as ONE standalone question for a Sri Lankan "
                   "bank's support system. Resolve pronouns and follow-ups from the "
                   "conversation. If it asks about currency or rates without naming both "
                   "currencies, assume the customer wants the rate against LKR (Sri "
                   "Lankan rupees). Reply with the rewritten question only."}],
    )
    record_generation(cfg.router_model, resp.usage)
    return resp.content[0].text.strip()


def _grounded_answer(question: str, evidence: str) -> str:
    cfg = load_config()
    resp = _llm().messages.create(
        model=cfg.answer_model, max_tokens=400,
        messages=[{"role": "user", "content": prompts.compile(
            "bb-answer", question=question, evidence=evidence or "none found")}],
    )
    record_generation(cfg.answer_model, resp.usage)
    return resp.content[0].text


@observe(name="answer_policy", as_type="generation")
def answer_policy(state: BBState) -> dict:
    q = _standalone(state)
    hits = gate_context(knowledge.search_policy(q))
    evidence = "\n".join(f"- {h.get('content', '')[:500]}" for h in hits)
    return {"evidence": evidence, "reply": _grounded_answer(q, evidence)}


@observe(name="answer_transactions", as_type="generation")
def answer_transactions(state: BBState) -> dict:
    msg = _standalone(state)
    ref = re.search(r"\b([A-Z]{2,6}-\d{3,})\b", msg, re.I)
    if ref:
        data = crm.get_wire_status(ref.group(1).upper())
        if not data.get("found"):
            data = crm.find_transaction(ref.group(1).upper())
    elif state.get("ctx", {}).get("email"):
        data = crm.get_customer_profile(state["ctx"]["email"])
    else:
        data = {"found": False, "note": "no reference given and no customer on session"}
    evidence = json.dumps(data, default=str)[:2000]
    return {"evidence": evidence, "reply": _grounded_answer(msg, evidence)}


@observe(name="answer_live", as_type="generation")
def answer_live(state: BBState) -> dict:
    q = _standalone(state)
    res = websearch.web_search(q)
    results = gate_context(res.get("results", []), text_key="content")
    evidence = "\n".join(f"- {r['title']}: {r['content'][:400]}" for r in results) \
        if res.get("ok") else f"(web search unavailable: {res.get('reason')})"
    return {"evidence": evidence, "reply": _grounded_answer(q, evidence)}


@observe(name="smalltalk", as_type="generation")
def smalltalk(state: BBState) -> dict:
    cfg = load_config()
    episodes = "; ".join(e.get("summary", "") for e in
                         state.get("recall", {}).get("episodes", [])[:2]) or "none"
    titles = ", ".join(s["title"].lower() for s in SOP_SPECS.values())
    resp = _llm().messages.create(
        model=cfg.answer_model, max_tokens=250,
        messages=[{"role": "user", "content": prompts.compile(
            "bb-smalltalk", message=state["message"], episodes=episodes, sop_titles=titles)}],
    )
    record_generation(cfg.answer_model, resp.usage)
    return {"reply": resp.content[0].text}


@observe(name="refuse", as_type="generation")
def refuse(state: BBState) -> dict:
    cfg = load_config()
    reason = "personal investment advice" if re.search(
        r"invest|stock|crypto|bitcoin", state["message"], re.I) else \
        "outside what bank support can share or do"
    resp = _llm().messages.create(
        model=cfg.answer_model, max_tokens=250,
        messages=[{"role": "user", "content": prompts.compile(
            "bb-refuse", message=state["message"], reason=reason)}],
    )
    record_generation(cfg.answer_model, resp.usage)
    return {"reply": resp.content[0].text}


@observe(name="judge")
def judge_node(state: BBState) -> dict:
    v = verdict(state["message"], state.get("reply", ""))
    score_trace(v)
    return {"judged": True}


@observe(name="output_gate")
def output_gate(state: BBState) -> dict:
    return {"reply": gate_output(state.get("reply", ""))}


@observe(name="memory_write")
def memory_write(state: BBState) -> dict:
    """The write path: transcript mirror + episodic events for closed procedures."""
    user_id = state.get("user_id", "anon")
    thread = state.get("thread_id", "") or user_id
    short_term.append_turns(user_id, thread, state.get("message", ""), state.get("reply", ""))
    turns_log = [{"user": u, "bot": b} for u, b in (state.get("history") or [])[-6:]]
    turns_log.append({"user": state.get("message", ""), "bot": state.get("reply", "")})
    for ev in state.get("events") or []:
        if ev["type"] in ("done", "escalated", "abandoned"):
            long_term.record_episode(
                user_id, thread,
                summary=ev.get("summary") or f"{ev['sop']} {ev['type']}",
                topic_tags=[ev["sop"], ev["type"]],
                turn_count=len(turns_log), turns=turns_log,
            )
    history = (state.get("history") or [])[-11:]
    history.append((state.get("message", ""), state.get("reply", "")))
    return {"history": history}


# ---------------------------------------------------------------- assembly

def build_graph(checkpointer=None):
    g = StateGraph(BBState)
    g.add_node("context_load", context_load)
    g.add_node("runner", runner)
    g.add_node("router", router)
    g.add_node("answer_policy", answer_policy)
    g.add_node("answer_transactions", answer_transactions)
    g.add_node("answer_live", answer_live)
    g.add_node("smalltalk", smalltalk)
    g.add_node("refuse", refuse)
    g.add_node("judge", judge_node)
    g.add_node("output_gate", output_gate)
    g.add_node("memory_write", memory_write)

    g.set_entry_point("context_load")
    g.add_conditional_edges("context_load", sticky_route,
                            {"runner": "runner", "router": "router"})
    g.add_conditional_edges("runner", route_after_router,
                            {"output_gate": "output_gate", "router": "router"})
    g.add_conditional_edges("router", route_after_router, {
        "output_gate": "output_gate", "answer_policy": "answer_policy",
        "answer_transactions": "answer_transactions", "answer_live": "answer_live",
        "smalltalk": "smalltalk", "refuse": "refuse", "router": "router"})
    for judged in ("answer_policy", "answer_transactions", "answer_live", "refuse"):
        g.add_edge(judged, "judge")
    g.add_edge("judge", "output_gate")
    g.add_edge("smalltalk", "output_gate")          # greetings skip the judge
    g.add_edge("output_gate", "memory_write")
    g.add_edge("memory_write", END)
    return g.compile(checkpointer=checkpointer)
