# agents/shared/config.py
"""
Centralised configuration — loaded once at import time from the .env file.
Call `validate()` at process startup to surface all problems before the first tick.

All bugs fixed in this version:
  1. _get() empty-string crash — os.getenv returns "" when key exists but blank.
     Fixed: `os.getenv(key) or default` treats absent and empty the same way.
  2. int(_get(...)) crashes on non-numeric or whitespace values.
     Fixed: _get_int() strips, validates, and provides a descriptive error.
  3. CLOSE_BEFORE_RESOLUTION_HOURS not range-validated — 0 or >=24 causes
     the Vyper contract to revert on market creation.
     Fixed: enforced [1, 23] via _get_int min_val/max_val.
  4. RESOLUTION_HOUR_UTC not range-validated — outside [0, 23] causes
     datetime.replace(hour=X) to raise ValueError at runtime.
     Fixed: enforced [0, 23] via _get_int min_val/max_val.
  5. validate() did not check CONTRACT_ADDRESS format or private key format.
     Fixed: added structural checks with actionable error messages.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Walk up:  agents/shared/ → agents/ → project root → find .env
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_ROOT / ".env", override=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(key: str, default: str = "") -> str:
    """
    Return the env-var value, or `default` when the key is absent OR blank.

    os.getenv(key, default) only applies `default` when the key is absent.
    If the key exists but is empty (e.g. `COINGECKO_API_KEY=` in .env),
    os.getenv returns "" and downstream int("") / api_call("") will crash.
    The `or default` operator treats both absent and blank as falsy.
    """
    return os.getenv(key) or default


def _require(key: str) -> str:
    """Return a mandatory env-var value; raise EnvironmentError if absent or blank."""
    val = (os.getenv(key) or "").strip()
    if not val:
        raise EnvironmentError(
            f"\n\n  Missing required environment variable: {key}\n"
            f"  Copy .env.sample to .env and fill in all values.\n"
        )
    return val


def _get_int(key: str, default: int,
             min_val: int | None = None,
             max_val: int | None = None) -> int:
    """
    Read an env-var as an integer with a default and optional range check.

    Handles every failure mode that plain int(_get(...)) misses:
      • Key present but blank  →  use default (not crash on int(""))
      • Value has whitespace   →  strip() before converting
      • Value is non-numeric   →  raise ValueError with the variable name
      • Value out of range     →  raise ValueError with [min, max] in message
    """
    raw = _get(key, str(default)).strip()
    try:
        val = int(raw)
    except ValueError:
        raise ValueError(
            f"Environment variable {key}={raw!r} must be an integer. "
            f"Check your .env file."
        ) from None
    if min_val is not None and val < min_val:
        raise ValueError(
            f"Environment variable {key}={val} is below the minimum "
            f"allowed value of {min_val}. Check your .env file."
        )
    if max_val is not None and val > max_val:
        raise ValueError(
            f"Environment variable {key}={val} exceeds the maximum "
            f"allowed value of {max_val}. Check your .env file."
        )
    return val


# ── Google AI ─────────────────────────────────────────────────────────────────

GOOGLE_API_KEY: str = _require("GOOGLE_API_KEY")
GEMINI_MODEL:   str = _get("GEMINI_MODEL", "gemini-2.0-flash")

# ── Base blockchain ───────────────────────────────────────────────────────────

BASE_RPC_URL:     str = _get("BASE_RPC_URL", "https://mainnet.base.org")
BASE_CHAIN_ID:    int = _get_int("BASE_CHAIN_ID", default=8453)
CONTRACT_ADDRESS: str = _require("CONTRACT_ADDRESS")

# ── Agent wallet private keys ─────────────────────────────────────────────────

OWNER_PRIVATE_KEY:        str = _require("OWNER_PRIVATE_KEY")
ORACLE_PRIVATE_KEY:       str = _require("ORACLE_PRIVATE_KEY")
TIMER_PRIVATE_KEY:        str = _require("TIMER_PRIVATE_KEY")
DISTRIBUTION_PRIVATE_KEY: str = _require("DISTRIBUTION_PRIVATE_KEY")

# ── USDC (hardcoded — Base mainnet) ──────────────────────────────────────────

USDC_ADDRESS:  str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_DECIMALS: int = 6

# ── CoinGecko ─────────────────────────────────────────────────────────────────

COINGECKO_API_KEY: str = _get("COINGECKO_API_KEY", "")    # empty → free tier
COINGECKO_BASE:    str = "https://api.coingecko.com/api/v3"

# ── Market parameters ─────────────────────────────────────────────────────────

# Betting closes this many hours before resolution_time.
# Valid range [1, 23]:
#   0  → close_ts == resolution_ts  → Vyper reverts CLOSE_NOT_BEFORE_RESOLUTION
#   ≥24 → close_ts < created_at    → Vyper reverts CLOSE_IN_PAST
CLOSE_BEFORE_RESOLUTION_HOURS: int = _get_int(
    "CLOSE_BEFORE_RESOLUTION_HOURS", default=2, min_val=1, max_val=23,
)

# UTC hour at which daily markets resolve (0 = midnight UTC).
# Valid range [0, 23]: outside this datetime.replace(hour=X) raises ValueError.
RESOLUTION_HOUR_UTC: int = _get_int(
    "RESOLUTION_HOUR_UTC", default=0, min_val=0, max_val=23,
)

# ── Scheduler ─────────────────────────────────────────────────────────────────

# Minimum 30 s: shorter intervals hammer the RPC and CoinGecko rate limit.
TICKER_INTERVAL_SECS: int = _get_int(
    "TICKER_INTERVAL_SECS", default=300, min_val=30,
)


# ── Startup validation ────────────────────────────────────────────────────────

def validate() -> None:
    """
    Verify all required env vars are present, all formats are correct, and all
    numeric values are in their valid ranges.

    Called once at process startup by run_orchestrator.py before the first tick.
    Raises EnvironmentError, ValueError, or AssertionError with a clear message.
    """
    # Re-check required strings (already read at import time, but explicit here
    # so this function is a self-contained correctness check)
    for key in [
        "GOOGLE_API_KEY", "CONTRACT_ADDRESS",
        "OWNER_PRIVATE_KEY", "ORACLE_PRIVATE_KEY",
        "TIMER_PRIVATE_KEY", "DISTRIBUTION_PRIVATE_KEY",
    ]:
        _require(key)

    # CONTRACT_ADDRESS: must be 0x + 40 hex chars, and not the zero placeholder
    addr = CONTRACT_ADDRESS.strip()
    if not (addr.startswith("0x") and len(addr) == 42):
        raise ValueError(
            f"CONTRACT_ADDRESS={addr!r} is not a valid Ethereum address "
            f"(expected 0x followed by 40 hex characters). Check your .env."
        )
    if addr.lower() == "0x" + "0" * 40:
        raise ValueError(
            "CONTRACT_ADDRESS is still the zero-address placeholder. "
            "Run `uv run deploy` to deploy the contract, then set CONTRACT_ADDRESS in .env."
        )

    # Private keys: must be 0x + 64 hex chars (32 bytes)
    for name, key in [
        ("OWNER_PRIVATE_KEY",        OWNER_PRIVATE_KEY),
        ("ORACLE_PRIVATE_KEY",       ORACLE_PRIVATE_KEY),
        ("TIMER_PRIVATE_KEY",        TIMER_PRIVATE_KEY),
        ("DISTRIBUTION_PRIVATE_KEY", DISTRIBUTION_PRIVATE_KEY),
    ]:
        hex_part = key.strip().removeprefix("0x")
        if len(hex_part) != 64 or not all(c in "0123456789abcdefABCDEF" for c in hex_part):
            raise ValueError(
                f"{name} is not a valid 32-byte hex private key "
                f"(expected 0x + 64 hex chars, got {len(hex_part)} hex chars). "
                f"Check your .env."
            )

    # Numeric ranges are enforced at import time by _get_int, but assert here
    # too so validate() gives a single deterministic pass/fail
    assert 1 <= CLOSE_BEFORE_RESOLUTION_HOURS <= 23, (
        f"CLOSE_BEFORE_RESOLUTION_HOURS={CLOSE_BEFORE_RESOLUTION_HOURS} out of [1, 23]"
    )
    assert 0 <= RESOLUTION_HOUR_UTC <= 23, (
        f"RESOLUTION_HOUR_UTC={RESOLUTION_HOUR_UTC} out of [0, 23]"
    )
    assert TICKER_INTERVAL_SECS >= 30, (
        f"TICKER_INTERVAL_SECS={TICKER_INTERVAL_SECS} is too small (minimum 30 s)"
    )

    print(
        f"  Config OK — chain={BASE_CHAIN_ID}  "
        f"contract={CONTRACT_ADDRESS[:10]}…  "
        f"model={GEMINI_MODEL}"
    )
