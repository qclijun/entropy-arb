"""Minute-bar replay: two-leg fills, persistence, and position accounting."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from entropy_arb.backtest import MinuteBar, run_backtest  # noqa: E402
from entropy_arb.config import load_config  # noqa: E402

NO_ENV = os.path.join(tempfile.gettempdir(), "entropy-arb-no-such.env")


def make_cfg(persist=0.0):
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    f.write(f"""
thresholds:
  midline_bps: 0.0
  upper_bps: 4.0
  lower_bps: 4.0
sizing:
  take_fraction: 0.5
  max_order_notional_usd: 100.0
  min_order_notional_usd: 10.0
inventory:
  scale_bps: 0.0
execution:
  premium_persist_sec: {persist}
  cooldown_sec: 0.0
entropy:
  max_position_usd: 1_000.0
hedge:
  max_position_usd: 1_000.0
""")
    f.close()
    return load_config(f.name, NO_ENV, symbol="SNDK", hedge_venue="lighter")


def test_replay_executes_both_directions_and_marks_to_market():
    # First Entropy is rich: sell Entropy / buy hedge. Then it is cheap: the
    # opposite signal offsets the pair at executable bid/ask prices.
    bars = [
        MinuteBar(0, 100.20, 100.22, 100.00, 100.02, 60),
        MinuteBar(60, 99.90, 99.92, 100.00, 100.02, 60),
    ]
    result = run_backtest(bars, make_cfg(), assumed_depth_usd=200.0,
                          size_step=0.001)

    assert [trade.direction for trade in result.trades] == [
        "sell_entropy", "buy_entropy"]
    # Per-venue residuals can remain because each slice is capped in current
    # quote currency, but every simulated pair is base-neutral.
    assert abs(result.entropy_position + result.hedge_position) < 1e-12
    assert result.total_fill_edge_usd > 0
    assert result.final_equity_usd > 0


def test_replay_requires_the_configured_persistence_before_filling():
    bars = [
        MinuteBar(0, 100.20, 100.22, 100.00, 100.02, 60),
        MinuteBar(60, 100.20, 100.22, 100.00, 100.02, 60),
        MinuteBar(120, 100.20, 100.22, 100.00, 100.02, 60),
    ]
    result = run_backtest(bars, make_cfg(persist=120.0),
                          assumed_depth_usd=200.0, size_step=0.001)

    assert len(result.trades) == 1
    assert result.trades[0].minute_ts == 120
    assert result.trades[0].direction == "sell_entropy"
