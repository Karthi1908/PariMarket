# agents/oracle_agent.py
"""
Oracle + Results Agent — fetches CoinGecko prices, resolves markets on-chain.
NOTE: instruction uses <angle_brackets> not {curly_braces} for placeholders.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from shared.config import GEMINI_MODEL
from shared.coingecko import get_price_at_timestamp
from shared.web3_utils import (
    contract, sign_and_send, ORACLE_PRIVATE_KEY,
    get_all_markets, get_market,
)

log = logging.getLogger(__name__)


def tool_pending_markets() -> list[dict]:
    """Return markets past resolution_time that are not yet resolved."""
    now     = int(time.time())
    markets = get_all_markets()
    return [
        {
            "market_id":       m["id"],
            "asset":           m["asset"],
            "question":        m["question"],
            "strike_price":    m["strike_price"],
            "resolution_time": m["resolution_time"],
            "resolution_utc":  datetime.fromtimestamp(
                m["resolution_time"], tz=timezone.utc
            ).isoformat(),
            "seconds_overdue": now - m["resolution_time"],
        }
        for m in markets
        if not m["is_resolved"]
        and not m["is_cancelled"]
        and now >= m["resolution_time"]
    ]


def tool_fetch_price(asset: str, resolution_timestamp: int) -> dict:
    """
    Fetch USD price of asset at resolution_timestamp from CoinGecko.
    Returns price_onchain = int(price_usd * 1e8) — pass this to tool_resolve_market.
    """
    try:
        price = get_price_at_timestamp(asset, resolution_timestamp)
        return {
            "asset":         asset,
            "price_usd":     price,
            "price_onchain": int(price * 1e8),
            "fetched_at":    int(time.time()),
        }
    except Exception as exc:
        log.error("tool_fetch_price(%s, %d): %s", asset, resolution_timestamp, exc)
        return {"error": str(exc), "asset": asset}


def tool_resolve_market(market_id: int, oracle_price_onchain: int) -> dict:
    """
    Post oracle price on-chain to resolve a market.
    Pre-checks resolution_time to avoid a costly revert.
    """
    now = int(time.time())
    try:
        m = get_market(market_id)
    except Exception as exc:
        return {"error": f"Cannot read market #{market_id}: {exc}"}

    if m["is_resolved"]:
        return {"error": f"Market #{market_id} is already resolved."}
    if m["is_cancelled"]:
        return {"error": f"Market #{market_id} is cancelled."}
    if now < m["resolution_time"]:
        return {"error": f"Market #{market_id} cannot be resolved yet — {m['resolution_time'] - now}s remaining."}

    try:
        tx = sign_and_send(
            contract.functions.resolve_market(market_id, oracle_price_onchain),
            ORACLE_PRIVATE_KEY, gas=250_000,
        )
    except Exception as exc:
        log.error("resolve_market(%d) tx failed: %s", market_id, exc)
        return {"error": str(exc)}

    try:
        resolved = get_market(market_id)
        outcome  = "YES" if resolved["outcome"] else "NO"
    except Exception as exc:
        log.warning("resolve_market(%d): tx OK but re-read failed: %s", market_id, exc)
        return {
            "market_id":        market_id,
            "outcome":          "unknown (re-read failed — check on-chain)",
            "oracle_price_usd": oracle_price_onchain / 1e8,
            "strike_price_usd": m["strike_price"],
            "tx_hash":          tx,
        }

    log.info("Resolved market #%d → %s  oracle=$%.2f  tx=%s",
             market_id, outcome, oracle_price_onchain / 1e8, tx)
    return {
        "market_id":        market_id,
        "outcome":          outcome,
        "oracle_price_usd": oracle_price_onchain / 1e8,
        "strike_price_usd": resolved["strike_price"],
        "tx_hash":          tx,
    }


def tool_build_announcement(market_id: int) -> dict:
    """Build a human-readable result announcement for a resolved market."""
    try:
        m = get_market(market_id)
    except Exception as exc:
        return {"error": str(exc)}
    if not m["is_resolved"]:
        return {"error": f"Market #{market_id} not resolved yet."}

    yes_u = m["yes_pool_usdc"]
    no_u  = m["no_pool_usdc"]
    total = yes_u + no_u
    win_p = yes_u if m["outcome"] else no_u
    mult  = (total / win_p * 0.97) if win_p > 0 else 0.0

    ann = (
        f"{'='*54}\n"
        f"MARKET #{market_id} RESOLVED - {m['asset']}\n"
        f"{'='*54}\n"
        f"Q: {m['question']}\n\n"
        f"Oracle : ${m['oracle_price']:>12,.2f}\n"
        f"Strike : ${m['strike_price']:>12,.2f}\n"
        f"Result : {'YES (price >= strike)' if m['outcome'] else 'NO (price < strike)'}\n\n"
        f"YES pool : ${yes_u:>10,.2f} USDC\n"
        f"NO  pool : ${no_u:>10,.2f} USDC\n"
        f"Total    : ${total:>10,.2f} USDC  ({m['total_bets']} bettors)\n\n"
        f"Payout multiplier : {mult:.4f}x  (net of 3% fee)\n"
        f"e.g. $100 stake returns ${100 * mult:,.2f}\n"
    )
    return {
        "market_id":         market_id,
        "outcome":           "YES" if m["outcome"] else "NO",
        "oracle_price_usd":  m["oracle_price"],
        "payout_multiplier": round(mult, 4),
        "announcement":      ann,
    }


oracle_agent = Agent(
    name="oracle_agent",
    model=GEMINI_MODEL,
    description="Resolves BTC/ETH prediction markets using CoinGecko closing prices.",
    instruction="""
You are the Oracle and Results Agent for PariMarket.

When invoked:

1. Call tool_pending_markets().
   If the list is empty, report "No markets pending resolution." and stop.

2. For each market in the pending list, in order:

   a. Call tool_fetch_price(asset=<market.asset>, resolution_timestamp=<market.resolution_time>).
      If the result contains an "error" key, log it and SKIP this market entirely.
      Record the price_onchain value (it is an integer — price in USD times 1e8).

   b. Call tool_resolve_market(market_id=<market.market_id>, oracle_price_onchain=<price_onchain value>).
      If the result contains an "error" key, log it and SKIP to the next market.
      Record the outcome and tx_hash.

   c. Call tool_build_announcement(market_id=<market.market_id>).
      Print the full announcement text verbatim.

3. Final summary:
   "Resolved N markets. Skipped M markets due to errors."
   List each resolved market ID with its outcome.
   List each skipped market ID with its error message.

CRITICAL:
- Always pass price_onchain (the integer) to tool_resolve_market, NEVER price_usd (the float).
- Process markets one at a time. Never skip step b after step a succeeds.
- If step a fails, do NOT call step b for that market.
""",
    tools=[
        FunctionTool(tool_pending_markets),
        FunctionTool(tool_fetch_price),
        FunctionTool(tool_resolve_market),
        FunctionTool(tool_build_announcement),
    ],
)