#!/usr/bin/env python3
"""One-shot cross-venue spread snapshot (read-only, no trading).

Connects to Entropy (Hyperliquid io dex) and Lighter mainnet websockets,
waits for book snapshots, prints the executable premium both directions.
A snapshot is NOT a tradable signal by itself -- the strategy needs the
premium distribution (see tools/analyze.py after --record-only collection).

Usage: python3 tools/snapshot_spread.py [SYM1 SYM2 ...]
"""
from __future__ import annotations

import asyncio
import sys

import aiohttp

sys.path.insert(0, ".")

from entropy_arb.book import OrderBook
from entropy_arb.config import HL_WS_URL, LIGHTER_PROFILES
from entropy_arb.feeds import HLBookFeed, LighterBookFeed

# Endpoints come from entropy_arb.config (single source) -- do not restate
# the literals here; an endpoint change must only ever be edited in config.
LIGHTER_MAINNET = LIGHTER_PROFILES["lighter"]

# Symbols scanned when none are passed on the command line.
DEFAULT_SYMBOLS = ["SNDK", "NBIS", "XIAOMI", "DRAM", "PRL", "EWY"]


async def fetch_market_ids() -> dict[str, int]:
    """Resolve Lighter mainnet symbol -> market_id from the public
    /api/v1/orderBooks (the same source venue_lighter.load_market uses),
    instead of a hardcoded table that silently goes stale."""
    url = LIGHTER_MAINNET.api_url + "/api/v1/orderBooks"
    # trust_env: aiohttp ignores HTTP(S)_PROXY by default; this deployment
    # egresses through a proxy (same reason as the engine's session).
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            r.raise_for_status()
            data = await r.json()
    return {ob["symbol"]: int(ob["market_id"])
            for ob in data.get("order_books") or []
            if ob.get("status") == "active"}


async def snapshot_symbol(symbol: str, market_id: int,
                          timeout: float = 20.0) -> None:
    book_e = OrderBook()
    book_hedge = OrderBook()
    stop = asyncio.Event()
    got_e, got_hedge = asyncio.Event(), asyncio.Event()

    feed_e = HLBookFeed("entropy", HL_WS_URL, f"io:{symbol}", book_e,
                        lambda: got_e.set())
    feed_hedge = LighterBookFeed("lighter", LIGHTER_MAINNET.ws_url,
                                 market_id, book_hedge,
                                 lambda: got_hedge.set())

    async def run_feed(feed):
        try:
            await feed.run(stop)
        except asyncio.CancelledError:
            pass

    tasks = [asyncio.create_task(run_feed(feed_e)),
             asyncio.create_task(run_feed(feed_hedge))]
    try:
        await asyncio.wait_for(
            asyncio.gather(got_e.wait(), got_hedge.wait()), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        print(f"{symbol:8} TIMEOUT waiting for book snapshots")
        return
    finally:
        stop.set()
        for t in tasks:
            t.cancel()

    asks_e = book_e.sorted_asks()
    bids_e = book_e.sorted_bids()
    asks_hedge = book_hedge.sorted_asks()
    bids_hedge = book_hedge.sorted_bids()
    if not (asks_e and bids_e and asks_hedge and bids_hedge):
        print(f"{symbol:8} empty book on a venue")
        return
    # executable premium both directions, in bps, pre-fee
    sell_e = (bids_e[0][0] / asks_hedge[0][0] - 1.0) * 1e4   # sell entropy, buy lighter
    buy_e = (bids_hedge[0][0] / asks_e[0][0] - 1.0) * 1e4    # buy entropy, sell lighter
    mid_e = (bids_e[0][0] + asks_e[0][0]) / 2
    mid_hedge = (bids_hedge[0][0] + asks_hedge[0][0]) / 2
    mid_prem = (mid_e / mid_hedge - 1.0) * 1e4
    print(f"{symbol:8} mid_prem {mid_prem:+7.1f}bps | "
          f"sell_entropy {sell_e:+7.1f}bps | buy_entropy {buy_e:+7.1f}bps | "
          f"depth_e {len(bids_e)}/{len(asks_e)} "
          f"depth_hedge {len(bids_hedge)}/{len(asks_hedge)}")


async def main() -> None:
    symbols = sys.argv[1:] or DEFAULT_SYMBOLS
    markets = await fetch_market_ids()
    for s in symbols:
        if s not in markets:
            print(f"{s}: unknown symbol, skip")
            continue
        try:
            await snapshot_symbol(s, markets[s])
        except Exception as e:  # noqa: BLE001 - one bad symbol shouldn't kill the scan
            print(f"{s:8} ERROR {e}")


if __name__ == "__main__":
    asyncio.run(main())
