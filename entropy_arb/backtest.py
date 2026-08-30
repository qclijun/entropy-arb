"""Conservative minute-bar replay for the two-venue arbitrage strategy.

The recorder retains only each minute's final L1 bid/ask, not depth or
per-update timestamps. This module therefore treats every row as one
simultaneous, fully-fillable top-of-book snapshot. It reuses :func:`plan_arb`
for fee-aware sizing and mirrors Engine's thresholds, inventory ladder,
position caps, persistence, cooldown, and per-venue order budget.

It deliberately doesn't pretend to simulate queue position, partial fills,
funding, or minute-internal quote changes. Those require L2 / tick data.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from .book import ArbPlan, OrderBook, plan_arb
from .config import Config, VenueConf


class BacktestError(ValueError):
    """Raised when replay inputs cannot support a deterministic simulation."""


@dataclass(frozen=True)
class MinuteBar:
    """The final fresh L1 snapshot retained by one recorder minute."""

    minute_ts: int
    entropy_bid: float
    entropy_ask: float
    hedge_bid: float
    hedge_ask: float
    samples: int


@dataclass(frozen=True)
class BacktestTrade:
    minute_ts: int
    direction: str
    buy_venue: str
    sell_venue: str
    qty: float
    buy_px: float
    sell_px: float
    buy_notional: float
    sell_notional: float
    expected_edge_usd: float
    fill_edge_usd: float
    inventory_surcharge_bps: float
    entropy_position: float
    hedge_position: float


@dataclass(frozen=True)
class EquityPoint:
    minute_ts: int
    equity_usd: float


@dataclass
class BacktestResult:
    bars: int
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[EquityPoint] = field(default_factory=list)
    total_expected_edge_usd: float = 0.0
    total_fill_edge_usd: float = 0.0
    turnover_usd: float = 0.0
    entropy_position: float = 0.0
    hedge_position: float = 0.0
    entropy_cash: float = 0.0
    hedge_cash: float = 0.0
    final_equity_usd: float = 0.0
    max_drawdown_usd: float = 0.0


@dataclass
class _VenueState:
    conf: VenueConf
    bid: float = 0.0
    ask: float = 0.0
    position: float = 0.0
    cash: float = 0.0
    send_timestamps: List[int] = field(default_factory=list)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    def set_quote(self, bid: float, ask: float) -> None:
        self.bid, self.ask = bid, ask

    def book(self, depth_usd: float) -> OrderBook:
        """Build the one-level synthetic book that the minute data supports."""
        book = OrderBook()
        book.apply_hl([[{"px": str(self.bid), "sz": str(depth_usd / self.bid)}],
                       [{"px": str(self.ask), "sz": str(depth_usd / self.ask)}]])
        return book


def load_minute_bars(path: str, min_samples: int = 10) -> List[MinuteBar]:
    """Load strictly ordered, usable recorder rows from *path*.

    Rows with too few fresh samples are excluded. Malformed prices or time
    ordering are errors rather than silently changing the replay chronology.
    """
    if min_samples < 1:
        raise BacktestError("min_samples must be at least 1")
    bars: List[MinuteBar] = []
    previous_ts: Optional[int] = None
    try:
        fh = open(path, newline="")
    except FileNotFoundError as exc:
        raise BacktestError(f"{path} not found") from exc
    with fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            try:
                bar = MinuteBar(
                    minute_ts=int(row["minute_ts"]),
                    entropy_bid=float(row["entropy_bid"]),
                    entropy_ask=float(row["entropy_ask"]),
                    hedge_bid=float(row["hedge_bid"]),
                    hedge_ask=float(row["hedge_ask"]),
                    samples=int(row["samples"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise BacktestError(f"{path}:{line_no}: invalid recorder row") from exc
            if bar.samples < min_samples:
                continue
            if (bar.entropy_bid <= 0 or bar.entropy_ask <= 0
                    or bar.hedge_bid <= 0 or bar.hedge_ask <= 0
                    or bar.entropy_bid > bar.entropy_ask
                    or bar.hedge_bid > bar.hedge_ask):
                raise BacktestError(f"{path}:{line_no}: invalid bid/ask quote")
            if previous_ts is not None and bar.minute_ts <= previous_ts:
                raise BacktestError(f"{path}:{line_no}: minute_ts must be strictly increasing")
            previous_ts = bar.minute_ts
            bars.append(bar)
    return bars


def _inventory_surcharge_bps(cfg: Config, buy: _VenueState,
                             sell: _VenueState) -> float:
    """Mirror Engine._inv_add_bps using each venue's current L1 midpoint."""
    scale = cfg.inventory_scale_bps
    if scale <= 0:
        return 0.0
    floor = min(max(cfg.inventory_floor_frac, 0.0), 0.99)

    def ramp(venue: _VenueState, adding: bool) -> float:
        if not adding:
            return 0.0
        used = min(abs(venue.position) * venue.mid / venue.conf.cap_usd, 1.0)
        if used <= floor:
            return 0.0
        return scale * (used - floor) / (1.0 - floor)

    return max(ramp(buy, buy.position >= 0), ramp(sell, sell.position <= 0))


def _threshold_bps(cfg: Config, buy: _VenueState, sell: _VenueState) -> float:
    if sell.conf.key == "entropy":
        base = cfg.midline_bps + cfg.upper_bps
    else:
        base = cfg.lower_bps - cfg.midline_bps
    return base + _inventory_surcharge_bps(cfg, buy, sell)


def _headroom_usd(buy: _VenueState, sell: _VenueState, ref_px: float) -> float:
    """Mirror Engine._headroom; signed positions protect unwind capacity."""
    buy_headroom = buy.conf.cap_usd - buy.position * ref_px
    sell_headroom = sell.conf.cap_usd + sell.position * ref_px
    return min(buy_headroom, sell_headroom)


def _rate_ok(venue: _VenueState, now: int) -> bool:
    venue.send_timestamps[:] = [ts for ts in venue.send_timestamps
                                if now - ts <= 60]
    return len(venue.send_timestamps) < venue.conf.orders_per_min


def _plan(cfg: Config, buy: _VenueState, sell: _VenueState, depth_usd: float,
          cap_notional: float, min_base: float, size_step: float):
    return plan_arb(
        buy.book(depth_usd), sell.book(depth_usd),
        threshold_bps=_threshold_bps(cfg, buy, sell),
        buy_fee_bps=buy.conf.fee_bps,
        sell_fee_bps=sell.conf.fee_bps,
        take_fraction=cfg.take_fraction,
        cap_notional=cap_notional,
        min_base=min_base,
        min_notional=cfg.min_order_notional,
        size_step=size_step,
    )


def _equity(entropy: _VenueState, hedge: _VenueState) -> float:
    return (entropy.cash + entropy.position * entropy.mid
            + hedge.cash + hedge.position * hedge.mid)


def run_backtest(bars: Iterable[MinuteBar], cfg: Config, *,
                 assumed_depth_usd: Optional[float] = None,
                 extra_slippage_bps: float = 0.0,
                 size_step: float = 1e-4,
                 min_base: Optional[float] = None) -> BacktestResult:
    """Replay *bars* under the strategy settings in *cfg*.

    ``assumed_depth_usd`` is the synthetic L1 notional available at every bid
    and ask. If omitted, it is just sufficient for ``max_order_notional`` to
    bind after ``take_fraction``. ``extra_slippage_bps`` applies adverse
    symmetric slippage to both simulated fills.
    """
    if size_step <= 0:
        raise BacktestError("size_step must be > 0")
    if min_base is None:
        min_base = size_step
    if min_base <= 0:
        raise BacktestError("min_base must be > 0")
    if extra_slippage_bps < 0:
        raise BacktestError("extra_slippage_bps must be >= 0")
    if assumed_depth_usd is None:
        assumed_depth_usd = max(cfg.max_order_notional / cfg.take_fraction,
                                 cfg.min_order_notional)
    if assumed_depth_usd <= 0:
        raise BacktestError("assumed_depth_usd must be > 0")

    entropy = _VenueState(cfg.entropy)
    hedge = _VenueState(cfg.hedge)
    armed = {"sell_entropy": None, "buy_entropy": None}
    last_trade_ts: Optional[int] = None
    result = BacktestResult(bars=0)
    peak_equity = 0.0
    fill_slippage = extra_slippage_bps / 1e4

    for bar in bars:
        result.bars += 1
        entropy.set_quote(bar.entropy_bid, bar.entropy_ask)
        hedge.set_quote(bar.hedge_bid, bar.hedge_ask)

        best = None
        if (last_trade_ts is None
                or bar.minute_ts - last_trade_ts >= cfg.cooldown_sec):
            for buy, sell, direction in ((hedge, entropy, "sell_entropy"),
                                         (entropy, hedge, "buy_entropy")):
                if not (_rate_ok(buy, bar.minute_ts) and _rate_ok(sell, bar.minute_ts)):
                    continue
                plan, reason = _plan(cfg, buy, sell, assumed_depth_usd,
                                     cfg.max_order_notional, min_base, size_step)
                if reason in ("no_edge", "empty_book"):
                    armed[direction] = None
                    continue
                if armed[direction] is None:
                    armed[direction] = bar.minute_ts
                    # In production a zero-second gate schedules a follow-up
                    # evaluation on the same unchanged book. A bar snapshot
                    # uses that same convention only for a zero-second gate.
                    if cfg.premium_persist_sec > 0:
                        continue
                elif bar.minute_ts - armed[direction] < cfg.premium_persist_sec:
                    continue
                if plan is None:
                    continue
                headroom = _headroom_usd(buy, sell, plan.buy_limit)
                if headroom < plan.buy_notional:
                    plan, _ = _plan(cfg, buy, sell, assumed_depth_usd,
                                    min(cfg.max_order_notional, headroom),
                                    min_base, size_step)
                    if plan is None:
                        continue
                if best is None or plan.exp_edge_usd > best[3].exp_edge_usd:
                    best = (buy, sell, direction, plan)

        if best is not None:
            buy, sell, direction, plan = best
            surcharge = _inventory_surcharge_bps(cfg, buy, sell)
            buy_px = plan.buy_limit * (1.0 + fill_slippage)
            sell_px = plan.sell_limit * (1.0 - fill_slippage)
            buy_notional = plan.qty * buy_px
            sell_notional = plan.qty * sell_px
            buy_fee = buy.conf.fee_bps / 1e4
            sell_fee = sell.conf.fee_bps / 1e4
            fill_edge = sell_notional * (1.0 - sell_fee) - buy_notional * (1.0 + buy_fee)

            buy.position += plan.qty
            sell.position -= plan.qty
            buy.cash -= buy_notional * (1.0 + buy_fee)
            sell.cash += sell_notional * (1.0 - sell_fee)
            buy.send_timestamps.append(bar.minute_ts)
            sell.send_timestamps.append(bar.minute_ts)
            last_trade_ts = bar.minute_ts
            result.total_expected_edge_usd += plan.exp_edge_usd
            result.total_fill_edge_usd += fill_edge
            result.turnover_usd += buy_notional + sell_notional
            result.trades.append(BacktestTrade(
                minute_ts=bar.minute_ts,
                direction=direction,
                buy_venue=buy.conf.label,
                sell_venue=sell.conf.label,
                qty=plan.qty,
                buy_px=buy_px,
                sell_px=sell_px,
                buy_notional=buy_notional,
                sell_notional=sell_notional,
                expected_edge_usd=plan.exp_edge_usd,
                fill_edge_usd=fill_edge,
                inventory_surcharge_bps=surcharge,
                entropy_position=entropy.position,
                hedge_position=hedge.position,
            ))

        equity = _equity(entropy, hedge)
        peak_equity = max(peak_equity, equity)
        result.max_drawdown_usd = max(result.max_drawdown_usd, peak_equity - equity)
        result.equity_curve.append(EquityPoint(bar.minute_ts, equity))

    result.entropy_position = entropy.position
    result.hedge_position = hedge.position
    result.entropy_cash = entropy.cash
    result.hedge_cash = hedge.cash
    result.final_equity_usd = _equity(entropy, hedge) if result.bars else 0.0
    return result


TRADE_HEADER = [
    "minute_ts", "direction", "buy_venue", "sell_venue", "qty", "buy_px",
    "sell_px", "buy_notional", "sell_notional", "expected_edge_usd",
    "fill_edge_usd", "inventory_surcharge_bps", "entropy_position",
    "hedge_position",
]


def write_trades_csv(path: str, trades: Iterable[BacktestTrade]) -> None:
    """Write the simulated two-leg fill ledger to *path*."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(TRADE_HEADER)
        for trade in trades:
            writer.writerow([
                trade.minute_ts, trade.direction, trade.buy_venue,
                trade.sell_venue, f"{trade.qty:.10g}", f"{trade.buy_px:.10g}",
                f"{trade.sell_px:.10g}", f"{trade.buy_notional:.10g}",
                f"{trade.sell_notional:.10g}", f"{trade.expected_edge_usd:.10g}",
                f"{trade.fill_edge_usd:.10g}",
                f"{trade.inventory_surcharge_bps:.10g}",
                f"{trade.entropy_position:.10g}",
                f"{trade.hedge_position:.10g}",
            ])
