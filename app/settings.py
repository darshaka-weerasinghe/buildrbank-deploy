"""
Settings for the deployment.

WHY THIS FILE EXISTS
--------------------
The agent package in vendor/buildrbank/ keeps every setting in one place:
`buildrbank/config.py`. Normally the package loads those settings itself,
from a .env file sitting next to it, and it insists on Anthropic + Alibaba
keys because that is what the students used in class.

We want three different things:

  1. our own .env, in this project folder
  2. one OpenRouter key instead of several different provider keys
  3. the agent package left EXACTLY as the students wrote it

So this file builds the settings object itself and hands it to the package.
The package has a "have I already been configured?" check at the top of its
`load()` function - we fill that in first, so it finds the answer waiting and
never runs its own loader.

Nothing in vendor/ is edited. Not one line.

ORDER MATTERS
-------------
`configure()` must run BEFORE anything imports `buildrbank.app`, because the
package reads some values at import time. app/api.py does this correctly -
look at the top of that file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# The agent package lives in vendor/, which Python does not look in by
# default. Add it to the search path so `import buildrbank` works. We keep
# it there rather than installing it, so you can see at a glance that it is
# an untouched copy of the students' code.
_VENDOR = Path(__file__).resolve().parent.parent / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

# Importing the config MODULE is safe and does not start the agent.
import buildrbank.config as bb_config

# ---------------------------------------------------------------- paths

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"          # the conversation memory file lives here

load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------- OpenRouter
#
# OpenRouter can pretend to be two different providers at once, which is why
# one key is enough for the whole system:
#
#   - Chat models.  The Anthropic library builds its address by sticking
#     "/v1/messages" onto the end of a base URL. So we give it the base
#     ".../api" and it ends up calling .../api/v1/messages, which OpenRouter
#     understands. We set this as an environment variable because that is
#     where the Anthropic library looks for it - the agent code never passes
#     an address of its own, so ours wins.
#
#   - Embeddings.  Plain OpenAI-style, so the full ".../api/v1" address.
#
# Model names need the provider in front ("anthropic/claude-haiku-4.5"),
# which is why the names below are not identical to the ones in class.

ANTHROPIC_BASE_URL = "https://openrouter.ai/api"
EMBED_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULTS = {
    "ANSWER_MODEL": "anthropic/claude-sonnet-4.6",   # writes the customer's reply
    "ROUTER_MODEL": "anthropic/claude-haiku-4.5",    # fast decisions: which route?
    "JUDGE_MODEL": "anthropic/claude-haiku-4.5",     # grades the reply afterwards
    "EMBED_MODEL": "openai/text-embedding-3-small",  # turns text into numbers
}

# These must be present or the agent cannot work at all.
REQUIRED = ("OPENROUTER_API_KEY", "SUPABASE_URL", "SUPABASE_KEY")


def _pick(name: str) -> str:
    """Read a model name from .env, falling back to our default."""
    return os.environ.get(name) or DEFAULTS[name]


def configure() -> bb_config.Config:
    """Build the settings and hand them to the agent package.

    Returns the settings object, mostly so the startup log can print what
    it is about to use.
    """
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            "Missing from .env: " + ", ".join(missing) + ".\n"
            "Copy .env.example to .env and fill it in."
        )

    key = os.environ["OPENROUTER_API_KEY"].strip()

    # Point the Anthropic library at OpenRouter. `setdefault` means a value
    # already set in the real environment wins - useful later in Docker.
    os.environ.setdefault("ANTHROPIC_BASE_URL", ANTHROPIC_BASE_URL)

    # Langfuse reads its own keys straight from the environment. If they are
    # missing or fake the agent still runs - recording just fails quietly in
    # the background. So we fill in placeholders rather than refuse to start.
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-lf-not-configured")
    os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-not-configured")
    os.environ.setdefault("LANGFUSE_HOST", "https://cloud.langfuse.com")

    # The agent writes its conversation memory to a file. The package puts
    # that file next to itself, i.e. inside vendor/. We would rather keep
    # vendor/ pristine, so we redirect it to this project's data/ folder.
    # This has to happen before the memory module is imported, because that
    # module works out the file path once, at import time.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bb_config.DATA_DIR = DATA_DIR

    # The handover: fill in the package's "already configured" slot.
    # `load()` returns this immediately and skips everything else it does.
    bb_config._config = bb_config.Config(
        # --- models, renamed for OpenRouter ---
        answer_model=_pick("ANSWER_MODEL"),
        router_model=_pick("ROUTER_MODEL"),
        judge_model=_pick("JUDGE_MODEL"),
        embed_model=_pick("EMBED_MODEL"),
        embed_base_url=EMBED_BASE_URL,
        embed_dim=1536,          # must match the database. Do not change.

        # --- credentials ---
        # The same OpenRouter key is used twice: once where the package
        # expects an Anthropic key, once where it expects an Alibaba key.
        anthropic_api_key=key,
        qwen_api_key=key,
        supabase_url=os.environ["SUPABASE_URL"].strip(),
        supabase_key=os.environ["SUPABASE_KEY"].strip(),
        tavily_api_key=os.environ.get("TAVILY_API_KEY", "").strip(),

        # --- a label for the recordings, so class traffic is easy to spot ---
        environment=os.environ.get("BB_ENV", "local"),

        # Everything else - how confident an SOP match must be, how many
        # memories to recall, and so on - is deliberately left alone. Those
        # are the agent's behaviour, and the agent's behaviour is not ours
        # to change.
    )
    return bb_config._config


def summary(cfg: bb_config.Config) -> dict:
    """A safe description of the settings. Never includes a key."""
    return {
        "answer_model": cfg.answer_model,
        "router_model": cfg.router_model,
        "judge_model": cfg.judge_model,
        "embed_model": cfg.embed_model,
        "llm_via": os.environ.get("ANTHROPIC_BASE_URL", ""),
        "embed_via": cfg.embed_base_url,
        "supabase": cfg.supabase_url,
        "websearch": "on" if cfg.tavily_api_key else "off",
        "tracing": "on" if "not-configured" not in os.environ.get(
            "LANGFUSE_PUBLIC_KEY", "") else "off",
        "memory_file": str(DATA_DIR / "checkpoints.sqlite"),
    }
