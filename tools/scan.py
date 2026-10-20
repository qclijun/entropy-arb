#!/usr/bin/env python3
"""Read-only opportunity scanner: Entropy (Hyperliquid `io` dex) vs the
supported hedge venues (Lighter mainnet, Lighter Robinhood, trade.xyz).

Discovers the eligible market universe from each venue's public catalog,
streams both legs' order books over the official websockets, and samples the
executable net edge (fees on BOTH legs included) at one or more USD notionals
across several rounds. It ranks candidates but never sends orders.

    .venv/bin/python tools/scan.py                    # full scan, defaults
    .venv/bin/python tools/scan.py --rounds 12 --interval 5
    .venv/bin/python tools/scan.py --notionals 1000,10000,50000

Direction convention: edge is quoted for "buy entropy + sell hedge" when
positive, "sell entropy + buy hedge" when negative.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from entropy_arb.book import OrderBook
from entropy_arb.feeds import HLBookFeed, LighterBookFeed

HL_API = "https://api.hyperliquid.xyz"
HL_WS = "wss://api.hyperliquid.xyz/ws"

LIGHTER_PROFILES = {
    "lighter": ("https://mainnet.zklighter.elliot.ai",
                "wss://mainnet.zklighter.elliot.ai/stream?readonly=true"),
    "lighter-rh": ("https://api.rh.lighter.xyz",
                   "wss://api.rh.lighter.xyz/stream?readonly=true"),
}

# taker fees, bps per leg (entropy: Growth Mode ~0.9bps, verified 2026-10-17)
FEE_ENTROPY_BPS = 0.9
FEE_BY_HEDGE = {"lighter": 0.0, "lighter-rh": 0.0, "tradexyz": 1.0}


# --------------------------------------------------------------- discovery

async def hl_meta(session: aiohttp.ClientSession, dex: str) -> list[dict]:
    async with session.post(HL_API + "/info", json={"type": "meta", "dex": dex},
                            timeout=aiohttp.ClientTimeout(total=15)) as r:
        r.raise_for_status()
        meta = await r.json()
    return [a for a in meta.get("universe", []) if not a.get("isDelisted")]


async def lighter_catalog(session: aiohttp.ClientSession, api_url: str) -> dict:
    async with session.get(api_url + "/api/v1/orderBooks",
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        r.raise_for_status()
        raw = await r.json()
    books = raw.get("order_books") if isinstance(raw, dict) else raw
    if not isinstance(books, list):
        books = list(books.values())
    out = {}
    for b in books:
        if b.get("status") not in (None, "active"):
            continue
        sym = b.get("symbol", "")
        base = sym.split("/")[0]          # 'LDO/USDC' -> 'LDO'
        out.setdefault(base, int(b["market_id"]))
    return out


@dataclass
class Pair:
    hedge: str            # venue key
    symbol: str
    hl_coin: str          # e.g. 'io:SNDK'
    lighter_market: int | None = None   # None for tradexyz


async def discover(session: aiohttp.ClientSession) -> list[Pair]:
    io, xyz = await asyncio.gather(hl_meta(session, "io"),
                                   hl_meta(session, "xyz"))
    cats = {k: await lighter_catalog(session, v[0]) for k, v in LIGHTER_PROFILES.items()}
    io_syms = {a["name"] for a in io}
    pairs: list[Pair] = []
    for hedge, cat in cats.items():
        for sym in sorted(io_syms & set(cat)):
            pairs.append(Pair(hedge, sym, f"io:{sym}", cat[sym]))
    xyz_syms = {a["name"] for a in xyz}
    for sym in sorted(io_syms & xyz_syms):
        pairs.append(Pair("tradexyz", sym, f"io:{sym}"))
    return pairs


# ------------------------------------------------------------------- books

@dataclass
class Leg:
    book: OrderBook = field(default_factory=OrderBook)


class Scanner:
    def __init__(self, pairs: list[Pair]) -> None:
        self.pairs = pairs
        self.entropy: dict[str, OrderBook] = {}      # hl_coin -> book
        self.lighter: dict[tuple[str, int], OrderBook] = {}  # (hedge, id) -> book
        self.stop = asyncio.Event()

    async def run_feeds(self) -> list:
        tasks = []
        hl_session = aiohttp.ClientSession()
        for coin in sorted({p.hl_coin for p in self.pairs}):
            book = OrderBook()
            self.entropy[coin] = book
            tasks.append(asyncio.create_task(
                HLBookFeed(f"entropy:{coin}", HL_WS, coin, book,
                           lambda: None).run(self.stop), name=f"hl-{coin}"))
        for hedge in ("lighter", "lighter-rh"):
            ms = [p for p in self.pairs if p.hedge == hedge and p.lighter_market is not None]
            if not ms:
                continue
            api, ws = LIGHTER_PROFILES[hedge]
            for p in ms:
                book = OrderBook()
                self.lighter[(hedge, p.lighter_market)] = book
                tasks.append(asyncio.create_task(
                    LighterBookFeed(f"{hedge}:{p.symbol}", ws, p.lighter_market,
                                    book, lambda: None).run(self.stop),
                    name=f"lt-{hedge}-{p.symbol}"))
        return tasks


# ------------------------------------------------------------------- edges

def walk(levels, qty: float):
    """Return (vwap, filled_qty) walking a sorted book to qty."""
    rem, notional, filled = qty, 0.0, 0.0
    for px, sz in levels:
        take = min(rem, sz)
        notional += take * px
        filled += take
        rem -= take
        if rem <= 1e-12:
            break
    return (notional / filled if filled > 0 else 0.0), filled


def edge_bps(buy_book: OrderBook, sell_book: OrderBook, notional_usd: float,
             buy_fee: float, sell_fee: float):
    """Net edge (bps of buy notional) for buy@buy_book / sell@sell_book at a
    target USD notional. Returns (edge_bps, filled_notional) or None if
    either leg lacks a top or depth collapses to dust."""
    asks, bids = buy_book.sorted_asks(), sell_book.sorted_bids()
    if not asks or not bids:
        return None
    qty = notional_usd / asks[0][0]
    buy_vwap, filled_b = walk(asks, qty)
    sell_vwap, filled_s = walk(bids, qty)
    filled = min(filled_b, filled_s)
    if filled * buy_vwap < 10.0:          # dust — not executable
        return None
    bn, sn = filled * buy_vwap, filled * sell_vwap
    net = sn * (1.0 - sell_fee) - bn * (1.0 + buy_fee)
    return net / bn * 1e4, bn


# -------------------------------------------------------------------- main

async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rounds", type=int, default=8,
                    help="samples per pair (default 8)")
    ap.add_argument("--interval", type=float, default=8.0,
                    help="seconds between rounds (default 8)")
    ap.add_argument("--notionals", default="1000,10000",
                    help="comma-separated USD notionals (default 1000,10000)")
    ap.add_argument("--warmup", type=float, default=20.0,
                    help="seconds to let books sync before sampling")
    ap.add_argument("--out", default=".scratch/scan-results",
                    help="directory for the JSON result dump")
    args = ap.parse_args()
    notionals = [float(x) for x in args.notionals.split(",")]

    async with aiohttp.ClientSession() as session:
        pairs = await discover(session)
    print(f"eligible universe: {len(pairs)} pairs")
    for p in pairs:
        print(f"  {p.symbol:10s} hedge={p.hedge:10s} entropy={p.hl_coin} "
              f"lighter_id={p.lighter_market}")

    scanner = Scanner(pairs)
    tasks = await scanner.run_feeds()
    print(f"waiting {args.warmup:.0f}s for {len(tasks)} book feeds to sync...")
    deadline = time.time() + args.warmup
    while time.time() < deadline:
        await asyncio.sleep(2)
        ready = sum(b.ready for b in list(scanner.entropy.values())
                    + list(scanner.lighter.values()))
        total = len(scanner.entropy) + len(scanner.lighter)
        print(f"  books ready: {ready}/{total}", flush=True)
        if ready >= total:
            break

    # sample: {pair_key: direction: notional: [edges]}
    samples: dict = {}
    for rnd in range(1, args.rounds + 1):
        ts = time.strftime("%H:%M:%S")
        for p in pairs:
            e_book = scanner.entropy.get(p.hl_coin)
            if p.lighter_market is not None:
                h_book = scanner.lighter.get((p.hedge, p.lighter_market))
            else:
                h_book = scanner.entropy.get(f"xyz:{p.symbol}")
            if not e_book or not h_book or not (e_book.ready and h_book.ready):
                continue
            hfee = FEE_BY_HEDGE[p.hedge]
            key = f"{p.symbol}/{p.hedge}"
            slot = samples.setdefault(key, {"buy_entropy": {n: [] for n in notionals},
                                            "sell_entropy": {n: [] for n in notionals}})
            for n in notionals:
                r1 = edge_bps(e_book, h_book, n, FEE_ENTROPY_BPS / 1e4, hfee / 1e4)
                if r1:
                    slot["buy_entropy"][n].append(r1[0])
                r2 = edge_bps(h_book, e_book, n, hfee / 1e4, FEE_ENTROPY_BPS / 1e4)
                if r2:
                    slot["sell_entropy"][n].append(r2[0])
        print(f"[{ts}] round {rnd}/{args.rounds} sampled", flush=True)
        if rnd < args.rounds:
            await asyncio.sleep(args.interval)

    scanner.stop.set()
    for t in tasks:
        t.cancel()

    # ------------------------------------------------------------ report
    rows = []
    for key, slot in samples.items():
        for direction in ("buy_entropy", "sell_entropy"):
            e1 = slot[direction][notionals[0]]
            if len(e1) < max(3, args.rounds // 2):
                continue
            row = {"pair": key, "direction": direction,
                   "n": len(e1),
                   "mean": sum(e1) / len(e1), "max": max(e1),
                   "pos": sum(1 for x in e1 if x > 0) / len(e1)}
            if len(notionals) > 1:
                e2 = slot[direction][notionals[1]]
                row["mean2"] = sum(e2) / len(e2) if e2 else None
            rows.append(row)
    rows.sort(key=lambda r: -r["mean"])

    n0 = int(notionals[0])
    print(f"\n=== net edge after both legs' fees, best direction per pair "
          f"(top-{n0:.0f} USD, {args.rounds} rounds) ===")
    print(f"{'pair':22s} {'direction':13s} {'mean_bps':>9s} {'max_bps':>8s} "
          f"{'pos%':>6s} {'mean@'+str(int(notionals[1]) if len(notionals)>1 else 0):>10s}")
    for r in rows:
        m2 = "n/a" if r.get("mean2") is None else f"{r['mean2']:+.1f}"
        print(f"{r['pair']:22s} {r['direction']:13s} {r['mean']:+9.1f} "
              f"{r['max']:+8.1f} {r['pos']*100:5.0f}% {m2:>10s}")

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"scan-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(out_path, "w") as f:
        json.dump({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "rounds": args.rounds, "interval": args.interval,
                   "notionals": notionals, "rows": rows}, f, indent=2)
    print(f"\nsaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
