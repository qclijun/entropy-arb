"""Validated, public-data-only collection of a manifest in one event loop."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import fcntl
import json
import logging
import os
from pathlib import Path

from .config import Config, HEDGE_VENUES, load_config
from .engine import Engine
from .recorder import HEADER

ROOT = Path(__file__).resolve().parents[1]
PAIR_CONTEXT = ContextVar('collection_pair', default='collector')
log = logging.getLogger('collection')


def existing_pair(symbol: str, hedge: str) -> tuple[int, bool] | None:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False,
                                     exit_on_error=False)
    parser.add_argument('--symbol')
    parser.add_argument('--hedge')
    parser.add_argument('--record-only', action='store_true')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = proc.joinpath('cmdline').read_bytes().decode().split('\0')
            if proc.joinpath('cwd').resolve() != ROOT:
                continue
            if not any(Path(a).name == 'main.py' for a in args if a):
                continue
            # Match main.py's spaced/equal forms and repeated-option semantics.
            options, _ = parser.parse_known_args(args)
            if (options.symbol, options.hedge) != (symbol, hedge):
                continue
            return int(proc.name), options.record_only
        except (OSError, ValueError, IndexError, argparse.ArgumentError):
            continue
    return None


@dataclass
class CollectionItem:
    pair: dict
    config: Config

    @property
    def key(self) -> str:
        return f"{self.pair['hedge_venue']}-{self.pair['symbol']}"

    @property
    def lock_path(self) -> Path:
        return ROOT / 'logs' / f'.recorder-{self.key}.lock'


def load_collection(path: Path) -> list[CollectionItem]:
    # Public subscriptions must not inherit credentials or read the user's .env.
    for name in list(os.environ):
        if name.startswith(('HL_', 'LIGHTER_', 'ENTROPY_')):
            os.environ.pop(name)
    manifest = json.loads(path.read_text())
    if manifest.get('schema_version') != 1:
        raise ValueError('collection list requires schema_version: 1')
    items, outputs, keys = [], set(), set()
    for pair in manifest['pairs']:
        if pair['collection_enabled'] is not True:
            continue
        symbol, hedge = pair['symbol'], pair['hedge_venue']
        if not (symbol == pair['entropy_symbol'] == pair['hedge_symbol']
                and hedge in HEDGE_VENUES and symbol.isalnum()):
            raise ValueError('only approved same-symbol market pairs can be collected')
        config_path = (ROOT / pair['config']).resolve()
        if not config_path.is_relative_to(ROOT):
            raise ValueError('config must be inside the project')
        cfg = load_config(str(config_path), '/dev/null', symbol=symbol, hedge_venue=hedge)
        output = Path(cfg.recorder_csv).resolve()
        if (cfg.creds_complete or output != (ROOT / pair['csv']).resolve()
                or output.parent != (ROOT / 'logs').resolve()):
            raise ValueError(f'{symbol}/{hedge}: unsafe credentials or recorder path')
        if (symbol, hedge) in keys or output in outputs:
            raise ValueError('duplicate market pair or CSV destination')
        keys.add((symbol, hedge))
        outputs.add(output)
        if output.exists() and output.stat().st_size:
            with output.open() as stream:
                if stream.readline().strip() != ','.join(HEADER):
                    raise ValueError(f'{output}: incompatible header; preserve it before starting')
        items.append(CollectionItem(pair, cfg))
    if not items:
        raise ValueError('collection list has no enabled pairs')
    return items


@contextmanager
def collection_locks(items: list[CollectionItem]):
    """All-or-nothing locks, compatible with the older per-pair launcher."""
    with ExitStack() as stack:
        for item in items:
            item.lock_path.parent.mkdir(exist_ok=True)
            lock = stack.enter_context(item.lock_path.open('a'))
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(f'{item.key}: another recorder holds the pair lock') from None
        yield


async def run_collection(items: list[CollectionItem], stop: asyncio.Event,
                         *, retry_sec: float = 5.0) -> None:
    async def supervise(item):
        PAIR_CONTEXT.set(item.key)
        while not stop.is_set():
            engine = Engine(item.config, record_only=True)
            task = asyncio.create_task(engine.run(), name=item.key)
            stopping = asyncio.create_task(stop.wait())
            try:
                await asyncio.wait([task, stopping], return_when=asyncio.FIRST_COMPLETED)
                if stop.is_set():
                    engine.request_stop()
                    await asyncio.wait_for(asyncio.shield(task), timeout=15)
                else:
                    await task
                    log.error('pair exited unexpectedly; restarting in %ss', retry_sec)
            except Exception:
                log.exception('pair failed; retrying independently in %ss', retry_sec)
            finally:
                engine.request_stop()
                for pending in (task, stopping):
                    if not pending.done():
                        pending.cancel()
                await asyncio.gather(task, stopping, return_exceptions=True)
            if not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=retry_sec)
                except asyncio.TimeoutError:
                    pass

    tasks = [asyncio.create_task(supervise(item), name=f'supervise-{item.key}')
             for item in items]
    try:
        # Keep cancellation of the caller from bypassing each recorder's flush.
        await asyncio.shield(asyncio.gather(*tasks))
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
