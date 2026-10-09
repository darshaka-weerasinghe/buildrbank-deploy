"""BuildrBank CRM over MCP — a thin wrapper importing the shared tools.

The Week 9 rule still holds: clients launch this from THEIR directory, so we
bootstrap sys.path from __file__ before any package import.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # .../Week 11

from mcp.server.fastmcp import FastMCP

from buildrbank.tools import crm

mcp = FastMCP("buildrbank-crm")


@mcp.tool()
def get_wire_status(reference: str) -> str:
    """Look up a wire transfer by its reference (e.g. 'WIRE-30621'): status,
    amount, currency, and the account holder it belongs to."""
    return json.dumps(crm.get_wire_status(reference), default=str)


@mcp.tool()
def get_customer_profile(email: str) -> str:
    """Full profile for a BuildrBank customer by email: name, segment,
    KYC status, accounts with balances, recent transactions."""
    return json.dumps(crm.get_customer_profile(email), default=str)


@mcp.tool()
def find_transaction(reference: str) -> str:
    """Look up any transaction by reference: amount, counterparty, status,
    and when it happened. Use for disputes."""
    return json.dumps(crm.find_transaction(reference), default=str)


if __name__ == "__main__":
    mcp.run()
