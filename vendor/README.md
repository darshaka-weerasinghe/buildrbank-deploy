# vendor/ — the students' agent, untouched

`buildrbank/` in this folder is a **verbatim copy** of the agent the cohort
built in Phase 1. It was taken straight out of git, not hand-copied:

```
git archive origin/week-11 "Week 11/buildrbank"
```

source commit: see `.source-commit`
source repo:   https://github.com/BuildrLabs-AI/agentic-ai-cohort-01-phase-01

## Do not edit anything in here

The whole point of this project is that deploying a system does not mean
rewriting it. Everything we needed to change — which models to call, which
provider, where the keys come from, where the memory file is written — is
done from the outside, in `app/settings.py`.

To prove nothing has drifted, from the repo folder:

```bash
./scripts/verify-vendor.sh
```

It hashes every `.py` file here and the same files straight out of git, and
tells you whether they match. (`__pycache__` is skipped — Python writes those
when it runs, and they are not source.)

Verified identical on the day this was built:
`3e12319e50578631ae1ef8764ca6d28cd2ad53ec`

## What is in here that we do not use

`buildrbank/mcp_servers/` — three small servers built in Week 9 so students
could call the bank from Claude Desktop. They are not part of the chat path
and nothing in `app/` imports them. They are left in place so the copy stays
faithful, but `mcp` is deliberately absent from `requirements.txt`.
