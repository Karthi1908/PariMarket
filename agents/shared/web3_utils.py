# agents/shared/web3_utils.py
"""
Web3 / contract helpers shared by every agent.

ALL FUNCTIONS ARE SYNCHRONOUS.
ADK tool functions run inside an event loop owned by the framework.
Calling asyncio.run() inside a tool raises:
    RuntimeError: This event loop is already running

web3.py 7.x breaking changes handled here:
  - geth_poa_middleware removed → use ExtraDataToPOAMiddleware
  - signed.rawTransaction      → signed.raw_transaction
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from .config import (
    BASE_RPC_URL, BASE_CHAIN_ID,
    CONTRACT_ADDRESS,
    OWNER_PRIVATE_KEY, ORACLE_PRIVATE_KEY,
    TIMER_PRIVATE_KEY, DISTRIBUTION_PRIVATE_KEY,
    USDC_ADDRESS, USDC_DECIMALS,
)

log = logging.getLogger(__name__)

# ── ABI ───────────────────────────────────────────────────────────────────────

_ABI_PATH = Path(__file__).parent.parent / "abi.json"
with open(_ABI_PATH) as _f:
    CONTRACT_ABI: list = json.load(_f)

USDC_ABI: list = [
    {
        "name": "approve", "type": "function", "stateMutability": "nonpayable",
        "inputs":  [{"name": "spender", "type": "address"},
                    {"name": "amount",  "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance", "type": "function", "stateMutability": "view",
        "inputs":  [{"name": "owner",   "type": "address"},
                    {"name": "spender", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "balanceOf", "type": "function", "stateMutability": "view",
        "inputs":  [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# ── Web3 singletons ───────────────────────────────────────────────────────────

w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"timeout": 30}))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

contract = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACT_ADDRESS),
    abi=CONTRACT_ABI,
)
usdc_contract = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS),
    abi=USDC_ABI,
)

# ── RPC retry helper ──────────────────────────────────────────────────────────

def _call_with_retry(fn_call, retries: int = 3, delay: float = 2.0) -> Any:
    """
    Execute a web3 .call() with exponential back-off retry.

    Public Sepolia RPCs occasionally drop requests, returning 0 bytes which
    web3 raises as BadFunctionCallOutput. Retrying recovers from transient
    failures without needing a paid RPC endpoint.

    Always either returns a value or raises — never returns None.
    The explicit return type annotation and the trailing RuntimeError
    satisfy Pylance so callers are not typed as receiving Optional.
    """
    retries = max(retries, 1)   # guarantee at least one attempt

    for attempt in range(retries):
        try:
            result = fn_call.call()
            return result                           # explicit return of real value
        except Exception as exc:
            if attempt < retries - 1:
                wait = delay * (2 ** attempt)
                log.warning(
                    "RPC call failed (attempt %d/%d) — retrying in %.0fs: %s",
                    attempt + 1, retries, wait, exc,
                )
                time.sleep(wait)
            else:
                log.error("RPC call failed after %d attempts: %s", retries, exc)
                raise                               # re-raise live exception, never None

    # Unreachable: loop always returns or raises.
    # Present only so Pylance knows this path always terminates.
    raise RuntimeError("_call_with_retry: exhausted retries without result")


# ── Account helpers ───────────────────────────────────────────────────────────

def _acct(key: str):
    return w3.eth.account.from_key(key)

def owner_account():        return _acct(OWNER_PRIVATE_KEY)
def oracle_account():       return _acct(ORACLE_PRIVATE_KEY)
def timer_account():        return _acct(TIMER_PRIVATE_KEY)
def distribution_account(): return _acct(DISTRIBUTION_PRIVATE_KEY)

def eth_balance(address: str) -> float:
    """Return ETH balance of `address` as a plain Python float."""
    return float(w3.from_wei(
        w3.eth.get_balance(Web3.to_checksum_address(address)), "ether"
    ))


# ── Transaction helper ────────────────────────────────────────────────────────

def sign_and_send(fn_call, private_key: str, gas: int = 400_000) -> str:
    """
    Build, sign, and broadcast a contract transaction. Waits for receipt.

    Args:
        fn_call:     Built web3 contract call (e.g. contract.functions.foo(bar)).
        private_key: Hex private key of the sending wallet.
        gas:         Gas limit. Use 3_000_000 for batch_distribute.

    Returns:
        Transaction hash as a 0x-prefixed hex string.

    Raises:
        RuntimeError if the transaction reverts on-chain.
    """
    account   = _acct(private_key)
    gas_price = int(w3.eth.gas_price * 1.15)

    tx_opts = {
        "from":                 account.address,
        "nonce":                w3.eth.get_transaction_count(account.address, "pending"),
        "maxFeePerGas":         gas_price,
        "maxPriorityFeePerGas": max(gas_price // 10, 1),
        "chainId":              BASE_CHAIN_ID,
    }

    try:
        est = fn_call.estimate_gas(tx_opts)
        tx_opts["gas"] = int(est * 1.25)
    except Exception as e:
        log.warning("Gas estimation failed, using fallback %s: %s", gas, e)
        tx_opts["gas"] = gas

    tx = fn_call.build_transaction(tx_opts)
    signed  = w3.eth.account.sign_transaction(tx, private_key)
    # web3 7.x: renamed from rawTransaction → raw_transaction
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] != 1:
        raise RuntimeError(f"Transaction reverted. tx={tx_hash.hex()}")

    return tx_hash.hex()


# ── Market helpers ────────────────────────────────────────────────────────────

def get_market_count() -> int:
    return int(_call_with_retry(contract.functions.market_count()))


def parse_market(market_id: int, raw: tuple) -> dict:
    """
    Convert the raw tuple returned by get_market() into a typed dict.

    Struct field order (PariMutuelUSDC.vy — Market):
      0  asset            String[10]
      1  question         String[256]
      2  strike_price     uint256  (USD x 1e8)
      3  resolution_time  uint256  (unix ts)
      4  close_time       uint256  (unix ts)
      5  is_resolved      bool
      6  is_cancelled     bool
      7  betting_open     bool
      8  outcome          bool     (True = YES)
      9  yes_pool         uint256  (micro-USDC)
     10  no_pool          uint256  (micro-USDC)
     11  total_bets       uint256
     12  oracle_price     uint256  (USD x 1e8)
     13  created_at       uint256  (unix ts)
    """
    yes_usdc = int(raw[9])  / 10 ** USDC_DECIMALS
    no_usdc  = int(raw[10]) / 10 ** USDC_DECIMALS
    now      = int(time.time())

    if   raw[6]:                 status = "cancelled"
    elif raw[5]:                 status = "resolved"
    elif now >= int(raw[4]):     status = "closed"
    elif raw[7]:                 status = "live"
    else:                        status = "pending"

    return {
        "id":              market_id,
        "asset":           str(raw[0]),
        "question":        str(raw[1]),
        "strike_price":    int(raw[2]) / 1e8,
        "resolution_time": int(raw[3]),
        "close_time":      int(raw[4]),
        "is_resolved":     bool(raw[5]),
        "is_cancelled":    bool(raw[6]),
        "betting_open":    bool(raw[7]),
        "outcome":         bool(raw[8]),
        "yes_pool_usdc":   yes_usdc,
        "no_pool_usdc":    no_usdc,
        "total_pool_usdc": yes_usdc + no_usdc,
        "total_bets":      int(raw[11]),
        "oracle_price":    int(raw[12]) / 1e8,
        "created_at":      int(raw[13]),
        "status":          status,
    }


def get_market(market_id: int) -> dict:
    raw = _call_with_retry(contract.functions.get_market(market_id))
    return parse_market(market_id, raw)


def get_all_markets() -> list[dict]:
    count = get_market_count()
    return [get_market(i) for i in range(count)]


def get_bettors(market_id: int) -> list[str]:
    return list(_call_with_retry(contract.functions.get_bettors(market_id)))


def get_bet(bettor: str, market_id: int) -> dict:
    """Return a single bet as a typed dict."""
    raw = _call_with_retry(contract.functions.get_bet(bettor, market_id))
    return {
        "amount_raw":  int(raw[0]),
        "amount_usdc": int(raw[0]) / 10 ** USDC_DECIMALS,
        "outcome":     bool(raw[1]),
        "claimed":     bool(raw[2]),
        "placed_at":   int(raw[3]),
    }