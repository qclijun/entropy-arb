#!/usr/bin/env python3
"""Validate the confirmed market list; --start launches public-data recorders only."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from entropy_arb.collection import existing_pair, load_collection


def recorder_lock_held(symbol: str, hedge: str) -> bool:
    path = ROOT / 'logs' / f'.recorder-{hedge}-{symbol}.lock'
    if not path.exists():
        return False
    with path.open('r') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', action='store_true', help='start missing record-only collectors')
    args = parser.parse_args()
    plan = []
    for item in load_collection(ROOT / 'record/hedge-markets.json'):
        pair = item.pair
        symbol, hedge = pair['symbol'], pair['hedge_venue']
        existing = existing_pair(symbol, hedge)
        if existing and not existing[1]:
            raise ValueError(f'{symbol}/{hedge}: live trading process exists; refusing a duplicate')
        plan.append((pair, existing))
    results = []
    for pair, existing in plan:
        symbol, hedge = pair['symbol'], pair['hedge_venue']
        result = {'symbol': symbol, 'hedge': hedge, 'csv': pair['csv']}
        if existing:
            results.append({**result, 'status': 'already_running', 'pid': existing[0]})
            continue
        # Restricted /proc views may hide an existing process; its inherited
        # lock must still prevent both duplicate launches and a false 'ready'.
        if recorder_lock_held(symbol, hedge):
            results.append({**result, 'status': 'recorder_lock_held'})
            continue
        if not args.start:
            results.append({**result, 'status': 'ready'})
            continue
        stem = f'{hedge}-{symbol}'
        lockpath = ROOT / 'logs' / f'.recorder-{stem}.lock'
        lockpath.parent.mkdir(exist_ok=True)
        with lockpath.open('a') as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                results.append({**result, 'status': 'locked_by_existing_recorder'})
                continue
            command = [str(ROOT / '.venv/bin/python'), str(ROOT / 'main.py'), '--record-only',
                       '--symbol', symbol, '--hedge', hedge, '--config', str(ROOT / pair['config']),
                       '--env-file', '/dev/null', '--no-dashboard']
            logfile = ROOT / 'logs' / f'collector-{stem}.log'
            with logfile.open('ab') as log:
                child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                         pass_fds=(lock.fileno(),))
            (ROOT / 'logs' / f'.recorder-{stem}.pid').write_text(str(child.pid) + '\n')
            # The inherited descriptor retains the lock until the recorder exits.
            results.append({**result, 'status': 'started', 'pid': child.pid, 'log': str(logfile)})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
