# PariMarket — Pari-Mutuel Prediction Market on Etherlink Shadownet

A fully on-chain pari-mutuel prediction market for BTC and ETH price milestones,
denominated in **Custom-USDC**, deployed on **Etherlink Shadownet** blockchain, orchestrated by
**Google ADK + Gemini 2.0 Flash** AI agents, with a single-file **HTML/JS** frontend.

---

### 🚀 About PariMarket

PariMarket is a "self-driving" financial platform. Unlike traditional prediction markets that require manual management and complex order books, PariMarket combines **Pari-mutuel math** with **Google AI Orchestration** to create a fully autonomous experience.

#### 1. Core Functionality: The Pari-Mutuel Model
The project uses a **pari-mutuel** betting system (similar to horse racing). Instead of betting against a "bookie" with fixed odds, all users bet into a collective pool.
- **The Pool:** All USDC from "YES" and "NO" bets are combined into one pot.
- **The Payout:** When the market resolves, the winners split the total pot (minus a 3% protocol fee) proportionally to their stake.
- **The Odds:** Odds are dynamic. If everyone bets "YES," a "NO" bet becomes extremely lucrative because you'd be splitting a huge pot with very few other winners.

#### 2. Why it is better than existing markets (Polymarket, etc.)
- **Guaranteed Liquidity:** Unlike order-book markets (like Polymarket) that require market makers, PariMarket’s pari-mutuel model ensures you can **always** place a bet. Your stake simply adjusts the pool share.
- **100% Autonomous:** Most markets require human intervention for creation and resolution. PariMarket is **self-driving**—AI agents handle the entire lifecycle.
- **Immediate Data-Driven Resolution:** No complex "dispute" phases. Markets are resolved instantly by Oracle Agents using verified CoinGecko price data.
- **Low Friction:** A single, portable HTML frontend connects directly to the blockchain. No heavy infrastructure required.

#### 3. How the AI Agents run the system
The system is powered by a "squad" of AI agents built using the **Google Agent Development Kit (ADK)** and powered by **Gemini 2.0/2.5 Flash**. 
- **The Conductor (Root Orchestrator):** Wakes up every hour, takes a "snapshot" of the blockchain, and directs the sub-agents on what needs to be done.
- **The Strategist (Market Creation Agent):** Analyzes current BTC/ETH volatility using Gemini to set "challenging" strike prices that generate the most betting interest.
- **The Timekeeper (Operations Agent):** Manages the lifecycle, ensuring betting windows open and close on time to prevent cheating.
- **The Truth-Teller (Oracle Agent):** The bridge to the real world. Fetches historical price data from CoinGecko via MCP and signs the official on-chain result.

#### 4. Blockchain: The Single Source of Truth
PariMarket is built on the philosophy that **code is law**. The blockchain acts as the ultimate authority:
- **Irreversible Logic:** Once a bet is placed or a market is resolved, the action is permanent and recorded on the **Etherlink Shadownet** ledger. No human, not even the project owner, can "undo" a bet or change a payout.
- **Transparent Math:** The pari-mutuel calculations and fee deductions happen entirely within the Vyper smart contract. Anyone can verify the math on-chain to ensure fairness.
- **Trustless Execution:** You don't need to trust the AI agents to be "honest." The smart contract only allows the Oracle Agent to settle a market with specific, verifiable data, and the Distribution Agent can only send funds to the legitimate winners defined by the code.

---

## Table of Contents

1. [What it does](#1-what-it-does)
2. [Architecture overview](#2-architecture-overview)
3. [Prerequisites](#3-prerequisites)
4. [Project structure](#4-project-structure)
5. [Step 1 — Clone and configure](#5-step-1--clone-and-configure)
6. [Step 2 — Fund your wallets](#6-step-2--fund-your-wallets)
7. [Step 3 — Deploy the smart contract](#7-step-3--deploy-the-smart-contract)
8. [Step 4 — Configure agents and frontend](#8-step-4--configure-agents-and-frontend)
9. [Step 5 — Run agents locally](#9-step-5--run-agents-locally)
10. [Step 6 — Run the frontend locally](#10-step-6--run-the-frontend-locally)
11. [Step 7 — Test the full flow](#11-step-7--test-the-full-flow)
12. [Smart contract reference](#12-smart-contract-reference)
13. [Agent reference](#13-agent-reference)
14. [Bug fixes (v3)](#14-bug-fixes-v3)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. What it does

PariMarket creates daily prediction markets on BTC and ETH prices. Example market:

> **"Will BTC close above $70,000 at 22 Mar 2026 00:00 UTC?"**
> Options: **YES** or **NO**

Users bet USDC on either outcome. The total pool (YES bets + NO bets) is split among
winners proportionally to their stake, after a 3% protocol fee.

**Pari-mutuel formula:**
```
gross_payout = (your_stake / winning_pool) × total_pool
net_payout   = gross_payout × 0.97   (3% fee)
```

AI agents run autonomously: create markets, open/close betting windows, fetch
CoinGecko prices at resolution, settle outcomes on-chain, and push USDC to winners.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (frontend/index.html)                              │
│  Chakra Petch + IBM Plex Mono  ·  ethers.js v6              │
│  Markets grid  ·  Bet modal  ·  Profile / P&L                │
└────────────────────┬────────────────────────────────────────┘
                     │ JSON-RPC (ethers.js)
┌────────────────────▼────────────────────────────────────────┐
│  PariMutuelUSDC.vy  —  Vyper smart contract on Etherlink     │
│  USDC ERC-20  ·  Pari-mutuel maths  ·  role-gated agents    │
└──────┬────────────────────────────────────┬─────────────────┘
       │ web3.py                            │ CoinGecko REST
┌──────▼─────────────────────────┐  ┌──────▼──────────────────┐
│  Python Agents (Google ADK)    │  │  api.coingecko.com       │
│                                │  │  /simple/price           │
│  root_orchestrator (root)      │  │  /coins/{id}/market_chart│
│   ├─ FunctionTool: snapshot    │  │  /coins/{id}/history     │
│   ├─ AgentTool: timer_agent    │  └─────────────────────────┘
│   ├─ AgentTool: oracle_agent   │
│   ├─ AgentTool: dist_agent     │
│   └─ AgentTool: creation_agent │
└────────────────────────────────┘
```

---

## 3. Prerequisites

Install these before starting:

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.11 | https://python.org |
| Vyper | ≥ 0.3.10 | `pip install vyper` |
| Node.js | ≥ 18 (for a dev server) | https://nodejs.org |
| Git | any | https://git-scm.com |
| MetaMask | latest | https://metamask.io |

Verify:
```bash
python --version        # Python 3.11+
vyper --version         # 0.3.10+
node --version          # v18+
```

---

## 4. Project structure

```
parimarket/
├── contracts/
│   └── PariMutuelUSDC.vy        Vyper smart contract
├── agents/
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── config.py            env-var loader
│   │   ├── web3_utils.py        web3.py helpers (sync only)
│   │   └── coingecko.py         CoinGecko HTTP (sync only)
│   ├── market_creation_agent.py
│   ├── timer_agent.py
│   ├── oracle_agent.py
│   ├── distribution_agent.py
│   ├── root_orchestrator.py     root agent + AgentTool wrappers
│   ├── run_orchestrator.py      ← entry point: python run_orchestrator.py
│   ├── abi.json                 contract ABI (updated by deploy.py)
│   └── requirements.txt
├── frontend/
│   └── index.html               single-file frontend (no build step)
├── scripts/
│   ├── deploy.py                compile + deploy the Vyper contract
│   └── show_addresses.py        print wallet addresses from private keys
├── .env.sample                  ← copy this to .env
└── README.md
```

---

## 5. Step 1 — Clone and configure

```bash
# 1a. Clone the repo
git clone <your-repo-url> parimarket
cd parimarket

# 1b. Copy the sample env file
cp .env.sample .env
```

Now open `.env` in your editor and fill in the values. See comments in `.env.sample`
for guidance on each field.

**Minimum required values to get started:**
- `GOOGLE_API_KEY` — get free at https://aistudio.google.com/app/apikey
- Four `*_PRIVATE_KEY` values — see Step 2 below
- `CONTRACT_ADDRESS` — filled in after Step 3

---

## 6. Step 2 — Fund your wallets

The agents need **4 wallets** (can be the same wallet for local testing).

### Option A — Use a single wallet for all roles (easiest for local testing)

Generate one wallet and use the same private key for all four `*_PRIVATE_KEY` vars.

```bash
python3 -c "
from eth_account import Account
import secrets
acct = Account.from_key('0x' + secrets.token_hex(32))
print('Private key:', acct.key.hex())
print('Address    :', acct.address)
"
```

Set all four private keys to the output key in `.env`.

### Option B — Separate wallets per role (recommended for production)

Generate four wallets using the same command above, give each a distinct key.
Run `python scripts/show_addresses.py` after filling the `.env` to see addresses:

```bash
python scripts/show_addresses.py
```

### Fund with testnet XTZ

For **Etherlink Shadownet** (testnet), get free XTZ from:
- https://faucet.etherlink.com

Each wallet needs ≥ 1 XTZ for gas. Fund all four.

### Fund with testnet USDC (for test bets)

Etherlink Shadownet USDC: `0x32788465e7170898f1CcFA9065Fafb025c3c9A37`
Get it from the Etherlink faucet or mint via the contract.

---

## 7. Step 3 — Deploy the smart contract

### 7a. Install Python dependencies

```bash
cd agents
pip install -r requirements.txt
pip install vyper    # if not already installed
cd ..
```

### 7b. (Testnet only) Update the USDC address

The contract hardcodes Base mainnet USDC. For testnet, edit the constant:

```bash
# In contracts/PariMutuelUSDC.vy, change line:
USDC: constant(address) = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
# to:
USDC: constant(address) = 0x32788465e7170898f1CcFA9065Fafb025c3c9A37
```

### 7c. Set wallet addresses in .env

```bash
# Run this to get your addresses
python scripts/show_addresses.py

# Then add to .env:
ORACLE_ADDRESS=0x...
TIMER_ADDRESS=0x...
DISTRIBUTION_ADDRESS=0x...
```

### 7d. Deploy

```bash
# Etherlink Shadownet (testnet)
python scripts/deploy.py

# Etherlink Mainnet (when ready for production)
python scripts/deploy.py --mainnet
```

You will see output like:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PariMarket Deploy → Etherlink Shadownet (testnet)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✓ Compiled successfully
  ✓ Connected to Etherlink Shadownet (testnet)
  Deployer : 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
  Balance  : 0.050000 ETH
  ...
  ✅  Contract deployed!
      Address : 0xAbCd...1234
      Block   : 12345678
      Gas     : 1,234,567
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ── Next steps ──────────────────────────────────────────
  1. Add to .env:
     CONTRACT_ADDRESS=0xAbCd...1234

  2. Update frontend/index.html:
     CONFIG.CONTRACT = '0xAbCd...1234'
```

---

## 8. Step 4 — Configure agents and frontend

### 8a. Update `.env` with the contract address

```env
CONTRACT_ADDRESS=0xAbCd...1234   # paste from deploy output
BASE_CHAIN_ID=127823             # 127823 for Etherlink Shadownet
```

### 8b. Update frontend

Open `frontend/index.html` and edit the `CFG` object near the top:

```javascript
const CFG = {
  CONTRACT:  '0xAbCd...1234',              // ← paste contract address
  USDC:      '0x32788465e7170898f1CcFA9065Fafb025c3c9A37', // Shadownet USDC
  CHAIN_ID:  127823,                        // 127823 for Shadownet
  RPC:       'https://node.shadownet.etherlink.com',
  NETWORK:   'ETHERLINK SHADOWNET',
  // ...
};
```

---

## 9. Step 5 — Run agents locally

```bash
cd agents

# Install dependencies (if not done in Step 7a)
pip install -r requirements.txt

# Run the root orchestrator
python run_orchestrator.py
```

You should see:

```
  ╔══════════════════════════════════════════════════════╗
  ║        PariMarket Root Orchestrator                  ║
  ║        Google ADK + Gemini 2.0 Flash                 ║
  ╚══════════════════════════════════════════════════════╝

  Config OK — chain=127823  contract=0xAbCd...
  Tick interval : 300s

2025-01-15 10:00:00  INFO      runner     ─── Tick #1 ──────────────
2025-01-15 10:00:05  INFO      runner     Tick #1 done in 5.2s
2025-01-15 10:00:05  INFO      runner       └─ No actions required this tick.
2025-01-15 10:00:05  INFO      runner     Sleeping 300s…
```

### What the agents do each tick (every 5 minutes)

1. **Read state** — read all markets from chain
2. **Gas check** — warn if wallets are running low
3. **Timer** — open/close betting windows as needed
4. **Oracle** — fetch CoinGecko prices and resolve expired markets
5. **Distribution** — push USDC payouts to winners
6. **Market creation** — create today's BTC and ETH markets if missing
7. **Log** — write a structured JSON summary

### First run behaviour

On a fresh deployment with no markets, the first tick will:
- Create a BTC market and an ETH market (resolving at next midnight UTC)
- Open betting on both immediately

You will see something like:
```
Market creation agent: Created BTC market #0: "Will BTC close above $67,000 at 22 Jan 2025 00:00 UTC?"
Market creation agent: Created ETH market #1: "Will ETH close above $3,200 at 22 Jan 2025 00:00 UTC?"
Timer agent: Opened betting for market #0
Timer agent: Opened betting for market #1
```

---

## 10. Step 6 — Run the frontend locally

The frontend is a single HTML file — no build step needed. Serve it with any
static server:

```bash
cd frontend

# Option A: Python built-in server
python -m http.server 3000

# Option B: Node.js serve
npx serve . -p 3000

# Option C: VS Code Live Server extension
# Right-click index.html → Open with Live Server
```

Open your browser at **http://localhost:3000**

### Connecting your wallet

1. Open MetaMask
2. Add Etherlink Shadownet network:
   - Network name: Etherlink Shadownet
   - RPC URL: https://node.shadownet.etherlink.com
   - Chain ID: 127823
   - Currency: XTZ
   - Block explorer: https://explorer.shadownet.etherlink.com
3. Switch to Etherlink Shadownet in MetaMask
4. Click **CONNECT** in the PariMarket header
5. Approve the connection in MetaMask

### Placing a test bet

1. Make sure you have testnet USDC in your wallet
2. On the Markets page, find a LIVE market
3. Click **PLACE BET**
4. Choose YES or NO
5. Enter a USDC amount (minimum 1 USDC)
6. Click the BET button
7. MetaMask will prompt for two transactions:
   - First: **Approve USDC** (only needed once per wallet)
   - Second: **Place bet** (the actual bet)
8. After both confirm, your bet appears on the market card

---

## 11. Step 7 — Test the full flow

To see a complete market lifecycle locally (without waiting 24 hours), you can
create a short-duration test market manually using Python:

```python
# Run from agents/ directory
# python -c "..."
from shared.web3_utils import contract, sign_and_send, OWNER_PRIVATE_KEY
import time

now         = int(time.time())
res_ts      = now + 300    # resolves in 5 minutes
close_ts    = now + 60     # betting closes in 1 minute
strike      = 70000_00000000  # $70,000 × 1e8

tx = sign_and_send(
    contract.functions.create_market(
        "BTC",
        "Will BTC close above $70,000 at [test]?",
        strike, res_ts, close_ts
    ),
    OWNER_PRIVATE_KEY
)
print("Created test market, tx:", tx)
```

Then:
1. The timer agent will open betting within 5 minutes
2. Place a bet in the frontend
3. After 1 minute the timer agent closes betting
4. After 5 minutes the oracle agent resolves it with the CoinGecko price
5. After that the distribution agent pays out winners

---

## 12. Smart contract reference

**Contract:** `contracts/PariMutuelUSDC.vy`
**Network:** Etherlink (Shadownet `127823`)
**USDC decimals:** 6 (1 USDC = 1,000,000 micro-USDC)

### Role-gated functions

| Function | Who can call |
|----------|-------------|
| `create_market(...)` | owner or timer_agent |
| `open_betting(market_id)` | timer_agent or owner |
| `close_betting(market_id)` | timer_agent or owner |
| `resolve_market(market_id, oracle_price)` | oracle_agent or owner |
| `batch_distribute(market_id)` | distribution_agent or owner |
| `cancel_market(market_id)` | owner |
| `withdraw_commission()` | owner |
| `place_bet(market_id, outcome, amount)` | any user |
| `claim_winnings(market_id)` | any user (winners only) |
| `claim_refund(market_id)` | any user (cancelled markets) |

### Key invariants

- One bet per address per market
- Minimum bet: 1 USDC (1,000,000 micro-USDC)
- `open_betting` reverts if betting is already open (`ALREADY_OPEN`)
- `close_betting` reverts if betting is not open (`NOT_OPEN`)
- `resolve_market` force-closes betting before computing outcome
- Commission (3%) is deducted at claim/distribution time

---

## 13. Agent reference

### Root orchestrator (root_orchestrator.py)

Runs every 5 minutes. Reads `tool_system_snapshot()` then delegates to sub-agents
via `AgentTool` in this order: timer → oracle → distribution → market creation.

### MarketCreationAgent

- Fetches BTC/ETH prices from CoinGecko
- Rounds BTC to nearest $1,000, ETH to nearest $50
- Creates markets resolving at next midnight UTC
- Skips creation if today's markets already exist

### TimerAgent (has wallet)

- Scans all markets for timing actions
- Opens betting on new markets
- Closes betting when `close_time` is reached (2h before resolution)

### OracleAgent (has wallet)

- Finds markets past `resolution_time`
- Fetches closing price from CoinGecko `/market_chart/range` (falls back to `/history`)
- Posts `resolve_market(id, price × 1e8)` on-chain

### DistributionAgent (has wallet)

- Finds resolved markets with unclaimed winners
- Calls `batch_distribute(market_id)` to push USDC to all winners
- Gas: 3,000,000 limit (supports ~60 winners per market)

---

## 14. Bug fixes (v3)

| # | What was wrong | How it was fixed |
|---|---------------|-----------------|
| 1 | `open_betting` could be called twice silently | Added `assert not betting_open, "ALREADY_OPEN"` |
| 2 | `close_betting` had no guard against calling on closed market | Added `assert betting_open, "NOT_OPEN"` |
| 3 | `resolve_market` didn't close betting first — late bets could slip in | Added `self.markets[mid].betting_open = False` at start of resolve |
| 4 | `asyncio.run()` in tool functions → `RuntimeError: This event loop is already running` | All HTTP rewritten with synchronous `httpx.Client` |
| 5 | `_next_midnight_utc()` added 1 day unconditionally — wrong after midnight | Fixed to always return the next upcoming midnight |
| 6 | Walrus operator `:=` in generator always truthy — filter never worked | Replaced with explicit `for` loop + `break` |
| 7 | `batch_distribute` gas 600k — reverts with >12 bettors | Raised to 3,000,000 |
| 8 | Distribution check: N_markets × N_bettors RPC calls per tick | Short-circuit `break` at first unclaimed winner per market |
| 9 | Timer could call `open_betting` on already-open market → revert | Catches `ALREADY_OPEN` gracefully, returns `status: "already_open"` |
| 10 | Oracle sent resolve tx even when too early → expensive revert | Pre-checks `now >= resolution_time` before building tx |
| 11 | `AgentTool` import path wrong in some ADK versions | Uses `from google.adk.tools.agent_tool import AgentTool` |
| 12 | One sub-agent failure aborted entire orchestration tick | Each AgentTool call wrapped in try/except; errors logged, tick continues |

---

## 15. Troubleshooting

### "Missing required environment variable: CONTRACT_ADDRESS"
```
You haven't deployed the contract yet, or you forgot to add it to .env.
Run: python scripts/deploy.py
Then add CONTRACT_ADDRESS=0x... to .env
```

### "Cannot connect to RPC"
```
Check BASE_RPC_URL in .env. For Shadownet use:
BASE_RPC_URL=https://node.shadownet.etherlink.com
```

### "Insufficient ETH for gas" on deploy
```
Fund your deployer wallet with at least 1 XTZ.
Get free Shadownet XTZ: https://faucet.etherlink.com
```

### "USDC_TRANSFER_FAILED" when placing a bet
```
You need to hold testnet USDC and approve the contract to spend it.
The frontend handles approval automatically when you place a bet.
Make sure you have USDC in your wallet.
```

### "Transaction reverted: TOO_EARLY"
```
The oracle tried to resolve a market before its resolution_time.
This is a timing issue — the agent will retry on the next tick.
```

### "RuntimeError: This event loop is already running"
```
You have asyncio.run() inside a tool function.
All tool functions must be synchronous. Check shared/coingecko.py.
```

### CoinGecko rate limits
```
Free tier: ~30 requests/minute.
The agents use exponential backoff automatically.
If you hit limits often, set COINGECKO_API_KEY in .env.
Get a free API key at https://www.coingecko.com
```

### MetaMask won't connect
```
1. Make sure you're on Etherlink Shadownet (chain ID 127823)
2. Check that CFG.CHAIN_ID in index.html matches
3. Try refreshing the page
4. Check browser console for errors (F12)
```

### Markets not loading in frontend
```
1. Check that CFG.CONTRACT in index.html matches your deployed address
2. Make sure CFG.RPC points to the right network
3. Open browser console (F12) and look for errors
4. Verify the contract is deployed by checking on BaseScan
```

---

## License

MIT
