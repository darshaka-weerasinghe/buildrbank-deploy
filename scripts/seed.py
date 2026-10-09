"""
Fill an empty Supabase project with the bank's data.

    python scripts/schema.sql   <- NO. Paste that one into the dashboard first.
    python scripts/seed.py      <- then run this.

WHY NOT JUST RUN THE COHORT'S NOTEBOOK?
---------------------------------------
Because of the embeddings. The handbook is stored as lists of numbers, and
you can only find a paragraph again if you search using the SAME model that
stored it. The Week 06 notebook stores them with Qwen, through Alibaba.
This app searches with OpenAI's small model, through OpenRouter.

Seed with one and search with the other and every policy question comes back
empty - with no error message to tell you why. So this script does exactly
what the notebook does, with the one model we actually run with.

Everything else - the customers, the accounts, WIRE-30621, the five
procedures, the chunk size - is copied from the notebook unchanged.

Safe to run more than once. It skips anything already there.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import settings                                      # noqa: E402

HANDBOOK = Path(__file__).parent / "data" / "bank_handbook.txt"
BATCH = 32          # how many pieces of text to embed per call


# --------------------------------------------------------------- the data
# Copied from Week 06 notebook 00_setup_supabase.ipynb, steps 5 and 6.

CUSTOMERS = [
    {"customer_id": "CUST-001", "full_name": "Isuru Alagiyawanna", "email": "isuru@example.com",
     "phone": "+94 77 123 4567", "segment": "vip", "risk_profile": "moderate"},
    {"customer_id": "CUST-002", "full_name": "Nehara Silva", "email": "nehara@example.com",
     "phone": "+94 71 987 6543", "segment": "retail", "risk_profile": "conservative"},
    {"customer_id": "CUST-004", "full_name": "Yasiru Perera", "email": "yasiru@example.com",
     "phone": "+94 76 555 1211", "segment": "retail", "risk_profile": "moderate"},
]

BRANCHES = [
    {"branch_id": "BR-COL-01", "name": "Colombo Fort Main", "address": "28 Galle Face Terrace",
     "city": "Colombo", "phone": "+94 11 234 5678", "extended_hours": True},
    {"branch_id": "BR-KAN-01", "name": "Kandy Central", "address": "12 Dalada Veediya",
     "city": "Kandy", "phone": "+94 81 222 3344", "extended_hours": True},
]

MANAGERS = [
    {"rm_id": "RM-001", "full_name": "Dinesh Fernando", "branch_id": "BR-COL-01",
     "email": "dinesh@buildrbank.lk", "phone": "+94 11 234 5680"},
    {"rm_id": "RM-002", "full_name": "Sanduni Jayawardena", "branch_id": "BR-KAN-01",
     "email": "sanduni@buildrbank.lk", "phone": "+94 81 222 3345"},
]

# NOTE - one correction to the notebook.
# The notebook gives ACC-100891 to "CUST-003", but no CUST-003 is ever
# created; the third customer is CUST-004 (Yasiru). The accounts table has a
# NOT NULL foreign key to customers, so the notebook's row cannot be
# inserted at all - it fails with a foreign key violation. Yasiru is plainly
# the intended owner (otherwise he has no account and no transactions), so
# the account is pointed at CUST-004 here.
ACCOUNTS = [
    {"account_id": "ACC-100234", "customer_id": "CUST-001", "account_type": "business_checking",
     "balance": 1250000.00, "currency": "LKR"},
    {"account_id": "ACC-100236", "customer_id": "CUST-001", "account_type": "fixed_deposit",
     "balance": 500000.00, "currency": "LKR"},
    {"account_id": "ACC-100567", "customer_id": "CUST-002", "account_type": "savings",
     "balance": 2340000.00, "currency": "LKR"},
    {"account_id": "ACC-100891", "customer_id": "CUST-004", "account_type": "checking",
     "balance": 456000.00, "currency": "LKR"},
]

# WIRE-30621 sitting at in_review is the storyline the whole demo runs on.
TRANSACTIONS = [
    {"tx_id": "WIRE-30621", "account_id": "ACC-100234", "tx_type": "wire_outgoing",
     "amount": 5000.00, "currency": "USD", "counterparty": "Nimal Perera / Sampath Bank",
     "status": "in_review", "reference": "WIRE-30621", "created_at": "2026-07-08T14:30:00+05:30",
     "notes": "Held for compliance review - exceeds LKR 1M equivalent"},
    {"tx_id": "TXN-30619", "account_id": "ACC-100234", "tx_type": "card_purchase",
     "amount": 12500.00, "currency": "LKR", "counterparty": "Cargills Food City",
     "status": "settled", "reference": "TXN-30619", "created_at": "2026-07-07T18:12:00+05:30",
     "notes": None},
    {"tx_id": "SAL-30618", "account_id": "ACC-100234", "tx_type": "salary_credit",
     "amount": 350000.00, "currency": "LKR", "counterparty": "BuildrLabs Ltd",
     "status": "settled", "reference": "SAL-30618", "created_at": "2026-07-05T09:00:00+05:30",
     "notes": None},
    {"tx_id": "WIRE-30525", "account_id": "ACC-100234", "tx_type": "wire_incoming",
     "amount": 2200.00, "currency": "USD", "counterparty": "Zuu Crew AI Consulting",
     "status": "settled", "reference": "WIRE-30525", "created_at": "2026-07-02T11:45:00+05:30",
     "notes": None},
    {"tx_id": "WIRE-30702", "account_id": "ACC-100567", "tx_type": "wire_incoming",
     "amount": 12000.00, "currency": "USD", "counterparty": "Overseas Tech Ltd",
     "status": "settled", "reference": "WIRE-30702", "created_at": "2026-07-06T10:20:00+05:30",
     "notes": None},
    {"tx_id": "LOAN-30628", "account_id": "ACC-100567", "tx_type": "loan_disbursement",
     "amount": 2000000.00, "currency": "LKR", "counterparty": "BuildrBank Personal Loan",
     "status": "settled", "reference": "LOAN-30628", "created_at": "2026-06-28T15:00:00+05:30",
     "notes": None},
    {"tx_id": "SAL-30619", "account_id": "ACC-100891", "tx_type": "salary_credit",
     "amount": 275000.00, "currency": "LKR", "counterparty": "Zuu Crew AI",
     "status": "settled", "reference": "SAL-30619", "created_at": "2026-07-05T09:00:00+05:30",
     "notes": None},
    {"tx_id": "UTL-30701", "account_id": "ACC-100891", "tx_type": "utility_payment",
     "amount": 4500.00, "currency": "LKR", "counterparty": "Water Board",
     "status": "settled", "reference": "UTL-30701", "created_at": "2026-07-01T08:30:00+05:30",
     "notes": None},
]

APPOINTMENTS = [
    {"appointment_id": "APT-001", "customer_id": "CUST-001", "rm_id": "RM-001",
     "branch_id": "BR-COL-01", "reason": "Wire recall discussion - WIRE-30621",
     "start_at": "2026-07-15T10:00:00+05:30", "end_at": "2026-07-15T10:30:00+05:30",
     "status": "confirmed"},
]

SOPS = [
    {"name": "vip_wire_recall",
     "description": "Recall or cancel an outgoing wire transfer for a VIP client",
     "context_when": "VIP customer asks to recall, cancel, or reverse a wire transfer they sent",
     "category": "payments",
     "steps": [
         {"step": 1, "action": "Verify the customer's VIP status via CRM (customers.segment = 'vip')"},
         {"step": 2, "action": "Log the recall request and mark it URGENT"},
         {"step": 3, "action": "Notify the assigned relationship manager immediately"},
         {"step": 4, "action": "Check wire state: recallable ONLY if status is submitted / in_review / processing - NOT settled"},
         {"step": 5, "action": "If recallable: cancel the wire, refund, confirm to customer. If settled: advise customer to contact the recipient bank directly"},
         {"step": 6, "action": "Follow up with the customer within 1 business day"},
     ]},
    {"name": "disputed_transaction",
     "description": "Handle a customer dispute of a card or account transaction",
     "context_when": "Customer says a transaction is wrong, unauthorized, or they want to dispute a charge",
     "category": "disputes",
     "steps": [
         {"step": 1, "action": "Verify customer identity"},
         {"step": 2, "action": "Locate the disputed transaction by reference"},
         {"step": 3, "action": "Check the dispute window: within 60 days of transaction date"},
         {"step": 4, "action": "If card transaction: freeze the card immediately"},
         {"step": 5, "action": "File the dispute with a reference number; VIP customers receive provisional credit"},
         {"step": 6, "action": "Notify customer of the 7-10 business day resolution timeline"},
     ]},
    {"name": "card_fraud_freeze",
     "description": "Freeze a card and respond to suspected fraud",
     "context_when": "Customer reports a lost/stolen card, unauthorized card activity, or suspected fraud",
     "category": "security",
     "steps": [
         {"step": 1, "action": "Freeze the card IMMEDIATELY - before any other step"},
         {"step": 2, "action": "Review recent transactions with the customer to identify unauthorized ones"},
         {"step": 3, "action": "File a fraud report with the security team (security@buildrbank.lk)"},
         {"step": 4, "action": "Issue replacement: standard LKR 500, emergency same-day LKR 1,500"},
         {"step": 5, "action": "Escalate to the fraud team if total unauthorized amount exceeds LKR 100,000"},
     ]},
    {"name": "kyc_reverification",
     "description": "Re-verify a customer's KYC documents when they expire",
     "context_when": "Customer's KYC status is expiring or expired, or compliance requests re-verification",
     "category": "compliance",
     "steps": [
         {"step": 1, "action": "Notify the customer their KYC verification is expiring"},
         {"step": 2, "action": "Collect updated government ID and proof of address (utility bill < 3 months)"},
         {"step": 3, "action": "Apply enhanced due diligence for VIP / high-net-worth customers"},
         {"step": 4, "action": "Update kyc_status in the CRM"},
         {"step": 5, "action": "Grace period: 30 days before account restrictions apply"},
     ]},
    {"name": "fd_early_withdrawal",
     "description": "Process an early withdrawal from a fixed deposit",
     "context_when": "Customer wants to break or withdraw a fixed deposit before its maturity date",
     "category": "deposits",
     "steps": [
         {"step": 1, "action": "Verify the customer owns the fixed deposit account"},
         {"step": 2, "action": "Quote the penalty: 1% of the deposit PLUS forfeiture of current-period interest"},
         {"step": 3, "action": "Get explicit customer confirmation of penalty acceptance"},
         {"step": 4, "action": "Process the withdrawal to the customer's linked account"},
         {"step": 5, "action": "Update the fixed deposit account status to closed"},
     ]},
    {"name": "loan_approval",
     "description": "Process and approve or escalate a customer's loan application",
     "context_when": "Customer applies for a loan (personal, home, auto, or business) or checks their loan application status",
     "category": "loans",
     "steps": [
         {"step": 1, "action": "Verify customer identity and check account status (must be active with no security holds)"},
         {"step": 2, "action": "Retrieve required documents: government ID, proof of income (last 3 months), and 3 months of bank statements"},
         {"step": 3, "action": "Perform a credit bureau check to obtain the customer's credit score"},
         {"step": 4, "action": "Calculate Debt-to-Income (DTI) ratio (gross monthly debt payments divided by gross monthly income; must be <= 40%)"},
         {"step": 5, "action": "Apply loan-specific rules: Personal Loan (< LKR 5,000,000, no collateral), Home Loan (< LKR 50,000,000, property valuation required), Business Loan (> LKR 10,000,000 requires Credit Committee escalation and collateral)"},
         {"step": 6, "action": "Upon approval: draft the loan agreement, obtain the customer's signature, and disburse the funds"},
     ]},
]


# --------------------------------------------------------------- helpers

def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    """Week 03's chunker, with one change: never cut a word in half.

    The original sliced at exactly `size` characters and ignored where words
    began and ended. That produced a chunk starting "rent period." - the tail
    of "...forfeiture of interest for the cur|rent period" - and when a
    customer asked about recall fees the agent read it back to them as though
    "rent period" were a banking term.

    Same size, same overlap, same idea. The cuts just move to the nearest
    space. Every chunk now begins at a word.
    """
    out: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # walk the cut back to the last space in the final quarter
            space = text.rfind(" ", end - size // 4, end)
            if space > start:
                end = space
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        # the next chunk starts ~overlap back, snapped forward to a word start
        nxt = max(end - overlap, start + 1)
        space = text.find(" ", nxt)
        start = space + 1 if (space != -1 and space < end) else end
    return out


def main() -> int:
    cfg = settings.configure()

    from openai import OpenAI
    from supabase import create_client

    print(f"  embedding with {cfg.embed_model} via OpenRouter")
    print(f"  writing to     {cfg.supabase_url}\n")

    sb = create_client(cfg.supabase_url, cfg.supabase_key)
    oai = OpenAI(api_key=cfg.qwen_api_key, base_url=cfg.embed_base_url)

    def embed_many(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            resp = oai.embeddings.create(
                model=cfg.embed_model, input=texts[i:i + BATCH], dimensions=cfg.embed_dim,
            )
            out.extend(d.embedding for d in resp.data)
        for v in out:
            assert len(v) == cfg.embed_dim, f"expected {cfg.embed_dim} numbers, got {len(v)}"
        return out

    def count(table: str) -> int:
        return sb.table(table).select("*", count="exact").limit(1).execute().count or 0

    # --- does the schema exist? ------------------------------------------
    try:
        count("customers")
    except Exception as e:
        print("  The tables do not exist yet.")
        print("  Open scripts/schema.sql, paste it into the Supabase")
        print("  dashboard (SQL Editor -> New query -> Run), then try again.\n")
        print(f"  ({type(e).__name__}: {str(e)[:120]})")
        return 1

    # --- the bank's own records ------------------------------------------
    print("1. CRM records")
    for table, rows, conflict in (
        ("customers", CUSTOMERS, "customer_id"),
        ("branches", BRANCHES, "branch_id"),
        ("relationship_managers", MANAGERS, "rm_id"),
        ("accounts", ACCOUNTS, "account_id"),
        ("transactions", TRANSACTIONS, "tx_id"),
        ("appointments", APPOINTMENTS, "appointment_id"),
    ):
        sb.table(table).upsert(rows, on_conflict=conflict).execute()
        print(f"     {table:<22} {len(rows)} rows")

    # --- the five procedures ---------------------------------------------
    print("\n2. Procedures (each needs an embedding, so the agent can find it)")
    if count("mem_procedures") >= len(SOPS):
        print(f"     already there ({count('mem_procedures')}) - skipped")
    else:
        texts = [f"{s['name']}: {s['description']}. When: {s['context_when']}" for s in SOPS]
        vectors = embed_many(texts)
        sb.table("mem_procedures").upsert(
            [{**s, "embedding": v} for s, v in zip(SOPS, vectors)], on_conflict="name",
        ).execute()
        print(f"     {len(SOPS)} procedures embedded and stored")

    # --- the handbook -----------------------------------------------------
    print("\n3. The handbook (this is what RAG searches)")
    if "--rechunk" in sys.argv and count("kb_chunks") > 0:
        sb.table("kb_chunks").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print(f"     --rechunk: cleared {count('kb_chunks')} old pieces")
    if count("kb_chunks") > 0:
        print(f"     already there ({count('kb_chunks')} pieces) - skipped")
        print("     To re-do it with a different model, empty kb_chunks first.")
    else:
        chunks = chunk_text(HANDBOOK.read_text(encoding="utf-8"))
        print(f"     cut into {len(chunks)} pieces, embedding...")
        vectors = embed_many(chunks)
        sb.table("kb_chunks").insert([
            {"source": "bank_handbook.txt", "chunk_index": i, "content": c, "embedding": v}
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ]).execute()
        print(f"     {len(chunks)} pieces stored")

    # --- prove the search works ------------------------------------------
    print("\n4. Testing a search")
    hits = sb.rpc("match_kb_chunks", {
        "query_embedding": embed_many(["what is the fee for a wire transfer?"])[0],
        "match_count": 2,
    }).execute()
    if not hits.data:
        print("     FAIL - search found nothing.")
        print("     The stored numbers do not match the search numbers.")
        return 1
    print(f'     found: "{hits.data[0]["content"][:70].strip()}..."')

    print("\nDone. Next:  python scripts/check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
