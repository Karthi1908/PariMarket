#!/usr/bin/env python3
# scripts/deploy.py
"""
Compile PariMutuelUSDC.vy and deploy to any EVM chain.

Usage (from project root):
    python scripts/deploy.py --rpc-url <URL> --chain-id <ID>
    python scripts/deploy.py  # Falls back to .env values or Base Sepolia
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# ── sys.path guard ──────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_AGENTS_DIR   = _PROJECT_ROOT / "agents"
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))
# ────────────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

OWNER_KEY = os.environ.get("OWNER_PRIVATE_KEY", "")

ORACLE = os.getenv("ORACLE_ADDRESS",       "")
TIMER  = os.getenv("TIMER_ADDRESS",        "")
DIST   = os.getenv("DISTRIBUTION_ADDRESS", "")

CONTRACT_PATH = _PROJECT_ROOT / "contracts" / "PariMutuelUSDC.vy"
ABI_OUT       = _AGENTS_DIR   / "abi.json"


def compile_vyper(path: Path) -> tuple[str, list]:
    print(f"  Compiling {path.name} ...")
    bc  = subprocess.run(["vyper", "-f", "bytecode", str(path)], capture_output=True, text=True)
    abi = subprocess.run(["vyper", "-f", "abi",      str(path)], capture_output=True, text=True)
    if bc.returncode:  print("  ERROR (bytecode):\n", bc.stderr);  sys.exit(1)
    if abi.returncode: print("  ERROR (abi):\n", abi.stderr);       sys.exit(1)
    return bc.stdout.strip(), json.loads(abi.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy PariMutuelUSDC to any EVM chain")
    parser.add_argument("--rpc-url", type=str, help="RPC URL of the EVM chain", 
                        default=os.getenv("EVM_RPC_URL", os.getenv("SEPOLIA_RPC_URL", "https://rpc.sepolia.org")))
    parser.add_argument("--chain-id", type=int, help="Chain ID of the EVM chain",
                        default=int(os.getenv("EVM_CHAIN_ID", os.getenv("BASE_CHAIN_ID", 11155111))))
    args = parser.parse_args()

    rpc_url = args.rpc_url
    chain_id = args.chain_id

    if not OWNER_KEY:
        print("  ERROR: OWNER_PRIVATE_KEY not set in .env"); sys.exit(1)

    print(f"\n{'='*58}\n  PariMarket Deploy -> Chain ID: {chain_id}\n{'='*58}")

    bytecode, abi = compile_vyper(CONTRACT_PATH)
    print("  OK: compiled")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected():
        print(f"  ERROR: Cannot connect to {rpc_url}"); sys.exit(1)

    acct = w3.eth.account.from_key(OWNER_KEY)
    bal  = w3.eth.get_balance(acct.address)
    print(f"  Deployer : {acct.address}")
    print(f"  Balance  : {float(w3.from_wei(bal,'ether')):.6f} ETH")

    if bal < 5 * 10**14:
        print("  ERROR: Insufficient ETH for gas (need at least 0.0005 ETH).")
        sys.exit(1)

    oracle = ORACLE or acct.address
    timer  = TIMER  or acct.address
    dist   = DIST   or acct.address
    print(f"  Oracle={oracle}\n  Timer={timer}\n  Dist={dist}")

    Factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    gas_price = int(w3.eth.gas_price * 1.2)
    
    contract_tx = Factory.constructor(oracle, timer, dist)
    tx_opts = {
        "from": acct.address, 
        "nonce": w3.eth.get_transaction_count(acct.address),
        "maxFeePerGas": gas_price,
        "maxPriorityFeePerGas": gas_price // 10, 
        "chainId": chain_id,
    }
    
    try:
        est_gas = contract_tx.estimate_gas(tx_opts)
        tx_opts["gas"] = int(est_gas * 1.2)
        print(f"  Gas est  : {est_gas:,} (budgeting {tx_opts['gas']:,})")
    except Exception as e:
        print(f"  WARNING: Gas estimation failed, forcing high limit. ({e})")
        tx_opts["gas"] = 60_000_000

    tx = contract_tx.build_transaction(tx_opts)
    signed  = w3.eth.account.sign_transaction(tx, OWNER_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"\n  Tx: {tx_hash.hex()}\n  Waiting...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt["status"] != 1:
        print("  ERROR: Deployment REVERTED"); sys.exit(1)

    addr = receipt["contractAddress"]
    print(f"\n{'='*58}")
    print(f"  DEPLOYED: {addr}")
    print(f"  Block: {receipt['blockNumber']}  Gas: {receipt['gasUsed']:,}")
    print(f"{'='*58}")

    with open(ABI_OUT, "w") as f:
        json.dump(abi, f, indent=2)
    print(f"\n  ABI saved -> agents/abi.json")

    print(f"\n  Next steps:")
    print(f"  1. Add to .env:  CONTRACT_ADDRESS={addr}")
    print(f"  2. In frontend/index.html set:")
    print(f"     CONFIG.CONTRACT = '{addr}'")
    print(f"     CONFIG.CHAIN_ID = {chain_id}")
    print(f"     CONFIG.RPC = '{rpc_url}'")


if __name__ == "__main__":
    main()