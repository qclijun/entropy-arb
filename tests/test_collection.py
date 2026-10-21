"""Offline manifest, supervision, and duplicate-writer checks (stdlib only)."""
import asyncio
import fcntl
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from entropy_arb import collection


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'logs').mkdir()
        self.pair = {'symbol': 'EWY', 'entropy_symbol': 'EWY', 'hedge_symbol': 'EWY',
                     'hedge_venue': 'lighter', 'config': 'pair.yaml',
                     'csv': 'logs/minutes.csv', 'collection_enabled': True}
        self.cfg = SimpleNamespace(creds_complete=False, recorder_csv=str(self.root / self.pair['csv']))
        self.path = self.root / 'list.json'
        self.write_list([self.pair])
        for p in [patch.object(collection, 'ROOT', self.root),
                  patch.object(collection, 'load_config', return_value=self.cfg),
                  patch.dict(os.environ)]:
            mock = p.start()
            self.addCleanup(p.stop)
            if hasattr(mock, 'call_args'):
                self.load_config = mock

    def write_list(self, pairs):
        self.path.write_text(json.dumps({'schema_version': 1, 'pairs': pairs}))

    def test_public_only_and_disabled_pairs(self):
        os.environ.update(HL_PRIVATE_KEY='must-not-be-used',
                          LIGHTER_API_KEY_PRIVATE_KEY='must-not-be-used', HTTPS_PROXY='preserve-proxy')
        self.write_list([self.pair, dict(self.pair, symbol='OTHER', collection_enabled=False)])
        self.assertEqual(len(collection.load_collection(self.path)), 1)
        self.assertNotIn('HL_PRIVATE_KEY', os.environ)
        self.assertNotIn('LIGHTER_API_KEY_PRIVATE_KEY', os.environ)
        self.assertEqual(os.environ['HTTPS_PROXY'], 'preserve-proxy')
        self.assertEqual(self.load_config.call_args.args[1], '/dev/null')

    def test_reject_unsafe_manifest(self):
        for change in ['duplicate', 'alias', 'header', 'path', 'empty']:
            with self.subTest(change=change):
                pair, pairs = dict(self.pair), []
                pairs.append(pair)
                self.cfg.recorder_csv = str(self.root / self.pair['csv'])
                csv = Path(self.cfg.recorder_csv)
                if csv.exists():
                    csv.unlink()
                if change == 'duplicate':
                    pairs.append(dict(pair))
                elif change == 'alias':
                    pair['hedge_symbol'] = 'ANOTHER'
                elif change == 'header':
                    csv.write_text('old,header\n')
                elif change == 'path':
                    self.cfg.recorder_csv = str(self.root / 'elsewhere.csv')
                else:
                    pair['collection_enabled'] = False
                self.write_list(pairs)
                with self.assertRaises(ValueError):
                    collection.load_collection(self.path)
                if change == 'header':
                    self.assertEqual(csv.read_text(), 'old,header\n')

    def test_lock_conflict_releases_already_acquired_locks(self):
        first = collection.load_collection(self.path)[0]
        second = collection.CollectionItem(dict(self.pair, symbol='SNDK'), self.cfg)
        with second.lock_path.open('a') as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'another recorder'):
                with collection.collection_locks([first, second]):
                    self.fail('conflicting lock allowed')
            with collection.collection_locks([first]):
                pass
        with collection.collection_locks([first, second]):
            with self.assertRaises(RuntimeError):
                with collection.collection_locks([first]):
                    self.fail('duplicate writer allowed')

    def test_concurrent_pairs_flush_on_stop_and_cancellation(self):
        async def scenario(cancel):
            started, flushed, modes = set(), set(), []
            both = asyncio.Event()
            class FakeEngine:
                def __init__(self, cfg, record_only):
                    self.cfg, self.stop = cfg, asyncio.Event()
                    modes.append(record_only)
                async def run(self):
                    started.add(self.cfg)
                    if len(started) == 2:
                        both.set()
                    await self.stop.wait()
                    flushed.add(self.cfg)
                def request_stop(self):
                    self.stop.set()
            items = [collection.CollectionItem({'symbol': s, 'hedge_venue': 'lighter'}, s)
                     for s in ('EWY', 'SNDK')]
            with patch.object(collection, 'Engine', FakeEngine):
                stop = asyncio.Event()
                task = asyncio.create_task(collection.run_collection(items, stop))
                await asyncio.wait_for(both.wait(), 1)
                if cancel:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(task, 1)
                else:
                    stop.set()
                    await asyncio.wait_for(task, 1)
            self.assertEqual(started, flushed)
            self.assertEqual(flushed, {'EWY', 'SNDK'})
            self.assertEqual(modes, [True, True])
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                asyncio.run(scenario(cancel))

    def test_failure_retries_without_stopping_other_pair(self):
        async def scenario():
            counts, running = {}, set()
            recovered, stop = asyncio.Event(), asyncio.Event()
            class FakeEngine:
                def __init__(self, cfg, record_only):
                    self.cfg, self.stop = cfg, asyncio.Event()
                    assert record_only
                async def run(self):
                    counts[self.cfg] = counts.get(self.cfg, 0) + 1
                    if self.cfg == 'FAIL' and counts[self.cfg] == 1:
                        raise RuntimeError('temporary venue error')
                    running.add(self.cfg)
                    if running == {'OK', 'FAIL'}:
                        recovered.set()
                    await self.stop.wait()
                def request_stop(self):
                    self.stop.set()
            items = [collection.CollectionItem({'symbol': s, 'hedge_venue': 'lighter'}, s)
                     for s in ('OK', 'FAIL')]
            with patch.object(collection, 'Engine', FakeEngine), self.assertLogs('collection', level='ERROR'):
                task = asyncio.create_task(collection.run_collection(items, stop, retry_sec=.001))
                await asyncio.wait_for(recovered.wait(), 1)
                stop.set()
                await asyncio.wait_for(task, 1)
            self.assertEqual(counts, {'OK': 1, 'FAIL': 2})
        asyncio.run(scenario())


class ExistingPairTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.proc = self.root / 'proc' / '12345'
        self.proc.mkdir(parents=True)
        (self.proc / 'cwd').symlink_to(self.root, target_is_directory=True)
        real_path = Path
        def fake_path(value):
            return self.root / 'proc' if value == '/proc' else real_path(value)
        for p in [patch.object(collection, 'ROOT', self.root),
                  patch.object(collection, 'Path', fake_path)]:
            p.start()
            self.addCleanup(p.stop)

    def command(self, flags):
        args = [sys.executable, str(self.root / 'main.py'), *flags]
        (self.proc / 'cmdline').write_bytes(('\0'.join(args) + '\0').encode())

    def test_split_equals_and_mixed_options_preserve_process_mode(self):
        forms = [
            ['--symbol', 'EWY', '--hedge', 'lighter'],
            ['--symbol=EWY', '--hedge=lighter'],
            ['--symbol', 'EWY', '--hedge=lighter'],
            ['--symbol=EWY', '--hedge', 'lighter'],
        ]
        for flags in forms:
            for record_only in (False, True):
                with self.subTest(flags=flags, record_only=record_only):
                    self.command(flags + (['--record-only'] if record_only else []))
                    self.assertEqual(collection.existing_pair('EWY', 'lighter'),
                                     (12345, record_only))

    def test_repeated_options_follow_argparse_last_value(self):
        self.command(['--symbol', 'SNDK', '--symbol=EWY',
                      '--hedge=tradexyz', '--hedge', 'lighter', '--record-only'])
        self.assertEqual(collection.existing_pair('EWY', 'lighter'), (12345, True))
        self.assertIsNone(collection.existing_pair('SNDK', 'tradexyz'))

    def test_unrelated_or_malformed_options_are_skipped(self):
        for flags in [['--symbol=EWY', '--hedge=tradexyz'],
                      ['--symbol=SNDK', '--hedge=lighter'],
                      ['--hedge=lighter', '--symbol'],
                      ['--symbol=EWY', '--hedge']]:
            with self.subTest(flags=flags):
                self.command(flags)
                with redirect_stderr(io.StringIO()) as stderr:
                    self.assertIsNone(collection.existing_pair('EWY', 'lighter'))
                self.assertEqual(stderr.getvalue(), '')

    def test_single_entry_refuses_existing_equals_process(self):
        from tools import collect
        self.command(['--symbol=EWY', '--hedge=lighter', '--record-only'])
        item = collection.CollectionItem({'symbol': 'EWY', 'hedge_venue': 'lighter'}, None)
        with patch.object(collect, 'load_collection', return_value=[item]), \
             patch.object(collect, 'collection_locks') as locks, \
             patch.object(collect, 'collect', side_effect=AssertionError('duplicate collection attempted')), \
             patch.object(sys, 'argv', ['collect.py']), \
             patch.object(collect.logging, 'basicConfig'), \
             redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as exit_result:
                collect.main()
            self.assertEqual(exit_result.exception.code, 1)
            self.assertIn('process 12345 is already running', stderr.getvalue())
            locks.assert_not_called()

    def test_legacy_entry_skips_existing_equals_recorder(self):
        from tools import start_recorders
        self.command(['--symbol=EWY', '--hedge=lighter', '--record-only'])
        pair = {'symbol': 'EWY', 'hedge_venue': 'lighter', 'csv': 'logs/example.csv'}
        item = collection.CollectionItem(pair, None)
        with patch.object(start_recorders, 'load_collection', return_value=[item]), \
             patch.object(start_recorders, 'ROOT', self.root), \
             patch.object(start_recorders.subprocess, 'Popen',
                          side_effect=AssertionError('duplicate process attempted')) as spawn, \
             patch.object(sys, 'argv', ['start_recorders.py', '--start']), \
             redirect_stdout(io.StringIO()) as stdout:
            start_recorders.main()
            result = json.loads(stdout.getvalue())
            self.assertEqual(result[0]['status'], 'already_running')
            self.assertEqual(result[0]['pid'], 12345)
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
