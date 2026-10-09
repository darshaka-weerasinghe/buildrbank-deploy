"""Executable runner specs for the six Week 6 SOPs.

Discovery lives in the database (mem_procedures + match_procedures, seeded in
Week 6). Execution lives here, versioned in code, joined by SOP name.

Step kinds the engine understands:
  collect  ask the customer for one slot        {"slot", "ask_for", "validate"}
  action   call a tool, save the result         {"tool", "args", "save_as"}
  branch   route on saved data                  {"on", "cases": {value: {...}}, "default"}
           each case: {"note": guidance for the voice, "end": bool, "escalate": bool}
  note     something the bank does/says         {"note"}  (no input, folded into next reply)
  confirm  yes/no gate before acting            {"slot", "ask_for"}
  close    finish + record episodic memory      {"summary"}

Arg values starting with "$" resolve from slots, saved action results, or the
customer context (e.g. "$ctx.email"). Branch "on" uses the same resolution, plus
the derived helper days_since(<path>).
"""

SOP_SPECS: dict[str, dict] = {

    "vip_wire_recall": {
        "title": "Recall an outgoing wire transfer",
        "steps": [
            {"kind": "action", "tool": "crm.get_customer_profile",
             "args": {"email": "$ctx.email"}, "save_as": "cust"},
            {"kind": "branch", "on": "$cust.segment", "cases": {
                "vip": {"note": "VIP status verified; the recall request is logged as URGENT "
                                "and the relationship manager is being notified."},
            }, "default": {"note": "Wire recall is a VIP service. For this account the bank "
                                   "logs a standard recall request instead, and the fastest "
                                   "path is contacting the recipient directly.",
                           "end": True}},
            {"kind": "collect", "slot": "wire_ref", "validate": "wire_ref",
             "ask_for": "the wire reference number (it looks like WIRE-12345)"},
            {"kind": "action", "tool": "crm.get_wire_status",
             "args": {"reference": "$wire_ref"}, "save_as": "wire"},
            {"kind": "branch", "on": "$wire.status", "cases": {
                "submitted":  {"note": "The wire has not been processed yet, so it can be cancelled."},
                "in_review":  {"note": "The wire is in compliance review and has not left the bank, "
                                        "so it can still be cancelled."},
                "processing": {"note": "The wire is processing but has not settled, "
                                        "so a cancellation can still be attempted."},
                "settled":    {"note": "The wire has settled at the recipient bank, so BuildrBank "
                                        "cannot recall it unilaterally. The path is to contact the "
                                        "recipient to arrange a refund; the bank can provide the "
                                        "transfer documentation.", "end": True},
            }, "default": {"note": "No wire was found for that reference.", "reask": "wire_ref"}},
            {"kind": "confirm", "slot": "confirmed",
             "ask_for": "confirmation to cancel this wire and refund the account"},
            {"kind": "close",
             "summary": "VIP wire recall for {wire_ref}: cancellation confirmed, refund initiated, "
                        "relationship manager notified, follow-up within 1 business day."},
        ],
    },

    "disputed_transaction": {
        "title": "Dispute a card or account transaction",
        "steps": [
            {"kind": "collect", "slot": "txn_ref", "validate": "any_ref",
             "ask_for": "the transaction reference from the app or statement"},
            {"kind": "action", "tool": "crm.find_transaction",
             "args": {"reference": "$txn_ref"}, "save_as": "tx"},
            {"kind": "branch", "on": "$tx.found", "cases": {
                "False": {"note": "No transaction was found for that reference.", "reask": "txn_ref"},
            }, "default": {"note": ""}},
            {"kind": "branch", "on": "days_since($tx.created_at) <= 60", "cases": {
                "True":  {"note": "The transaction is inside the 60-day dispute window."},
                "False": {"note": "The transaction is older than the 60-day dispute window, so a "
                                   "standard dispute cannot be filed. The case can go to the "
                                   "disputes team for a manual review instead.", "escalate": True},
            }},
            {"kind": "branch", "on": "$tx.tx_type", "cases": {
                "card_purchase": {"note": "Because this is a card transaction, the card is frozen "
                                          "immediately as a protective step."},
            }, "default": {"note": ""}},
            {"kind": "confirm", "slot": "confirmed",
             "ask_for": "confirmation to file the dispute"},
            {"kind": "close",
             "summary": "Dispute filed for {txn_ref}; card frozen if applicable; customer informed "
                        "of the 7-10 business day resolution timeline."},
        ],
    },

    "card_fraud_freeze": {
        "title": "Freeze a card and respond to suspected fraud",
        "steps": [
            {"kind": "collect", "slot": "card_last4", "validate": "last4",
             "ask_for": "the last 4 digits of the card"},
            {"kind": "note", "note": "The card is frozen IMMEDIATELY, before anything else. "
                                     "No new charges can go through."},
            {"kind": "action", "tool": "crm.get_customer_profile",
             "args": {"email": "$ctx.email"}, "save_as": "cust"},
            {"kind": "collect", "slot": "unauthorized", "validate": "free",
             "ask_for": "which recent charges look unauthorized (roughly when and how much)"},
            {"kind": "note", "note": "A fraud report is filed with the security team "
                                     "(security@buildrbank.lk). Unauthorized totals above "
                                     "LKR 100,000 escalate to the fraud team automatically."},
            {"kind": "collect", "slot": "replacement", "validate": "free",
             "ask_for": "which replacement to send: standard (LKR 500) or emergency same-day (LKR 1,500)"},
            {"kind": "close",
             "summary": "Card ending {card_last4} frozen for suspected fraud; report filed; "
                        "replacement requested ({replacement})."},
        ],
    },

    "kyc_reverification": {
        "title": "Re-verify KYC documents",
        "steps": [
            {"kind": "action", "tool": "crm.get_customer_profile",
             "args": {"email": "$ctx.email"}, "save_as": "cust"},
            {"kind": "branch", "on": "$cust.kyc_status", "cases": {
                "verified": {"note": "KYC is currently verified; no re-verification is required. "
                                     "Documents can still be refreshed voluntarily."},
            }, "default": {"note": "KYC needs re-verification to keep the account unrestricted."}},
            {"kind": "collect", "slot": "doc_type", "validate": "free",
             "ask_for": "which document to submit: NIC, passport, or driving licence"},
            {"kind": "note", "note": "A secure upload link is sent to the registered email; "
                                     "review takes 1-2 business days."},
            {"kind": "close",
             "summary": "KYC re-verification started with {doc_type}; upload link sent."},
        ],
    },

    "fd_early_withdrawal": {
        "title": "Withdraw a fixed deposit before maturity",
        "steps": [
            {"kind": "action", "tool": "knowledge.search_policy",
             "args": {"query": "fixed deposit early withdrawal penalty"}, "save_as": "policy"},
            {"kind": "note", "note": "Early withdrawal has a real cost: a penalty of 1% of the "
                                     "deposit plus forfeiture of interest for the current period. "
                                     "The exact policy text is quoted to the customer."},
            {"kind": "confirm", "slot": "confirmed",
             "ask_for": "confirmation to proceed with the early withdrawal despite the penalty"},
            {"kind": "close",
             "summary": "FD early withdrawal requested after penalty disclosure "
                        "(1% + interest forfeiture); processing initiated."},
        ],
    },

    "loan_approval": {
        "title": "Apply for a personal loan",
        "steps": [
            {"kind": "collect", "slot": "amount", "validate": "amount",
             "ask_for": "the loan amount in LKR (between 100,000 and 5,000,000)"},
            {"kind": "collect", "slot": "term_months", "validate": "months",
             "ask_for": "the repayment term in months (12 to 60)"},
            {"kind": "action", "tool": "knowledge.search_policy",
             "args": {"query": "personal loan amounts rates approval time"}, "save_as": "policy"},
            {"kind": "note", "note": "Personal loans run 12-18% p.a. based on credit score; "
                                     "approval typically takes 5-7 business days."},
            {"kind": "confirm", "slot": "confirmed",
             "ask_for": "confirmation to submit the application"},
            {"kind": "close",
             "summary": "Personal loan application submitted: LKR {amount} over {term_months} "
                        "months; decision expected in 5-7 business days."},
        ],
    },
}
