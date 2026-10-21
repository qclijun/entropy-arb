#!/usr/bin/env python3
"""Read-only venue cost lookups: account fee rates, funding history, size steps.

Public endpoints only; no credentials, no orders.

    python3 tools/venue_costs.py fees [--hl-address 0x...]
    python3 tools/venue_costs.py funding --symbol SNDK --hedge lighter-rh \
        --start 2026-10-17T00:00:00Z [--end ...] [--csv out.csv]
    python3 tools/venue_costs.py steps --symbol SNDK --hedge tradexyz

Fee formula for HIP-3 perps (Entropy = dex "io", trade.xyz = dex "xyz") follows
https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees (feeRates):
    taker = userCrossRate * hip3_scale * growth_scale * (1 - referral)
    hip3_scale = scale + 1 if scale < 1 else 2 * scale;  growth_scale = 0.1
Non-aligned collateral (USDC) is assumed. Lighter account tiers (Standard 0/0,
Plus, Premium) need an authenticated accountLimits call and are not queried.

Funding sign convention everywhere in this module: a positive rate means
longs pay shorts, as a fraction of notional per funding interval (1h).
Lighter /fundings returns an unsigned percent with direction; "long" is taken
to mean longs pay. Checked 2026-10-22 on SNDK hourly rates since 2026-10-10:
signed this way, Lighter and Lighter RH correlate 0.98/0.97 with trade.xyz
(same sign 96%), so the convention is empirically consistent.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entropy_arb.config import HEDGE_VENUES  # noqa: E402

HL_INFO = "https://api.hyperliquid.xyz/info"
LIGHTER_REST = {"lighter": "https://mainnet.zklighter.elliot.ai",
                "lighter-rh": "https://api.rh.lighter.xyz"}
HL_DEX = {"entropy": "io", "tradexyz": "xyz"}


def _get(url: str, body: Optional[dict] = None, timeout: float = 25.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


def hl_info(body: dict):
    return _get(HL_INFO, body)


# ---------------------------------------------------------------- fees

def hl_market(dex: str, symbol: str) -> dict:
    """meta universe entry for ``<dex>:<symbol>`` (szDecimals, fee scale, ...)."""
    name = f"{dex}:{symbol}"
    for asset in hl_info({"type": "meta", "dex": dex})["universe"]:
        if asset["name"] == name:
            return asset
    raise KeyError(name)


def hip3_rates_bps(cross: float, add: float, referral: float,
                   deployer_fee_scale: float, growth_mode: bool) -> Tuple[float, float]:
    """(taker, maker) in bps for a HIP-3 perp, non-aligned collateral."""
    scale = (deployer_fee_scale + 1 if deployer_fee_scale < 1
             else deployer_fee_scale * 2)
    growth = 0.1 if growth_mode else 1.0
    taker = cross * 1e4 * scale * growth * (1 - referral)
    maker = add * 1e4 * growth
    maker *= scale * (1 - referral) if maker > 0 else 1.0
    return taker, maker


def hl_fee_report(symbols: Sequence[str], address: Optional[str]) -> dict:
    user = address or "0x0000000000000000000000000000000000000000"
    fees = hl_info({"type": "userFees", "user": user})
    cross = float(fees["userCrossRate"])
    add = float(fees["userAddRate"])
    referral = float(fees.get("activeReferralDiscount") or 0.0)
    out = dict(address=address, source="userFees" if address else
               "userFees for zero address (no account given: default tier only)",
               user_cross_rate=cross, user_add_rate=add,
               referral_discount=referral, markets={})
    for venue, dex in HL_DEX.items():
        for sym in symbols:
            try:
                m = hl_market(dex, sym)
            except KeyError:
                continue
            growth = m.get("growthMode") == "enabled"
            scale = float(m.get("deployerFeeScale", 1.0))
            taker, maker = hip3_rates_bps(cross, add, referral, scale, growth)
            out["markets"][f"{dex}:{sym}"] = dict(
                venue=venue, deployer_fee_scale=scale, growth_mode=growth,
                taker_bps=round(taker, 4), maker_bps=round(maker, 4),
                sz_decimals=m["szDecimals"])
    return out


def lighter_markets(hedge: str) -> Dict[str, dict]:
    data = _get(LIGHTER_REST[hedge] + "/api/v1/orderBookDetails")
    out = {}
    for ob in data.get("order_book_details", []):
        out[ob["symbol"]] = dict(
            market_id=int(ob["market_id"]),
            size_decimals=int(ob["supported_size_decimals"]),
            min_base=float(ob["min_base_amount"]),
            taker_bps=float(ob["taker_fee"]) * 100,  # API gives percent
            maker_bps=float(ob["maker_fee"]) * 100)
    return out


# ---------------------------------------------------------------- funding

def hl_funding(coin: str, start: int, end: int) -> List[Tuple[int, float]]:
    """[(ts_sec, rate)] for an HL coin such as ``io:SNDK``; paginated."""
    out: List[Tuple[int, float]] = []
    cursor = start * 1000
    while cursor < end * 1000:
        page = hl_info({"type": "fundingHistory", "coin": coin,
                        "startTime": cursor, "endTime": end * 1000})
        if not page:
            break
        for row in page:
            out.append((int(row["time"]) // 1000, float(row["fundingRate"])))
        nxt = int(page[-1]["time"]) + 1
        if nxt <= cursor or len(page) < 500:
            break
        cursor = nxt
    return out


def lighter_funding(hedge: str, market_id: int, start: int,
                    end: int) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    step = 700 * 3600  # endpoint returns at most 750 rows per call
    lo = start
    while lo < end:
        hi = min(end, lo + step)
        url = (f"{LIGHTER_REST[hedge]}/api/v1/fundings?market_id={market_id}"
               f"&resolution=1h&start_timestamp={lo}&end_timestamp={hi}&count_back=0")
        for row in _get(url).get("fundings", []):
            sign = 1.0 if row["direction"] == "long" else -1.0
            out.append((int(row["timestamp"]), sign * float(row["rate"]) / 100))
        lo = hi
    return sorted(set(out))


def funding_series(venue: str, symbol: str, start: int,
                   end: int) -> List[Tuple[int, float]]:
    """venue: entropy | tradexyz | lighter | lighter-rh."""
    if venue in HL_DEX:
        return hl_funding(f"{HL_DEX[venue]}:{symbol}", start, end)
    market = lighter_markets(venue)[symbol]
    return lighter_funding(venue, market["market_id"], start, end)


def funding_pnl(positions: Sequence[Tuple[int, float]],
                prices: Sequence[Tuple[int, float]],
                rates: Iterable[Tuple[int, float]],
                start: int, end: int) -> Tuple[float, int]:
    """Cash received (+) / paid (-) by one leg over funding events in [start, end].

    positions: [(fill minute_ts, position after the fill)], ascending. A fill
    stamped at minute T happens at the end of that minute, so it is not yet
    held at a funding event at T. prices: [(minute_ts, mid)], ascending; the
    last price at or before the event is used. Returns (pnl, events charged).
    """
    pos_ts = [t for t, _ in positions]
    px_ts = [t for t, _ in prices]
    pnl = 0.0
    events = 0
    for t, rate in rates:
        if not start <= t <= end:
            continue
        i = bisect.bisect_left(pos_ts, t) - 1
        if i < 0 or positions[i][1] == 0:
            continue
        j = bisect.bisect_right(px_ts, t) - 1
        if j < 0:
            continue
        pnl -= positions[i][1] * prices[j][1] * rate
        events += 1
    return pnl, events


# ---------------------------------------------------------------- CLI

def parse_ts(text: Optional[str]) -> int:
    """ISO time (Z allowed) to unix seconds; None means now."""
    if not text:
        return int(time.time())
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())


def steps(symbol: str, hedge: str) -> dict:
    """Shared base step/min size across Entropy and the hedge leg."""
    e = hl_market("io", symbol)
    legs = {"entropy": dict(size_decimals=e["szDecimals"], min_base=None)}
    if hedge == "tradexyz":
        h = hl_market("xyz", symbol)
        legs["hedge"] = dict(size_decimals=h["szDecimals"], min_base=None)
    else:
        h = lighter_markets(hedge)[symbol]
        legs["hedge"] = dict(size_decimals=h["size_decimals"], min_base=h["min_base"])
    dec = min(v["size_decimals"] for v in legs.values())
    mins = [v["min_base"] for v in legs.values() if v["min_base"]]
    step = 10.0 ** -dec
    return dict(legs=legs, size_step=step,
                min_base=max(mins + [step]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fees", help="HIP-3 account fee rates + Lighter market fees")
    f.add_argument("--hl-address", help="Hyperliquid main account address (public)")
    f.add_argument("--symbols", default="SNDK,EWY,NBIS,DRAM,PRL,XIAOMI")
    g = sub.add_parser("funding", help="hourly funding for both legs of a pair")
    g.add_argument("--symbol", required=True)
    g.add_argument("--hedge", required=True,
                   choices=HEDGE_VENUES)
    g.add_argument("--start", required=True, help="ISO time, e.g. 2026-10-17T00:00:00Z")
    g.add_argument("--end", help="ISO time (default: now)")
    g.add_argument("--csv", help="write hourly rows here")
    s = sub.add_parser("steps", help="size step / min base for a pair")
    s.add_argument("--symbol", required=True)
    s.add_argument("--hedge", required=True,
                   choices=HEDGE_VENUES)
    args = ap.parse_args()

    if args.cmd == "fees":
        syms = [x.strip().upper() for x in args.symbols.split(",") if x.strip()]
        report = dict(hyperliquid=hl_fee_report(syms, args.hl_address), lighter={})
        for hedge in LIGHTER_REST:
            mk = lighter_markets(hedge)
            report["lighter"][hedge] = {
                sym: dict(market_taker_bps=mk[sym]["taker_bps"],
                          market_maker_bps=mk[sym]["maker_bps"])
                for sym in syms if sym in mk}
        report["lighter_note"] = ("market-level fees only; account tier "
                                  "(Standard 0/0, Plus, Premium) needs the "
                                  "authenticated /api/v1/accountLimits")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.cmd == "funding":
        start, end = parse_ts(args.start), parse_ts(args.end)
        legs = {"entropy": dict(funding_series("entropy", args.symbol, start, end)),
                "hedge": dict(funding_series(args.hedge, args.symbol, start, end))}
        hours = sorted(set(legs["entropy"]) | set(legs["hedge"]))
        rows = [dict(ts=t, time_utc=datetime.fromtimestamp(t, timezone.utc).isoformat(),
                     entropy_rate=legs["entropy"].get(t), hedge_rate=legs["hedge"].get(t))
                for t in hours]
        if args.csv:
            with open(args.csv, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["ts"])
                w.writeheader()
                w.writerows(rows)
        both = [r for r in rows if r["entropy_rate"] is not None
                and r["hedge_rate"] is not None]
        diff = [r["entropy_rate"] - r["hedge_rate"] for r in both]
        summary = dict(
            hours=len(rows), both_legs_hours=len(both),
            entropy_mean_bps_per_h=sum(legs["entropy"].values()) / max(len(legs["entropy"]), 1) * 1e4,
            hedge_mean_bps_per_h=sum(legs["hedge"].values()) / max(len(legs["hedge"]), 1) * 1e4,
            # short Entropy / long hedge receives entropy_rate - hedge_rate.
            short_entropy_long_hedge_bps_per_day=sum(diff) / max(len(diff), 1) * 24e4)
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(steps(args.symbol, args.hedge), indent=2))


if __name__ == "__main__":
    main()
