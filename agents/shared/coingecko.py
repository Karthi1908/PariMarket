# agents/shared/coingecko.py
"""
CoinGecko price fetching — Synchronous wrapper over async MCP Server.

Uses threading + asyncio loop to execute MCP ClientSession calls 
because ADK tool functions run inside an already-owned event loop; 
asyncio.run() inside an ADK tool raises RuntimeError.
"""
from __future__ import annotations

import logging
import time
import threading
import asyncio
import json
from datetime import datetime, timezone

from .config import COINGECKO_API_KEY

from mcp import ClientSession
from mcp.client.sse import sse_client

log = logging.getLogger(__name__)

_COIN_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
}


def _run_mcp_query(tool_name: str, args: dict, retries: int = 4) -> dict:
    """
    Spawns a background thread to execute the async MCP client call.
    Includes retry logic for network timeouts or rate limits.
    """
    delay = 2.0
    last_exc: Exception | None = None

    # We use the public keyless MCP server over SSE
    # Note: If rate-limiting becomes an issue, one could pass PRO keys using env vars 
    # to the authenticated MCP server URL, but instructions specified keyless remote server.
    mcp_url = "https://mcp.api.coingecko.com/sse"

    async def _mcp_workflow() -> dict:
        async with sse_client(mcp_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.call_tool(tool_name, args)
                if not resp.content:
                    raise RuntimeError(f"MCP tool '{tool_name}' returned empty content.")
                # Assumes tool returns JSON-encoded output in text content
                return json.loads(resp.content[0].text)

    for attempt in range(retries):
        result_container: list[dict] = []
        exception_container: list[Exception] = []

        def _thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(_mcp_workflow())
                result_container.append(res)
            except Exception as exc:
                exception_container.append(exc)
            finally:
                loop.close()

        t = threading.Thread(target=_thread_target)
        t.start()
        t.join()

        if not exception_container:
            return result_container[0]

        exc = exception_container[0]
        # Very simple retry strategy:
        # A proper implementation inspects the exception for 429/timeout
        wait = delay * (2 ** attempt)
        log.warning(
            "MCP execution failed (%s) — sleeping %.0fs (attempt %d/%d)",
            exc, wait, attempt + 1, retries,
        )
        last_exc = exc
        time.sleep(wait)

    raise RuntimeError(
        f"MCP request failed after {retries} attempts for tool: {tool_name}"
    ) from last_exc


def get_current_prices() -> dict:
    """
    Fetch current USD prices for BTC and ETH.

    Returns:
        {
          "btc_usd":        float,
          "eth_usd":        float,
          "btc_24h_change": float,
          "eth_24h_change": float,
          "fetched_at":     int,   # unix timestamp
        }
    """
    data = _run_mcp_query("get_simple_price", {
        "ids": "bitcoin,ethereum",
        "vs_currencies": "usd",
        "include_24hr_change": "true"
    })

    return {
        "btc_usd":        float(data["bitcoin"]["usd"]),
        "eth_usd":        float(data["ethereum"]["usd"]),
        "btc_24h_change": float(data["bitcoin"].get("usd_24h_change", 0.0)),
        "eth_24h_change": float(data["ethereum"].get("usd_24h_change", 0.0)),
        "fetched_at":     int(time.time()),
    }


def get_price_at_timestamp(asset: str, target_ts: int) -> float:
    """
    Return the USD price of `asset` closest to `target_ts`.

    Strategy:
      1. get_range_coins_market_chart — minute-level data, ±5 min window.
      2. get_coins_history — daily close (fallback).

    Raises:
        ValueError  — unknown asset or no price data available.
        RuntimeError — network failure after all retries.
    """
    coin_id = _COIN_IDS.get(asset.upper())
    if not coin_id:
        raise ValueError(f"Unknown asset '{asset}'. Supported: BTC, ETH.")

    # Attempt 1: minute-resolution range
    try:
        data = _run_mcp_query("get_range_coins_market_chart", {
            "id": coin_id,
            "vs_currency": "usd",
            "from": str(target_ts - 300),
            "to": str(target_ts + 300)
        })
        prices = data.get("prices", [])          # [[ts_ms, price], ...]
        if prices:
            target_ms = target_ts * 1000
            closest   = min(prices, key=lambda p: abs(p[0] - target_ms))
            price     = float(closest[1])
            log.info("MCP range chart: %s @ ts=%d → $%.4f", asset, target_ts, price)
            return price
    except Exception as exc:
        log.warning("MCP range chart failed (%s) — falling back to history.", exc)

    # Attempt 2: daily history fallback
    dt_str = datetime.fromtimestamp(target_ts, tz=timezone.utc).strftime("%d-%m-%Y")
    try:
        data = _run_mcp_query("get_coins_history", {
            "id": coin_id,
            "date": dt_str,
            "localization": "false"
        })
        price = float(data["market_data"]["current_price"]["usd"])
        log.info("MCP history fallback: %s on %s → $%.4f", asset, dt_str, price)
        return price
    except Exception as exc:
        raise ValueError(f"No price data for {asset} at {dt_str}: {exc}") from exc
