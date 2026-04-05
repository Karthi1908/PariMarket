#!/usr/bin/env python3
# scripts/show_addresses.py
"""
Print the wallet addresses derived from the private keys in .env.
Use the output to fill in ORACLE_ADDRESS, TIMER_ADDRESS, DISTRIBUTION_ADDRESS.

Usage (from project root):
    uv run addresses
    python scripts/show_addresses.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

# ── sys.path guard ────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_AGENTS_DIR   = _PROJECT_ROOT / "agents"
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))
# ─────────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from web3 import Web3

w3 = Web3()

ROLES = {
    "OWNER":        "OWNER_PRIVATE_KEY",
    "ORACLE":       "ORACLE_PRIVATE_KEY",
    "TIMER":        "TIMER_PRIVATE_KEY",
    "DISTRIBUTION": "DISTRIBUTION_PRIVATE_KEY",
}

print("\n  Addresses derived from private keys in .env\n")
print(f"  {'Role':<16}  Address")
print("  " + "-" * 56)
for role, env_key in ROLES.items():
    key = os.getenv(env_key, "")
    if not key:
        print(f"  {role:<16}  (not set — add {env_key} to .env)")
        continue
    try:
        addr = w3.eth.account.from_key(key).address
        print(f"  {role:<16}  {addr}")
    except Exception as e:
        print(f"  {role:<16}  ERROR: {e}")

print()
print("  Add these to your .env:")
print("    ORACLE_ADDRESS=0x...")
print("    TIMER_ADDRESS=0x...")
print("    DISTRIBUTION_ADDRESS=0x...")
print()
