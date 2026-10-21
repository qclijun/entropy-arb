#!/usr/bin/env python3
"""Collect every enabled pair in a JSON list, in one public-data-only process."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from entropy_arb.collection import (PAIR_CONTEXT, collection_locks, existing_pair,
                                    load_collection, run_collection)


class PairFilter(logging.Filter):
    def filter(self, record):
        record.pair = PAIR_CONTEXT.get()
        return True


async def collect(items):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        logging.info('RECORD-ONLY pid=%s pairs=%d; no credentials, no strategy',
                     os.getpid(), len(items))
        await run_collection(items, stop)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', type=Path, default=ROOT / 'record/hedge-markets.json',
                        help='JSON collection list (paths inside it are project-relative)')
    parser.add_argument('--check', action='store_true', help='validate without connecting or writing data')
    args = parser.parse_args()
    handler = logging.StreamHandler()
    handler.addFilter(PairFilter())
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(pair)s] %(name)s: %(message)s'))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger('websockets').setLevel(logging.WARNING)
    try:
        items = load_collection(args.list)
        if args.check:
            print(json.dumps({'pairs': len(items), 'markets': [item.key for item in items]}))
            return
        # Detect manually started main.py collectors/traders as well as file locks.
        for item in items:
            existing = existing_pair(item.pair['symbol'], item.pair['hedge_venue'])
            if existing:
                raise RuntimeError(f'{item.key}: main.py process {existing[0]} is already running')
        with collection_locks(items):
            asyncio.run(collect(items))
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(1, f'collection error: {exc}\n')


if __name__ == '__main__':
    main()
