"""
scripts/diagnose_contract.py
Run from project root:  python scripts/diagnose_contract.py
Tells you exactly why market_count() fails and what to do.
"""
import os, sys, json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_AGENTS_DIR   = _PROJECT_ROOT / "agents"
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

RPC      = os.getenv("BASE_RPC_URL", "https://rpc.sepolia.org")
CHAIN_ID = int(os.getenv("BASE_CHAIN_ID", "11155111"))
ADDR     = os.getenv("CONTRACT_ADDRESS", "")

print(f"\n{'='*60}")
print(f"  PariMarket Contract Diagnostics")
print(f"{'='*60}")
print(f"  CONTRACT : {ADDR}")
print(f"  RPC      : {RPC}")
print(f"  CHAIN_ID : {CHAIN_ID}")
print()

# ── 1. RPC connection ─────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC, request_kwargs={"timeout": 15}))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

if not w3.is_connected():
    print("❌  Cannot connect to RPC. Try alternative:")
    print("    BASE_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com")
    sys.exit(1)

actual_chain = w3.eth.chain_id
print(f"  RPC connected — block #{w3.eth.block_number}, chain_id={actual_chain}")
if actual_chain != CHAIN_ID:
    print(f"❌  CHAIN MISMATCH: .env says {CHAIN_ID} but RPC is chain {actual_chain}")
    sys.exit(1)
print(f"  Chain ID matches ✓")

# ── 2. Bytecode at address ─────────────────────────────────────────────────────
try:
    addr = Web3.to_checksum_address(ADDR)
except Exception as e:
    print(f"❌  Invalid CONTRACT_ADDRESS: {e}")
    sys.exit(1)

code = w3.eth.get_code(addr)
print(f"\n  Bytecode size at {addr}: {len(code)} bytes")

if len(code) <= 2:
    print("❌  NO BYTECODE — contract not deployed at this address on this chain")
    print()
    print("  SOLUTION: Redeploy the contract:")
    print("    1. pip install vyper==0.4.3")
    print("    2. python scripts/deploy.py")
    print("    3. Copy new CONTRACT_ADDRESS into .env")
    sys.exit(1)

print("  Bytecode exists ✓")

# ── 3. Raw eth_call for market_count() ────────────────────────────────────────
selector = w3.keccak(text="market_count()")[:4]
print(f"\n  Calling market_count() — selector: 0x{selector.hex()}")

result = w3.eth.call({"to": addr, "data": selector})
print(f"  Raw result: 0x{result.hex()} ({len(result)} bytes)")

if len(result) == 0:
    print()
    print("❌  SELECTOR MISMATCH — contract has bytecode but market_count() returns 0 bytes")
    print()
    print("  This means the deployed contract was compiled from DIFFERENT source code.")
    print("  The function selector 0x" + selector.hex() + " does not exist in the deployed bytecode.")
    print()
    print("  SOLUTION: Redeploy with the current Vyper 0.4.3 source:")
    print("    1. pip install vyper==0.4.3")
    print("    2. python scripts/deploy.py")
    print("    3. Copy new CONTRACT_ADDRESS into .env")
    sys.exit(1)

if len(result) == 32:
    count = int.from_bytes(result, "big")
    print(f"  market_count() = {count}  ✓ CONTRACT IS WORKING")
    print()
    print("✅  Contract is responding correctly!")
    print("   The error you're seeing must be intermittent RPC failure.")
    print("   Try switching to a more reliable RPC:")
    print("   BASE_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com")
else:
    print(f"❌  Unexpected response length: {len(result)} bytes")

print(f"\n{'='*60}\n")