"""
Preflight check. Run this BEFORE starting the server.

    python scripts/check.py

It tests each piece on its own, in order, so that when something is wrong
you know exactly which thing is wrong. Starting the server first and reading
a stack trace tells you much less.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make this runnable as `python scripts/check.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import settings     # noqa: E402

OK, BAD = "  PASS  ", "  FAIL  "
failures = []


def step(name):
    print(f"\n{name}")
    print("-" * len(name))


def good(msg):
    print(OK + msg)


def bad(msg, hint=""):
    print(BAD + msg)
    if hint:
        print("        -> " + hint)
    failures.append(msg)


# ---------------------------------------------------------------- 1. settings
step("1. Settings")
try:
    cfg = settings.configure()
    for k, v in settings.summary(cfg).items():
        print(f"        {k:<14} {v}")
    good("loaded")
except Exception as e:
    bad(str(e), "Copy .env.example to .env and fill it in.")
    print("\nCannot continue without settings.")
    sys.exit(1)


# ---------------------------------------------------------------- 2. chat model
step("2. Chat model, through OpenRouter")
try:
    import anthropic
    r = anthropic.Anthropic(api_key=cfg.anthropic_api_key).messages.create(
        model=cfg.router_model, max_tokens=12,
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
    )
    good(f"{cfg.router_model} replied {r.content[0].text.strip()!r}")
except Exception as e:
    bad(f"{type(e).__name__}: {e}",
        "Check OPENROUTER_API_KEY, and that the model name has the "
        "'anthropic/' prefix in front of it.")


# ---------------------------------------------------------------- 3. embeddings
step("3. Embeddings, through OpenRouter")
try:
    from openai import OpenAI
    client = OpenAI(api_key=cfg.qwen_api_key, base_url=cfg.embed_base_url)
    vec = client.embeddings.create(
        model=cfg.embed_model, input="wire transfer fees", dimensions=cfg.embed_dim,
    ).data[0].embedding
    if len(vec) == cfg.embed_dim:
        good(f"{cfg.embed_model} returned {len(vec)} numbers")
    else:
        bad(f"got {len(vec)} numbers, the database expects {cfg.embed_dim}",
            "Search will return nothing. Use a model that can do 1536.")
except Exception as e:
    bad(f"{type(e).__name__}: {e}", "Check the embedding model name.")


# ---------------------------------------------------------------- 4. database
step("4. Database (Supabase)")
try:
    from supabase import create_client
    sb = create_client(cfg.supabase_url, cfg.supabase_key)
    counts = {}
    for table in ("customers", "kb_chunks", "mem_procedures"):
        counts[table] = sb.table(table).select("*", count="exact").limit(1).execute().count
    for t, n in counts.items():
        print(f"        rows in {t:<16} {n}")
    if all(counts.values()):
        good("connected and seeded")
    else:
        bad("some tables are empty",
            "Run Week 06 notebook 00_setup_supabase.ipynb against this project.")
except Exception as e:
    bad(f"{type(e).__name__}: {e}",
        "Check SUPABASE_URL and SUPABASE_KEY. A paused free-tier project "
        "fails here too - unpause it in the dashboard.")


# ---------------------------------------------------------------- 5. search
step("5. Searching the handbook")
try:
    from buildrbank.tools.knowledge import search_policy
    hits = search_policy("what is the fee for a wire transfer?")
    if hits:
        good(f"{len(hits)} passages found")
        print(f'        best match: "{hits[0].get("content", "")[:70].strip()}…"')
    else:
        bad("search returned nothing",
            "The handbook chunks were embedded with a DIFFERENT model than "
            "the one above. Re-seed the knowledge base using this model.")
except Exception as e:
    bad(f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- 6. a real turn
step("6. One full message through the agent")
try:
    from buildrbank.app import build_app
    agent = build_app()
    out = agent.turn(user_id="preflight", thread_id="preflight-001",
                     text="What is the interest rate on a savings account?")
    good(f"route={out.route}")
    print(f'        reply: "{out.reply[:90].strip()}…"')
    agent.close()
except Exception as e:
    bad(f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- verdict
print()
if failures:
    print(f"{len(failures)} check(s) failed. Fix the first one and run again.")
    sys.exit(1)
print("Everything is wired up. Start the server with:")
print("    uvicorn app.api:api --reload --port 8000")
