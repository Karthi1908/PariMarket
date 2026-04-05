# agents/operations_agent.py
"""
Operations Agent — Coordinates on-chain betting timer windows and distributions.
Combines previous Timer and Distribution Agents to reduce agent count.
NOTE: instruction uses <angle_brackets> not {curly_braces} for placeholders.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from shared.config import GEMINI_MODEL
from shared.web3_utils import (
    contract, sign_and_send, TIMER_PRIVATE_KEY, DISTRIBUTION_PRIVATE_KEY,
    get_all_markets, get_market, get_bettors, get_bet, timer_account,
    distribution_account, eth_balance,
)

log = logging.getLogger(__name__)


# ─── Timer Tools ─────────────────────────────────────────────────────────────

def tool_timer_wallet_info() -> dict:
    """Return ETH balance of the timer wallet."""
    acct = timer_account()
    bal  = eth_balance(acct.address)
    return {"address": acct.address, "eth_balance": round(bal, 6), "low_gas": bal < 0.005}


def tool_scan_markets() -> dict:
    """
    Scan all markets and return IDs that need betting opened or closed.
    to_open  → active, betting NOT open, now < close_time
    to_close → active, betting IS open,  now >= close_time
    """
    now     = int(time.time())
    markets = get_all_markets()
    to_open : list[int] = []
    to_close: list[int] = []

    for m in markets:
        if m["is_resolved"] or m["is_cancelled"]:
            continue
        if not m["betting_open"] and now < m["close_time"]:
            to_open.append(m["id"])
        elif m["betting_open"] and now >= m["close_time"]:
            to_close.append(m["id"])

    return {
        "to_open":  to_open,
        "to_close": to_close,
        "now_utc":  datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "total":    len(markets),
    }


def tool_open_betting(market_id: int) -> dict:
    """Open betting for one market. Returns status."""
    try:
        tx = sign_and_send(
            contract.functions.open_betting(market_id),
            TIMER_PRIVATE_KEY, gas=150_000,
        )
        log.info("Opened betting market #%d  tx=%s", market_id, tx)
        return {"market_id": market_id, "status": "opened", "tx_hash": tx}
    except Exception as exc:
        err = str(exc)
        if "ALREADY_OPEN" in err:
            log.warning("Market #%d already open — skipping.", market_id)
            return {"market_id": market_id, "status": "already_open", "tx_hash": ""}
        log.error("open_betting(%d) failed: %s", market_id, exc)
        return {"market_id": market_id, "status": "error", "error": err, "tx_hash": ""}


def tool_close_betting(market_id: int) -> dict:
    """Close betting for one market. Returns status."""
    try:
        tx = sign_and_send(
            contract.functions.close_betting(market_id),
            TIMER_PRIVATE_KEY, gas=150_000,
        )
        log.info("Closed betting market #%d  tx=%s", market_id, tx)
        return {"market_id": market_id, "status": "closed", "tx_hash": tx}
    except Exception as exc:
        err = str(exc)
        if "NOT_OPEN" in err:
            log.warning("Market #%d betting not open — skipping.", market_id)
            return {"market_id": market_id, "status": "not_open", "tx_hash": ""}
        log.error("close_betting(%d) failed: %s", market_id, exc)
        return {"market_id": market_id, "status": "error", "error": err, "tx_hash": ""}


# ─── Distribution Tools ──────────────────────────────────────────────────────

def tool_dist_wallet_info() -> dict:
    """Return ETH gas balance of the distribution wallet."""
    acct = distribution_account()
    bal  = eth_balance(acct.address)
    return {"address": acct.address, "eth_balance": round(bal, 6), "low_gas": bal < 0.005}


def tool_pending_distributions() -> list[dict]:
    """Find resolved markets with at least one unclaimed winner."""
    markets = get_all_markets()
    result: list[dict] = []

    for m in markets:
        if not m["is_resolved"] or m["is_cancelled"]:
            continue

        bettors         = get_bettors(m["id"])
        found_unclaimed = False

        for addr in bettors:
            bet = get_bet(addr, m["id"])
            if (
                bet["amount_raw"] > 0
                and not bet["claimed"]
                and bet["outcome"] == m["outcome"]
            ):
                found_unclaimed = True
                break

        if found_unclaimed:
            win_pool = m["yes_pool_usdc"] if m["outcome"] else m["no_pool_usdc"]
            result.append({
                "market_id":             m["id"],
                "asset":                 m["asset"],
                "outcome":               "YES" if m["outcome"] else "NO",
                "total_pool_usdc":       m["total_pool_usdc"],
                "win_pool_usdc":         win_pool,
                "has_unclaimed_winners": True,
            })

    return result


def tool_distribute(market_id: int) -> dict:
    """Trigger batch USDC distribution to all winners of one resolved market."""
    try:
        m = get_market(market_id)
    except Exception as exc:
        return {"error": f"Cannot read market #{market_id}: {exc}"}

    if not m["is_resolved"]:
        return {"error": f"Market #{market_id} not resolved."}
    if m["is_cancelled"]:
        return {"error": f"Market #{market_id} cancelled."}

    total       = m["total_pool_usdc"]
    win_pool    = m["yes_pool_usdc"] if m["outcome"] else m["no_pool_usdc"]
    commission  = total * 0.03 if win_pool > 0 else 0.0
    distributed = total - commission if win_pool > 0 else 0.0

    try:
        tx = sign_and_send(
            contract.functions.batch_distribute(market_id),
            DISTRIBUTION_PRIVATE_KEY,
            gas=3_000_000,
        )
    except Exception as exc:
        log.error("batch_distribute(%d) failed: %s", market_id, exc)
        return {"error": str(exc)}

    log.info("Distributed market #%d  $%.2f USDC  tx=%s", market_id, distributed, tx)
    return {
        "market_id":        market_id,
        "tx_hash":          tx,
        "outcome":          "YES" if m["outcome"] else "NO",
        "total_usdc":       round(total, 4),
        "distributed_usdc": round(distributed, 4),
        "commission_usdc":  round(commission, 4),
    }


operations_agent = Agent(
    name="operations_agent",
    model=GEMINI_MODEL,
    description="Manages market betting windows and distributes USDC winnings.",
    instruction="""
You are the Operations Agent for PariMarket. You handle both timer operations and prize distributions.

When invoked, execute the following sequence:

__TIMER OPERATIONS__:
1. Call tool_timer_wallet_info(). If low_gas is true, warn: "WARNING LOW GAS: timer wallet has <eth_balance> ETH".
2. Call tool_scan_markets() to get to_open and to_close lists.
3. For each market_id in to_open, call tool_open_betting(market_id). Log the outcome.
4. For each market_id in to_close, call tool_close_betting(market_id). Log the outcome.

__DISTRIBUTION OPERATIONS__:
5. Call tool_dist_wallet_info(). If low_gas is true, warn: "WARNING LOW GAS: dist wallet has <eth_balance> ETH".
6. Call tool_pending_distributions() to find resolved markets needing payouts.
7. For each market_id in the returned pending list, call tool_distribute(market_id). Log the results.

Rules:
- Process items one at a time.
- If a tool returns an error, log it and move to the next item.
- Return a single concise summary detailing opened markets, closed markets, and distributions completed.
""",
    tools=[
        FunctionTool(tool_timer_wallet_info),
        FunctionTool(tool_scan_markets),
        FunctionTool(tool_open_betting),
        FunctionTool(tool_close_betting),
        FunctionTool(tool_dist_wallet_info),
        FunctionTool(tool_pending_distributions),
        FunctionTool(tool_distribute),
    ],
)
