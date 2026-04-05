# agents/market_creation_agent.py
"""
Market Creation Agent — creates daily BTC/ETH prediction markets.
NOTE: instruction uses <angle_brackets> not {curly_braces} for placeholders.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from shared.config import GEMINI_MODEL, CLOSE_BEFORE_RESOLUTION_HOURS, RESOLUTION_HOUR_UTC
from shared.coingecko import get_current_prices
from shared.web3_utils import (
    contract, sign_and_send, w3,
    OWNER_PRIVATE_KEY, get_all_markets,
)

log = logging.getLogger(__name__)


def _next_resolution_utc() -> int:
    """Return unix timestamp of the next resolution time UTC (tomorrow at RESOLUTION_HOUR_UTC)."""
    now = datetime.now(timezone.utc)
    candidate = (now + timedelta(days=1)).replace(
        hour=RESOLUTION_HOUR_UTC, minute=0, second=0, microsecond=0
    )
    return int(candidate.timestamp())


def _round_btc(price: float) -> float:
    return float(round(price / 1_000) * 1_000)


def _round_eth(price: float) -> float:
    return float(round(price / 50) * 50)


def _market_id_from_receipt(tx_hash: str) -> int:
    """Parse MarketCreated event from receipt. Falls back to count-1 with warning."""
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        logs    = contract.events.MarketCreated().process_receipt(receipt)
        if logs:
            return int(logs[0]["args"]["market_id"])
    except Exception as exc:
        log.warning("Could not parse MarketCreated event (%s) — using count fallback", exc)
    from shared.web3_utils import get_market_count
    mid = get_market_count() - 1
    log.warning("Race-condition fallback: market_id=%d from count", mid)
    return mid


def tool_check_todays_markets() -> dict:
    """Check whether BTC/ETH markets exist for the next resolution time."""
    res_ts  = _next_resolution_utc()
    markets = get_all_markets()
    btc = any(
        m["asset"] == "BTC" and m["resolution_time"] == res_ts and not m["is_cancelled"]
        for m in markets
    )
    eth = any(
        m["asset"] == "ETH" and m["resolution_time"] == res_ts and not m["is_cancelled"]
        for m in markets
    )
    return {
        "btc_exists":     btc,
        "eth_exists":     eth,
        "resolution_ts":  res_ts,
        "resolution_utc": datetime.fromtimestamp(res_ts, tz=timezone.utc).isoformat(),
    }


def tool_get_prices() -> dict:
    """Fetch current BTC and ETH prices from CoinGecko."""
    try:
        return get_current_prices()
    except Exception as exc:
        log.error("get_current_prices failed: %s", exc)
        return {"error": str(exc)}


def tool_create_btc_market(strike_price_usd: float) -> dict:
    """Create a BTC/USD market. strike_price_usd is rounded to nearest $1,000."""
    strike       = _round_btc(strike_price_usd)
    res_ts       = _next_resolution_utc()
    close_ts     = res_ts - CLOSE_BEFORE_RESOLUTION_HOURS * 3_600
    strike_chain = int(strike * 1e8)
    res_dt       = datetime.fromtimestamp(res_ts, tz=timezone.utc)
    question     = f"Will BTC close above ${strike:,.0f} at {res_dt.strftime('%d %b %Y %H:%M')} UTC?"
    try:
        tx_hash = sign_and_send(
            contract.functions.create_market("BTC", question, strike_chain, res_ts, close_ts),
            OWNER_PRIVATE_KEY, gas=400_000,
        )
        mid = _market_id_from_receipt(tx_hash)
        log.info("Created BTC market #%s: %s", mid, question)
        return {"market_id": mid, "question": question, "tx_hash": tx_hash}
    except Exception as exc:
        log.error("tool_create_btc_market failed: %s", exc)
        return {"error": str(exc)}


def tool_create_eth_market(strike_price_usd: float) -> dict:
    """Create an ETH/USD market. strike_price_usd is rounded to nearest $50."""
    strike       = _round_eth(strike_price_usd)
    res_ts       = _next_resolution_utc()
    close_ts     = res_ts - CLOSE_BEFORE_RESOLUTION_HOURS * 3_600
    strike_chain = int(strike * 1e8)
    res_dt       = datetime.fromtimestamp(res_ts, tz=timezone.utc)
    question     = f"Will ETH close above ${strike:,.0f} at {res_dt.strftime('%d %b %Y %H:%M')} UTC?"
    try:
        tx_hash = sign_and_send(
            contract.functions.create_market("ETH", question, strike_chain, res_ts, close_ts),
            OWNER_PRIVATE_KEY, gas=400_000,
        )
        mid = _market_id_from_receipt(tx_hash)
        log.info("Created ETH market #%s: %s", mid, question)
        return {"market_id": mid, "question": question, "tx_hash": tx_hash}
    except Exception as exc:
        log.error("tool_create_eth_market failed: %s", exc)
        return {"error": str(exc)}


market_creation_agent = Agent(
    name="market_creation_agent",
    model=GEMINI_MODEL,
    description="Creates daily BTC and ETH price prediction markets on Ethereum.",
    instruction="""
You are the Market Creation Agent for PariMarket.

When invoked, follow these steps:

1. Call tool_check_todays_markets() to get btc_exists, eth_exists, and resolution_utc.

2. If BOTH btc_exists AND eth_exists are true:
   Report: "Both markets already exist for <resolution_utc value>. Nothing to do."
   STOP here. Do NOT call tool_get_prices().

3. If either btc_exists OR eth_exists is false:
   Call tool_get_prices().
   If it returns an error, report the error and STOP.

4. If btc_exists is false:
   Round the BTC price DOWN to the nearest $1,000 (example: $67,342 becomes $67,000).
   Call tool_create_btc_market(strike_price_usd=<the rounded value>).
   Log: market_id, question, tx_hash.

5. If eth_exists is false:
   Round the ETH price to the nearest $50 (example: $2,483 becomes $2,500).
   Call tool_create_eth_market(strike_price_usd=<the rounded value>).
   Log: market_id, question, tx_hash.

6. Report a final summary:
   Created: list of asset, market_id, question for each market created
   Skipped: assets that already existed
   Resolution time: the resolution_utc value from step 1

Rules:
- NEVER create a market if one already exists for the same asset and resolution_time.
- If a tool returns an error, log it and do not retry.
- Do not modify strike prices beyond the rounding rules above.
""",
    tools=[
        FunctionTool(tool_check_todays_markets),
        FunctionTool(tool_get_prices),
        FunctionTool(tool_create_btc_market),
        FunctionTool(tool_create_eth_market),
    ],
)