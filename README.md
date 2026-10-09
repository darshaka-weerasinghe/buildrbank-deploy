# BuildrBank · put it on the internet

The agent you built in Phase 1 is a Python library. You can call it from a
script; you cannot send it to anyone. This repo adds the three things it is
missing — a web address, a chat page, and settings that come from outside —
**without changing one line of the agent itself.**

By the end you will have a link you can open on your phone.

```
you ──> browser ──> FastAPI ──> BuildrBank ──> OpenRouter  (the thinking)
                                           └──> Supabase    (the bank's data)
```

---

## Before you start

Four accounts. All free, none need a card.

| | | |
|---|---|---|
| **Supabase** | <https://supabase.com> | the database |
| **OpenRouter** | <https://openrouter.ai/keys> | the models — one key covers chat *and* embeddings |
| **Langfuse** | <https://cloud.langfuse.com> | the prompts, and the recording |
| **Docker Hub** | <https://hub.docker.com> | you already made this in Week 03 |

And **Python 3.12 or 3.13** — *not* the newest one you can find. On a very new
Python some of these libraries have no ready-made package, so pip tries to
build them from source: it looks like a twenty-minute hang, then fails.

---

## The ten steps

### 1 · Make the Supabase project

New project → any name → the region nearest you → generate the password and
**write it down** (it is shown once). It takes about two minutes to build.

### 2 · Run the SQL

Supabase dashboard → **SQL Editor** → **New query** → paste → **Run**.
Three files, in this order:

| | | |
|---|---|---|
| [`scripts/schema.sql`](scripts/schema.sql) | 12 tables, 6 search functions | no data |
| [`scripts/seed-1-bank.sql`](scripts/seed-1-bank.sql) | customers, accounts, transactions | 5 KB |
| [`scripts/seed-2-knowledge.sql`](scripts/seed-2-knowledge.sql) | the handbook and the procedures | 450 KB — give it a moment |

All three are safe to run more than once.

> **Supabase will warn you: "Potential issues detected".** Choose
> **Run without RLS** — not the green button. The app signs in with the
> publishable key, and Row Level Security with no policies blocks every query
> it makes. It fails deceptively: the seed files still load, so the tables look
> correct, and only `check.py` tells you something is wrong.

> No terminal yet. Creating tables is not something an API key is allowed to
> do, so this part happens in the browser.

> **Why is file 2 so big?** Every handbook chunk carries a 1536-number
> embedding, and those numbers cannot be written by hand. They were generated
> with `openai/text-embedding-3-small` — the model `.env.example` pins
> `EMBED_MODEL` to. Change that model and search silently returns nothing;
> regenerate with `python scripts/seed.py` instead.

### 3 · Fill in your keys

```bash
cp .env.example .env
```

Then open `.env` and fill it in. The Supabase values are in your project under
**Project Overview** → the **Copy** button beside the project name. The model
names are already filled in.

`.env` is gitignored, and the Dockerfile never copies it. Keep it that way.

### 4 · Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

**Checkpoint —** `python scripts/check.py` prints six green ticks.

> **`python: command not found`?** The venv is not active in that terminal.
> Run the `activate` line again — you need it in every new window. Use
> `python`, not `python3`: a Windows venv does not create a `python3`.

It tests settings, chat model, embeddings, database, handbook search, and one
real message, one at a time, so when something is wrong you know *which* thing.

### 5 · Run it

```bash
python -m uvicorn app.api:api --reload --port 8000
```

> `python -m uvicorn`, not bare `uvicorn` — that guarantees the same
> interpreter pip installed into, and cannot pick up some other `uvicorn`
> left on your PATH by another project.

**Checkpoint —** <http://localhost:8000> opens the chat page and answers you.

### 6 · Build the image

```bash
docker build --platform linux/amd64 -t buildrbank:v1 .

docker run -d --name bank -p 8000:8000 --env-file .env buildrbank:v1
docker logs -f bank
```

**Checkpoint —** same page, same port, and your keys were never baked in.

> **`--platform linux/amd64` is not optional.** On an Apple Silicon Mac,
> leaving it out builds an arm64 image. EC2 runs x86. The push will work, the
> pull will warn, and the container will die with `exec format error` — an hour
> later, with no clue pointing back here.

### 7 · Push it to Docker Hub

```bash
docker login
docker tag  buildrbank:v1 YOUR-NAME/buildrbank:v1
docker push YOUR-NAME/buildrbank:v1
```

Public is fine — your keys are not in the image. That is what `--env-file`
bought you.

### 8 · Rent the machine

EC2 → Launch instance.

| | |
|---|---|
| Image | Ubuntu, 64-bit **x86** |
| Size | `t3.micro` — 1 GB RAM is plenty, ours uses 134 MB |
| Key pair | download the `.pem`; you only get it once |
| Firewall | allow **22** and **8000**, source **My IP** |

> **My IP, not `0.0.0.0/0`.** This agent has no login. Anyone who finds the
> address can run up your OpenRouter bill and read the bank's data, and
> scanners find open ports within hours.

### 9 · Walk in, install Docker

```bash
chmod 400 builder-bank.pem
scp -i builder-bank.pem .env ubuntu@YOUR-IP:~     # the one file not in the image
ssh -i builder-bank.pem ubuntu@YOUR-IP

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu                    # then log out and back in
chmod 600 ~/.env
```

**Checkpoint —** `docker ps` runs without `sudo` and prints an empty table.

### 10 · Pull it, run it for good

```bash
docker login
docker pull YOUR-NAME/buildrbank:v1

docker run -d --name bank --restart unless-stopped \
  -p 8000:8000 --env-file ~/.env YOUR-NAME/buildrbank:v1
```

**Checkpoint —** open `http://YOUR-IP:8000` on your phone, off wifi.

`--restart unless-stopped` is the difference between a demo and a service. The
machine reboots; your agent comes back by itself.

---

## Try these

Sign in as **Isuru (VIP)** in the dropdown.

| Say this | What should happen |
|---|---|
| `What is the interest rate on a savings account?` | Answers from the handbook. Route: `policy` |
| `Where is WIRE-30621?` | Looks it up in the database. Route: `transactions` |
| `Can you recall it?` | Starts the VIP wire recall **procedure**, and asks you a question |
| `Actually, what are your wire fees?` | Answers the side question, then returns to the procedure |

That last one is the whole system in one move: it parks what it was doing,
answers, and picks the procedure back up where it left off.

The small grey line under each reply shows which path the message took.

---

## When it breaks

| What you see | Where to look |
|---|---|
| **The page never loads** | The port is closed, or the app bound to `127.0.0.1`. Check the security group first. |
| **The container exits immediately** | `docker logs bank`. Almost always a missing key in `.env`. |
| **It answers, but knows nothing** | `seed-2-knowledge.sql` did not finish, or `EMBED_MODEL` was changed. Re-run the file in the SQL editor. |

Read the log *before* you change anything. The first error is the real one.

---

## What is in here

```
app/
  settings.py     where the settings come from   <- the interesting file
  api.py          the web address
  index.html      the chat page
vendor/
  buildrbank/     the agent, copied verbatim. NEVER EDITED.
scripts/
  schema.sql      the 12 tables and 6 search functions
  seed-1-bank.sql, seed-2-knowledge.sql   the data
  seed.py         only needed if you change the embedding model
  check.py        tests each piece before you start the server
docs/             diagrams, and how it all fits together
```

Only three files are really ours. The rest is your Phase 1 work, untouched.

### Why the agent never notices

The agent keeps every setting in `vendor/buildrbank/config.py`, and normally
loads them itself. Its loader starts with "have I already been configured?" —
so `app/settings.py` fills that slot in first, and the agent finds the answer
waiting and skips its own loading entirely.

No subclassing, no patching, no fork. Delete `app/settings.py` and the agent
goes straight back to behaving exactly as it did in class.

---

## Honest limits

Carried over from Phase 1. Fine in a classroom, not fine on the open internet.

- **No login.** Whoever calls the API says who they are and is believed.
- **The procedures only narrate.** The agent will tell you your wire has been
  recalled. Nothing is written to the database.
- **One copy only.** Conversation memory is a file. Run a second server and the
  two will disagree about what you said.

That last one is not a bug to fix today. It is why the next session is about
databases.
