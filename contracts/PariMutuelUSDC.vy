# pragma version ^0.4.3
# @title   PariMutuelUSDC
# @notice  Pari-mutuel prediction market denominated in USDC on Base blockchain.

interface IERC20:
    def transferFrom(_from: address, _to: address, _value: uint256) -> bool: nonpayable
    def transfer(_to: address, _value: uint256) -> bool: nonpayable
    def balanceOf(_owner: address) -> uint256: view

# ─── Constants ────────────────────────────────────────────────────────────────

USDC:         constant(address) = 0x32788465e7170898f1CcFA9065Fafb025c3c9A37
FEE_BPS:      constant(uint256) = 300
BASIS_POINTS: constant(uint256) = 10_000
MIN_BET:      constant(uint256) = 1_000_000
MAX_BETTORS:  constant(uint256) = 2_000

# ─── Events ───────────────────────────────────────────────────────────────────

event MarketCreated:
    market_id:       indexed(uint256)
    asset:           String[10]
    question:        String[256]
    strike_price:    uint256
    resolution_time: uint256
    close_time:      uint256

event BettingOpened:
    market_id: indexed(uint256)
    open_time: uint256

event BettingClosed:
    market_id:  indexed(uint256)
    close_time: uint256

event BetPlaced:
    market_id: indexed(uint256)
    bettor:    indexed(address)
    outcome:   bool
    amount:    uint256

event MarketResolved:
    market_id:    indexed(uint256)
    outcome:      bool
    oracle_price: uint256
    yes_pool:     uint256
    no_pool:      uint256
    total_bets:   uint256

event WinningsPaid:
    market_id: indexed(uint256)
    winner:    indexed(address)
    payout:    uint256

event MarketCancelled:
    market_id: indexed(uint256)

event RefundPaid:
    market_id: indexed(uint256)
    bettor:    indexed(address)
    amount:    uint256

event CommissionWithdrawn:
    amount: uint256
    to:     address

# ─── Structs ──────────────────────────────────────────────────────────────────

struct Market:
    asset:           String[10]
    question:        String[256]
    strike_price:    uint256
    resolution_time: uint256
    close_time:      uint256
    is_resolved:     bool
    is_cancelled:    bool
    betting_open:    bool
    outcome:         bool
    yes_pool:        uint256
    no_pool:         uint256
    total_bets:      uint256
    oracle_price:    uint256
    created_at:      uint256

struct Bet:
    amount:    uint256
    outcome:   bool
    claimed:   bool
    placed_at: uint256

# ─── Storage ──────────────────────────────────────────────────────────────────

owner:              public(address)
oracle_agent:       public(address)
timer_agent:        public(address)
distribution_agent: public(address)

markets:      public(HashMap[uint256, Market])
market_count: public(uint256)

bets:           public(HashMap[address, HashMap[uint256, Bet]])
market_bettors: HashMap[uint256, DynArray[address, MAX_BETTORS]]

pending_commission: public(uint256)

# ─── Constructor ──────────────────────────────────────────────────────────────

@deploy
def __init__(_oracle: address, _timer: address, _distribution: address):
    self.owner              = msg.sender
    self.oracle_agent       = _oracle
    self.timer_agent        = _timer
    self.distribution_agent = _distribution
    self.market_count       = 0

# ─── Internal auth guards ─────────────────────────────────────────────────────

@internal
def _only_owner():
    assert msg.sender == self.owner, "NOT_OWNER"

@internal
def _only_oracle():
    assert msg.sender == self.oracle_agent or msg.sender == self.owner, "NOT_ORACLE"

@internal
def _only_timer():
    assert msg.sender == self.timer_agent or msg.sender == self.owner, "NOT_TIMER"

@internal
def _only_distribution():
    assert msg.sender == self.distribution_agent or msg.sender == self.owner, "NOT_DIST"

# ─── Payout calculation ───────────────────────────────────────────────────────

@internal
@view
def _net_payout(market_id: uint256, bettor: address) -> uint256:
    bet: Bet    = self.bets[bettor][market_id]
    mkt: Market = self.markets[market_id]

    if bet.amount == 0 or bet.claimed or bet.outcome != mkt.outcome:
        return 0

    total:    uint256 = mkt.yes_pool + mkt.no_pool
    win_pool: uint256 = mkt.yes_pool if mkt.outcome else mkt.no_pool

    if win_pool == 0:
        return 0

    gross:      uint256 = (bet.amount * total) // win_pool
    commission: uint256 = (gross * FEE_BPS) // BASIS_POINTS
    return gross - commission

# ─── Market lifecycle ─────────────────────────────────────────────────────────

@external
def create_market(
    asset:           String[10],
    question:        String[256],
    strike_price:    uint256,
    resolution_time: uint256,
    close_time:      uint256,
) -> uint256:
    assert msg.sender == self.owner or msg.sender == self.timer_agent, "NOT_AUTH"
    assert resolution_time > block.timestamp, "RESOLUTION_IN_PAST"
    assert close_time      < resolution_time, "CLOSE_NOT_BEFORE_RESOLUTION"
    assert close_time      > block.timestamp, "CLOSE_IN_PAST"

    mid: uint256 = self.market_count
    self.markets[mid] = Market(
        asset=asset,
        question=question,
        strike_price=strike_price,
        resolution_time=resolution_time,
        close_time=close_time,
        is_resolved=False,
        is_cancelled=False,
        betting_open=False,
        outcome=False,
        yes_pool=0,
        no_pool=0,
        total_bets=0,
        oracle_price=0,
        created_at=block.timestamp,
    )
    self.market_count += 1

    log MarketCreated(
        market_id=mid,
        asset=asset,
        question=question,
        strike_price=strike_price,
        resolution_time=resolution_time,
        close_time=close_time,
    )
    return mid


@external
def open_betting(market_id: uint256):
    self._only_timer()
    assert market_id < self.market_count,                        "BAD_ID"
    assert not self.markets[market_id].is_resolved,              "RESOLVED"
    assert not self.markets[market_id].is_cancelled,             "CANCELLED"
    assert not self.markets[market_id].betting_open,             "ALREADY_OPEN"
    assert block.timestamp < self.markets[market_id].close_time, "PAST_CLOSE"

    self.markets[market_id].betting_open = True
    log BettingOpened(market_id=market_id, open_time=block.timestamp)


@external
def close_betting(market_id: uint256):
    self._only_timer()
    assert market_id < self.market_count,        "BAD_ID"
    assert self.markets[market_id].betting_open, "NOT_OPEN"

    self.markets[market_id].betting_open = False
    log BettingClosed(market_id=market_id, close_time=block.timestamp)

# ─── Betting ──────────────────────────────────────────────────────────────────

@external
def place_bet(market_id: uint256, outcome: bool, amount: uint256):
    assert market_id < self.market_count,                        "BAD_ID"
    assert self.markets[market_id].betting_open,                 "BETTING_CLOSED"
    assert not self.markets[market_id].is_resolved,              "ALREADY_RESOLVED"
    assert not self.markets[market_id].is_cancelled,             "CANCELLED"
    assert block.timestamp < self.markets[market_id].close_time, "PAST_CLOSE"
    assert amount >= MIN_BET,                                    "BELOW_MIN_BET"
    assert self.bets[msg.sender][market_id].amount == 0,         "ALREADY_BET"

    success: bool = extcall IERC20(USDC).transferFrom(msg.sender, self, amount)
    assert success, "USDC_TRANSFER_FAILED"

    if outcome:
        self.markets[market_id].yes_pool += amount
    else:
        self.markets[market_id].no_pool  += amount

    self.markets[market_id].total_bets += 1
    self.bets[msg.sender][market_id] = Bet(
        amount=amount,
        outcome=outcome,
        claimed=False,
        placed_at=block.timestamp,
    )
    self.market_bettors[market_id].append(msg.sender)

    log BetPlaced(market_id=market_id, bettor=msg.sender, outcome=outcome, amount=amount)

# ─── Oracle resolution ────────────────────────────────────────────────────────

@external
def resolve_market(market_id: uint256, oracle_price: uint256):
    self._only_oracle()
    assert market_id < self.market_count,            "BAD_ID"
    assert not self.markets[market_id].is_resolved,  "ALREADY_RESOLVED"
    assert not self.markets[market_id].is_cancelled, "CANCELLED"
    assert block.timestamp >= self.markets[market_id].resolution_time, "TOO_EARLY"

    self.markets[market_id].betting_open = False

    outcome: bool = oracle_price >= self.markets[market_id].strike_price

    self.markets[market_id].is_resolved  = True
    self.markets[market_id].outcome      = outcome
    self.markets[market_id].oracle_price = oracle_price

    log MarketResolved(
        market_id=market_id,
        outcome=outcome,
        oracle_price=oracle_price,
        yes_pool=self.markets[market_id].yes_pool,
        no_pool=self.markets[market_id].no_pool,
        total_bets=self.markets[market_id].total_bets,
    )

# ─── Claiming ─────────────────────────────────────────────────────────────────

@external
@view
def calculate_payout(market_id: uint256, bettor: address) -> uint256:
    return self._net_payout(market_id, bettor)


@external
def claim_winnings(market_id: uint256):
    assert market_id < self.market_count,       "BAD_ID"
    assert self.markets[market_id].is_resolved, "NOT_RESOLVED"

    bet: Bet = self.bets[msg.sender][market_id]
    assert bet.amount > 0,  "NO_BET_FOUND"
    assert not bet.claimed, "ALREADY_CLAIMED"
    assert bet.outcome == self.markets[market_id].outcome, "NOT_A_WINNER"

    payout: uint256 = self._net_payout(market_id, msg.sender)
    assert payout > 0, "ZERO_PAYOUT"

    mkt:      Market  = self.markets[market_id]
    win_pool: uint256 = mkt.yes_pool if mkt.outcome else mkt.no_pool
    total:    uint256 = mkt.yes_pool + mkt.no_pool
    gross:    uint256 = (bet.amount * total) // win_pool

    self.pending_commission                  += gross - payout
    self.bets[msg.sender][market_id].claimed  = True

    success: bool = extcall IERC20(USDC).transfer(msg.sender, payout)
    assert success, "USDC_TRANSFER_FAILED"

    log WinningsPaid(market_id=market_id, winner=msg.sender, payout=payout)


@external
def batch_distribute(market_id: uint256):
    self._only_distribution()
    assert market_id < self.market_count,       "BAD_ID"
    assert self.markets[market_id].is_resolved, "NOT_RESOLVED"

    mkt:      Market  = self.markets[market_id]
    win_pool: uint256 = mkt.yes_pool if mkt.outcome else mkt.no_pool

    if win_pool == 0:
        return

    total: uint256 = mkt.yes_pool + mkt.no_pool

    for bettor: address in self.market_bettors[market_id]:
        bet: Bet = self.bets[bettor][market_id]

        if bet.amount == 0 or bet.claimed or bet.outcome != mkt.outcome:
            continue

        gross:      uint256 = (bet.amount * total) // win_pool
        commission: uint256 = (gross * FEE_BPS) // BASIS_POINTS
        payout:     uint256 = gross - commission

        if payout == 0:
            continue

        self.pending_commission              += commission
        self.bets[bettor][market_id].claimed  = True

        success: bool = extcall IERC20(USDC).transfer(bettor, payout)
        assert success, "USDC_TRANSFER_FAILED"

        log WinningsPaid(market_id=market_id, winner=bettor, payout=payout)

# ─── Cancellation & refunds ───────────────────────────────────────────────────

@external
def cancel_market(market_id: uint256):
    self._only_owner()
    assert market_id < self.market_count,           "BAD_ID"
    assert not self.markets[market_id].is_resolved, "ALREADY_RESOLVED"

    self.markets[market_id].is_cancelled = True
    self.markets[market_id].betting_open = False
    log MarketCancelled(market_id=market_id)


@external
def claim_refund(market_id: uint256):
    assert self.markets[market_id].is_cancelled, "NOT_CANCELLED"

    bet: Bet = self.bets[msg.sender][market_id]
    assert bet.amount > 0 and not bet.claimed, "NOTHING_TO_REFUND"

    self.bets[msg.sender][market_id].claimed = True

    success: bool = extcall IERC20(USDC).transfer(msg.sender, bet.amount)
    assert success, "USDC_TRANSFER_FAILED"

    log RefundPaid(market_id=market_id, bettor=msg.sender, amount=bet.amount)

# ─── Commission withdrawal ────────────────────────────────────────────────────

@external
def withdraw_commission():
    self._only_owner()
    amount: uint256 = self.pending_commission
    assert amount > 0, "NO_COMMISSION"
    self.pending_commission = 0

    success: bool = extcall IERC20(USDC).transfer(self.owner, amount)
    assert success, "USDC_TRANSFER_FAILED"

    log CommissionWithdrawn(amount=amount, to=self.owner)

# ─── View helpers ─────────────────────────────────────────────────────────────

@external
@view
def get_market(market_id: uint256) -> Market:
    return self.markets[market_id]


@external
@view
def get_bet(bettor: address, market_id: uint256) -> Bet:
    return self.bets[bettor][market_id]


@external
@view
def get_bettors(market_id: uint256) -> DynArray[address, MAX_BETTORS]:
    return self.market_bettors[market_id]


@external
@view
def get_odds(market_id: uint256) -> (uint256, uint256):
    total: uint256 = self.markets[market_id].yes_pool + self.markets[market_id].no_pool
    if total == 0:
        return (5_000, 5_000)
    yes_bps: uint256 = (self.markets[market_id].yes_pool * BASIS_POINTS) // total
    return (yes_bps, BASIS_POINTS - yes_bps)


@external
@view
def is_accepting_bets(market_id: uint256) -> bool:
    m: Market = self.markets[market_id]
    return (
        m.betting_open
        and not m.is_resolved
        and not m.is_cancelled
        and block.timestamp < m.close_time
    )


@external
@view
def usdc_balance() -> uint256:
    return staticcall IERC20(USDC).balanceOf(self)

# ─── Admin ────────────────────────────────────────────────────────────────────

@external
def set_oracle(addr: address):
    self._only_owner()
    assert addr != empty(address), "ZERO_ADDRESS"
    self.oracle_agent = addr


@external
def set_timer(addr: address):
    self._only_owner()
    assert addr != empty(address), "ZERO_ADDRESS"
    self.timer_agent = addr


@external
def set_distribution(addr: address):
    self._only_owner()
    assert addr != empty(address), "ZERO_ADDRESS"
    self.distribution_agent = addr


@external
def transfer_ownership(new_owner: address):
    self._only_owner()
    assert new_owner != empty(address), "ZERO_ADDRESS"
    self.owner = new_owner