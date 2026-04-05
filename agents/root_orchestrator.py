# agents/root_orchestrator.py
"""
Root Orchestrator Agent
───────────────────────
The master Gemini agent that coordinates all sub-agents via AgentTool.

IMPORTANT — ADK instruction template escaping:
  ADK >= 1.x treats {variable} patterns inside instruction strings as session-state
  template variables and raises KeyError if they are not in the session context.
  All example placeholders in instructions use <angle_brackets> instead of {curly_braces}.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.tools.agent_tool import AgentTool

from shared.config import GEMINI_MODEL, RESOLUTION_HOUR_UTC
from shared.web3_utils import (
    get_all_markets, get_bettors, get_bet,
    timer_account, distribution_account, eth_balance,
)

from market_creation_agent import market_creation_agent
from oracle_agent          import oracle_agent
from operations_agent      import operations_agent

log = logging.getLogger(__name__)


# ── System snapshot ───────────────────────────────────────────────────────────

def tool_system_snapshot() -> dict:
    """
    Read the full protocol state in one call. Called first on every tick.
    All sub-agent dispatch decisions come from this snapshot alone.
    """
    now     = int(time.time())
    markets = get_all_markets()

    to_open:       list[int] = []
    to_close:      list[int] = []
    to_resolve:    list[int] = []
    to_distribute: list[int] = []
    btc_exists = False
    eth_exists = False

    # Must match market_creation_agent._next_resolution_utc() exactly
    next_resolution_ts = int(
        (datetime.now(timezone.utc) + timedelta(days=1))
        .replace(hour=RESOLUTION_HOUR_UTC, minute=0, second=0, microsecond=0)
        .timestamp()
    )

    for m in markets:
        mid = m["id"]

        if m["resolution_time"] == next_resolution_ts and not m["is_cancelled"]:
            if m["asset"] == "BTC":
                btc_exists = True
            elif m["asset"] == "ETH":
                eth_exists = True

        if m["is_resolved"] or m["is_cancelled"]:
            if m["is_resolved"]:
                for addr in get_bettors(mid):
                    bet = get_bet(addr, mid)
                    if (
                        bet["amount_raw"] > 0
                        and not bet["claimed"]
                        and bet["outcome"] == m["outcome"]
                    ):
                        to_distribute.append(mid)
                        break
            continue

        past_close = now >= m["close_time"]
        if not m["betting_open"] and not past_close:
            to_open.append(mid)
        elif m["betting_open"] and past_close:
            to_close.append(mid)

        if now >= m["resolution_time"]:
            to_resolve.append(mid)

    t_eth = eth_balance(timer_account().address)
    d_eth = eth_balance(distribution_account().address)

    return {
        "snapshot_time":                datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "markets_needing_timer_open":   to_open,
        "markets_needing_timer_close":  to_close,
        "markets_needing_resolution":   to_resolve,
        "markets_needing_distribution": to_distribute,
        "needs_btc_market":             not btc_exists,
        "needs_eth_market":             not eth_exists,
        "timer_wallet_eth":             round(t_eth, 6),
        "distribution_wallet_eth":      round(d_eth, 6),
        "low_gas":                      t_eth < 0.005 or d_eth < 0.005,
        "total_markets":                len(markets),
    }


def tool_log_tick(summary: dict) -> dict:
    """Write a structured JSON log entry for this tick."""
    log.info("TICK SUMMARY:\n%s", json.dumps(summary, indent=2, default=str))
    return {"logged": True, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Wrap sub-agents ───────────────────────────────────────────────────────────

operations_tool   = AgentTool(agent=operations_agent)
oracle_tool       = AgentTool(agent=oracle_agent)
creation_tool     = AgentTool(agent=market_creation_agent)


# ── Root agent ────────────────────────────────────────────────────────────────
# NOTE: All example placeholders use <angle_brackets> NOT {curly_braces}.
# ADK injects session-state variables for anything matching {var_name} in the
# instruction string and raises KeyError if the variable is not in the session.

root_agent = Agent(
    name="root_orchestrator",
    model=GEMINI_MODEL,
    description="Master orchestrator for the PariMarket pari-mutuel prediction market.",
    instruction="""
You are the Root Orchestrator for PariMarket.
You run every 5 minutes. Read state, then invoke the correct sub-agents in order.

STEP 1 — READ STATE (mandatory, always first)
Call tool_system_snapshot(). Read every field carefully before proceeding.

STEP 2 — GAS CHECK (always evaluate)
If snapshot field "low_gas" is true, include in your final report:
  WARNING LOW GAS: timer=<timer_wallet_eth> ETH, distribution=<distribution_wallet_eth> ETH
  Top up both wallets immediately.

STEP 3 — MARKET CREATION (only if needed)
If "needs_btc_market" OR "needs_eth_market" is true:
  Call market_creation_agent with this prompt (substitute real values from snapshot):
    "Create today's markets. needs_btc=<value of needs_btc_market>, needs_eth=<value of needs_eth_market>."
  Wait for the full response before continuing to Step 4

STEP 4 — OPERATIONS (only if needed)
If any of "markets_needing_timer_open", "markets_needing_timer_close", or "markets_needing_distribution" are non-empty lists:
  Call operations_agent with this prompt:
    "Process timing and distribution. 
     Open betting for: <list of IDs from markets_needing_timer_open>.
     Close betting for: <list of IDs from markets_needing_timer_close>.
     Distribute winnings for: <list of IDs from markets_needing_distribution>.
     Process all listed markets now."
  Wait for the full response before continuing to Step 5.

STEP 5 — ORACLE (only if needed)
If "markets_needing_resolution" is a non-empty list:
  Call oracle_agent with this prompt (substitute real IDs from snapshot):
    "These markets need resolution: <list of IDs from markets_needing_resolution>.
     Fetch CoinGecko prices and resolve each one on-chain now."
  Wait for the full response before continuing.

STEP 6 — LOG (mandatory, always last)
Call tool_log_tick() with a summary dict containing:
  tick_number: the integer from the trigger prompt
  snapshot_time: value from snapshot
  sub_agents_called: list of sub-agent names called in steps 3-5
  actions_taken: plain-English list of every action taken this tick
  errors: list of any error messages returned by sub-agents
  gas_warning: value of "low_gas" from snapshot

RULES:
1. ALWAYS call tool_system_snapshot() first — no exceptions.
2. Execute steps 3 through 6 strictly in order. Never start a later step before the current one finishes.
3. Only invoke a sub-agent if its condition is met (non-empty list or true flag).
4. If a sub-agent returns an error, add it to the errors list in step 6. Do NOT abort — continue.
5. tool_log_tick() MUST always be called last, even when nothing was done.
6. "No actions required this tick." is a perfectly valid and expected outcome.
""",
    tools=[
        FunctionTool(tool_system_snapshot),
        FunctionTool(tool_log_tick),
        operations_tool,
        oracle_tool,
        creation_tool,
    ],
)