#!/usr/bin/env python3
"""Replay a hedge-specific recorder CSV through the current strategy rules.

Example:
    python3 tools/backtest.py --symbol SNDK --hedge lighter \
        --csv logs/minutes-lighter.csv --trades-csv logs/backtest-trades.csv

Each minute row is an L1 snapshot. See docs/research/backtesting-frameworks.md
for the execution assumptions and the data needed for a higher-fidelity replay.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from entropy_arb.backtest import (BacktestError, load_minute_bars, run_backtest,
                                  write_trades_csv)
from entropy_arb.config import ConfigError, HEDGE_VENUES, load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="replay minute L1 data through the two-venue arbitrage strategy")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--hedge", required=True, choices=HEDGE_VENUES)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--csv", help="recorder CSV (default: config path for --hedge)")
    parser.add_argument("--min-samples", type=int, default=10,
                        help="skip minutes with fewer fresh samples (default: 10)")
    parser.add_argument("--assumed-depth-usd", type=float,
                        help="notional at each L1 bid/ask; default reaches order cap")
    parser.add_argument("--extra-slippage-bps", type=float, default=0.0,
                        help="adverse slippage applied to both fills (default: 0)")
    parser.add_argument("--size-step", type=float, default=1e-4,
                        help="shared base-size increment (default: 0.0001)")
    parser.add_argument("--min-base", type=float,
                        help="minimum base size (default: --size-step)")
    parser.add_argument("--trades-csv", help="optional output path for simulated fills")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config, args.env_file,
                          symbol=args.symbol, hedge_venue=args.hedge)
        path = args.csv or cfg.recorder_csv
        bars = load_minute_bars(path, args.min_samples)
        if not bars:
            raise BacktestError(f"no usable minute rows in {path}")
        result = run_backtest(
            bars, cfg,
            assumed_depth_usd=args.assumed_depth_usd,
            extra_slippage_bps=args.extra_slippage_bps,
            size_step=args.size_step,
            min_base=args.min_base,
        )
    except (BacktestError, ConfigError) as exc:
        print(f"backtest error: {exc}", file=sys.stderr)
        raise SystemExit(2)

    if args.trades_csv:
        write_trades_csv(args.trades_csv, result.trades)

    print(f"\n=== {path}: {result.bars} eligible minute(s) ===")
    print(f"trades {len(result.trades)}  turnover ${result.turnover_usd:,.2f}")
    print(f"expected edge ${result.total_expected_edge_usd:+,.4f}  "
          f"filled edge ${result.total_fill_edge_usd:+,.4f}")
    print(f"final equity ${result.final_equity_usd:+,.4f}  "
          f"max drawdown ${result.max_drawdown_usd:,.4f}")
    print(f"positions entropy {result.entropy_position:+.8g}  "
          f"hedge {result.hedge_position:+.8g}")
    if args.trades_csv:
        print(f"simulated fills -> {args.trades_csv}")


if __name__ == "__main__":
    main()
