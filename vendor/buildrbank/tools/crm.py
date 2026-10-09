"""CRM tools — database reads over the live Week 6 backend.

These are the model-facing menu items. Docstrings are written for the model:
they double as MCP tool descriptions and as routing hints.
"""
from __future__ import annotations

from ..db import db
from ..observability import observe


@observe(as_type="tool")
def get_wire_status(reference: str) -> dict:
    """Look up a wire transfer by its reference (e.g. 'WIRE-30621'): status,
    amount, currency, and the account holder it belongs to."""
    tx = (db().table("transactions")
          .select("reference, tx_type, amount, currency, status, created_at, notes, "
                  "accounts(account_type, customers(full_name, segment))")
          .eq("reference", reference).execute())
    if not tx.data:
        return {"found": False, "reference": reference}
    return {"found": True, **tx.data[0]}


@observe(as_type="tool")
def get_customer_profile(email: str) -> dict:
    """Full profile for a customer by email: name, segment (retail/vip/business),
    KYC status, accounts with balances, recent transactions."""
    cust = (db().table("customers")
            .select("customer_id, full_name, email, segment, kyc_status, risk_profile, "
                    "accounts(account_id, account_type, balance, currency, "
                    "transactions(reference, tx_type, amount, currency, status, created_at))")
            .eq("email", email).execute())
    if not cust.data:
        return {"found": False, "email": email}
    return {"found": True, **cust.data[0]}


@observe(as_type="tool")
def find_transaction(reference: str) -> dict:
    """Look up any transaction (card purchase, wire, ATM, payment) by reference:
    amount, counterparty, status, and when it happened. Use for disputes."""
    tx = (db().table("transactions")
          .select("reference, tx_type, amount, currency, counterparty, status, created_at")
          .eq("reference", reference).execute())
    if not tx.data:
        return {"found": False, "reference": reference}
    return {"found": True, **tx.data[0]}
