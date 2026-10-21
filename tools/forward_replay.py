#!/usr/bin/env python3
"""Forward (out-of-sample) replay with parameters frozen at one point in time.

    # once: fit thresholds on the last 48h before the newest common minute
    python3 tools/forward_replay.py freeze [--hl-address 0x...]
    # daily: replay every minute recorded after the freeze, unchanged params
    python3 tools/forward_replay.py run [--freeze logs/forward/<id>]

Pairs come from record/hedge-markets.json (all of them, including pairs whose
collection is disabled). Offline except for public fee/step/funding lookups
(tools/venue_costs.py); no credentials, no orders, production configs and CSVs
are only read. Outputs go to logs/forward/<freeze id>/: freeze.json + research
configs at freeze time, then runs/<newest minute>/ (summary.json, report.md,
fills) and history.csv (one row per pair and scenario per run).

`run` uses the newest freeze that has no SUPERSEDED.txt (by creation time).
Each pair is replayed up to its own last recorded minute; pairs with no new
minute since the previous run are reported as stale and not appended to
history, and a run with no new minute anywhere writes nothing.

Execution model is the project replay (entropy_arb/backtest.py): minute-close
L1 on both legs treated as simultaneous full fills. Results are simulated and
labelled as such; terminal positions are valued at bid/ask with fees and
slippage (hypothetical liquidation), plus public hourly funding. Funding that
falls inside a recording gap (> 3 min) is also reported separately, because
the position could not have been observed or managed then.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from entropy_arb.backtest import load_minute_bars, run_backtest, write_trades_csv  # noqa: E402
from entropy_arb.config import load_config  # noqa: E402
from analyze import pctl  # noqa: E402
import venue_costs as vc  # noqa: E402

MANIFEST = ROOT / "record/hedge-markets.json"
TZ = ZoneInfo("Asia/Taipei")
MIN_SAMPLES = 10
MIN_FIT_MINUTES = 360
MIN_TEST_MINUTES = 60
GAP_SEC = 180
LAST_RUN = "last_run.json"
SUPERSEDED = "SUPERSEDED.txt"


@dataclass(frozen=True)
class Scenario:
    label: str
    slip_bps: float                    # adverse slippage per leg per fill
    entropy_fee_bps: Optional[float]   # None: keep the frozen fee


SCENARIOS = [Scenario("slip1", 1.0, None), Scenario("slip2", 2.0, None),
             Scenario("entropy9-slip1", 1.0, 9.0)]
BASE = SCENARIOS[0]


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, TZ).isoformat()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_pairs():
    """[(key, symbol, hedge, config path, csv path)] from the collection manifest."""
    pairs = []
    for p in json.loads(MANIFEST.read_text())["pairs"]:
        key = f"{p['symbol']}-{p['hedge_venue']}"
        pairs.append((key, p["symbol"], p["hedge_venue"], ROOT / p["config"], ROOT / p["csv"]))
    return pairs


def clean_rows(path: Path):
    """Valid minutes, one per timestamp (most samples, then last row), sorted."""
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames
        best = {}
        for row in reader:
            try:
                ts = int(row["minute_ts"])
                if int(row["samples"]) < MIN_SAMPLES:
                    continue
                eb, ea, hb, ha = (float(row[k]) for k in
                                  ("entropy_bid", "entropy_ask", "hedge_bid", "hedge_ask"))
                extra = [float(row[k]) for k in
                         ("premium_close_bps", "sell_edge_max_bps", "buy_edge_max_bps")]
            except (KeyError, ValueError):
                continue
            if not all(math.isfinite(x) for x in (eb, ea, hb, ha, *extra)):
                continue
            if not (0 < eb <= ea and 0 < hb <= ha):
                continue
            if ts in best and int(best[ts]["samples"]) > int(row["samples"]):
                continue
            best[ts] = row
    return header, [best[t] for t in sorted(best)]


def write_rows(path: Path, header, rows) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def fit(rows, fee_bps: float) -> dict:
    """Same rule as tools/analyze.py: median center, p90 minute-max bands."""
    prem = sorted(float(r["premium_close_bps"]) for r in rows)
    mid = round(pctl(prem, 50), 1) or 0.0
    sell = sorted(float(r["sell_edge_max_bps"]) - mid - fee_bps for r in rows)
    buy = sorted(float(r["buy_edge_max_bps"]) + mid - fee_bps for r in rows)
    return dict(midline_bps=mid,
                upper_bps=max(round(pctl(sell, 90) * 2) / 2, 1.0),
                lower_bps=max(round(pctl(buy, 90) * 2) / 2, 1.0),
                premium_std_bps=statistics.pstdev(prem))


def hedge_fee(hedge: str, symbol: str, hl_fees: dict) -> Tuple[float, str]:
    """(taker bps, provenance) for the hedge leg."""
    if hedge == "tradexyz":
        return hl_fees["markets"][f"xyz:{symbol}"]["taker_bps"], hl_fees["source"]
    return (vc.lighter_markets(hedge)[symbol]["taker_bps"],
            "Lighter market-level taker fee; account tier NOT verified here")


def freeze(args) -> Path:
    loaded = {}
    for key, symbol, hedge, conf, csv_path in manifest_pairs():
        if not csv_path.exists() or not conf.exists():
            print(f"skip {key}: missing {csv_path if not csv_path.exists() else conf}")
            continue
        header, rows = clean_rows(csv_path)
        if rows:
            loaded[key] = (symbol, hedge, conf, csv_path, header, rows)
    if not loaded:
        raise SystemExit(f"no usable minute CSV for any pair in {MANIFEST}")
    as_of = min(int(x[5][-1]["minute_ts"]) for x in loaded.values())
    if args.as_of:
        as_of = min(as_of, vc.parse_ts(args.as_of))
    fit_start = as_of - args.fit_hours * 3600
    hl_fees = vc.hl_fee_report(sorted({x[0] for x in loaded.values()}), args.hl_address)

    out = Path(args.root) / datetime.fromtimestamp(as_of, TZ).strftime("%Y%m%d-%H%M")
    if out.exists():
        raise SystemExit(f"{out} already exists; a freeze is never overwritten")
    out.mkdir(parents=True)
    meta = dict(created_at=datetime.now(timezone.utc).isoformat(), as_of=iso(as_of),
                as_of_ts=as_of, fit_hours=args.fit_hours, fit_start=iso(fit_start),
                rule="median premium_close center; p90 of minute-max edge net of fees; "
                     f"samples>={MIN_SAMPLES}; dedupe most samples then last row",
                fee_source=hl_fees["source"], hl_fee_report=hl_fees, pairs={})
    for key, (symbol, hedge, conf, csv_path, header, rows) in loaded.items():
        window = [r for r in rows if fit_start <= int(r["minute_ts"]) <= as_of]
        entry = dict(symbol=symbol, hedge=hedge, csv=str(csv_path.relative_to(ROOT)),
                     source_csv_sha256=sha(csv_path),
                     source_config=str(conf.relative_to(ROOT)),
                     source_config_sha256=sha(conf), fit_minutes=len(window),
                     fit_first=iso(int(window[0]["minute_ts"])) if window else None)
        if len(window) < MIN_FIT_MINUTES:
            entry["status"] = f"skipped: {len(window)} fit minutes < {MIN_FIT_MINUTES}"
            meta["pairs"][key] = entry
            continue
        raw_cfg = yaml.safe_load(conf.read_text())
        e_fee = hl_fees["markets"][f"io:{symbol}"]["taker_bps"]
        h_fee, h_fee_source = hedge_fee(hedge, symbol, hl_fees)
        params = fit(window, e_fee + h_fee)
        raw_cfg["entropy"]["taker_fee_bps"] = e_fee
        raw_cfg["hedge"]["taker_fee_bps"] = h_fee
        raw_cfg["thresholds"].update({k: params[k] for k in
                                      ("midline_bps", "upper_bps", "lower_bps")})
        cfg_path = out / f"{key}.yaml"
        cfg_path.write_text(yaml.safe_dump(raw_cfg, sort_keys=False, allow_unicode=True))
        fit_csv = out / f"{key}-fit.csv"
        write_rows(fit_csv, header, window)
        entry.update(status="frozen", entropy_fee_bps=e_fee, hedge_fee_bps=h_fee,
                     entropy_fee_source=hl_fees["source"], hedge_fee_source=h_fee_source,
                     params=params, steps=vc.steps(symbol, hedge),
                     research_config=cfg_path.name, research_config_sha256=sha(cfg_path),
                     fit_csv_sha256=sha(fit_csv))
        meta["pairs"][key] = entry
    (out / "freeze.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"frozen {sum(p['status'] == 'frozen' for p in meta['pairs'].values())} pairs "
          f"at {meta['as_of']} -> {out}")
    return out


def latest_freeze(root: Path) -> Path:
    """Most recently created freeze that has not been marked superseded."""
    live = [p for p in root.iterdir()
            if (p / "freeze.json").exists() and not (p / SUPERSEDED).exists()]
    if not live:
        raise SystemExit(f"no active freeze under {root}; run `freeze` first")
    return max(live, key=lambda p: json.loads((p / "freeze.json").read_text())["created_at"])


def liquidation(result, last, cfg, slip_bps: float) -> float:
    """Mid equity minus the cost of crossing the spread to flatten, per leg."""
    cost = 0.0
    for pos, bid, ask, fee in ((result.entropy_position, last.entropy_bid,
                                last.entropy_ask, cfg.entropy.fee_bps),
                               (result.hedge_position, last.hedge_bid,
                                last.hedge_ask, cfg.hedge.fee_bps)):
        if pos == 0:
            continue
        mid = (bid + ask) / 2
        px = bid if pos > 0 else ask
        cost += abs(pos) * (abs(mid - px) + px * (slip_bps + fee) / 1e4)
    return result.final_equity_usd - cost


def gaps(ts: List[int]) -> List[Tuple[int, int]]:
    """(last minute before, first minute after) for every gap > GAP_SEC."""
    return [(a, b) for a, b in zip(ts, ts[1:]) if b - a > GAP_SEC]


def in_gap(t: int, holes: List[Tuple[int, int]]) -> bool:
    return any(a < t < b for a, b in holes)


def flat_returns(trades) -> int:
    """Times the Entropy position went from non-zero back to zero."""
    return sum(1 for prev, cur in zip(trades, trades[1:])
               if abs(cur.entropy_position) < 1e-9 <= abs(prev.entropy_position))


def replay_pair(key, p, header, rows, start, out, fdir) -> dict:
    end = int(rows[-1]["minute_ts"])
    ts = [int(r["minute_ts"]) for r in rows]
    holes = gaps(ts)
    entry = dict(minutes=len(rows), test_end=iso(end), test_end_ts=end,
                 hours=(end - start) / 3600, gaps_gt3min=len(holes),
                 gap_minutes=sum(b - a - 60 for a, b in holes) / 60,
                 max_gap_minutes=max((b - a - 60 for a, b in holes), default=0) / 60,
                 status="ok", scenarios={})
    test_csv = out / f"{key}-test.csv"
    write_rows(test_csv, header, rows)
    entry["test_csv_sha256"] = sha(test_csv)
    bars = load_minute_bars(str(test_csv), MIN_SAMPLES)
    base = load_config(str(fdir / p["research_config"]), "/dev/null",
                       symbol=p["symbol"], hedge_venue=p["hedge"])
    epx = [(b.minute_ts, (b.entropy_bid + b.entropy_ask) / 2) for b in bars]
    hpx = [(b.minute_ts, (b.hedge_bid + b.hedge_ask) / 2) for b in bars]
    e_rates = vc.funding_series("entropy", p["symbol"], start, end + 60)
    h_rates = vc.funding_series(p["hedge"], p["symbol"], start, end + 60)
    e_gap = [x for x in e_rates if in_gap(x[0], holes)]
    h_gap = [x for x in h_rates if in_gap(x[0], holes)]
    for sc in SCENARIOS:
        cfg = base if sc.entropy_fee_bps is None else replace(
            base, entropy=replace(base.entropy, fee_bps=sc.entropy_fee_bps))
        res = run_backtest(bars, cfg, extra_slippage_bps=sc.slip_bps,
                           size_step=p["steps"]["size_step"],
                           min_base=p["steps"]["min_base"])
        write_trades_csv(str(out / f"{key}-{sc.label}-fills.csv"), res.trades)
        epos = [(t.minute_ts, t.entropy_position) for t in res.trades]
        hpos = [(t.minute_ts, t.hedge_position) for t in res.trades]
        funding = (vc.funding_pnl(epos, epx, e_rates, start, end)[0]
                   + vc.funding_pnl(hpos, hpx, h_rates, start, end)[0])
        funding_in_gaps = (vc.funding_pnl(epos, epx, e_gap, start, end)[0]
                           + vc.funding_pnl(hpos, hpx, h_gap, start, end)[0])
        liq = liquidation(res, bars[-1], cfg, sc.slip_bps)
        entry["scenarios"][sc.label] = dict(
            fills=len(res.trades), flat_returns=flat_returns(res.trades),
            turnover_usd=res.turnover_usd,
            entropy_position=res.entropy_position,
            entropy_position_usd=res.entropy_position * bars[-1].entropy_bid,
            mid_equity_usd=res.final_equity_usd,
            liquidation_usd=liq, funding_usd=funding,
            funding_in_gaps_usd=funding_in_gaps,
            net_after_funding_usd=liq + funding,
            max_drawdown_mid_usd=res.max_drawdown_usd)
    return entry


def run(args) -> Optional[Path]:
    fdir = Path(args.freeze) if args.freeze else latest_freeze(Path(args.root))
    meta = json.loads((fdir / "freeze.json").read_text())
    start = meta["as_of_ts"]
    last_path = fdir / LAST_RUN
    last = json.loads(last_path.read_text()) if last_path.exists() else {}

    data = {}
    for key, p in meta["pairs"].items():
        if p["status"] != "frozen":
            continue
        if sha(fdir / p["research_config"]) != p["research_config_sha256"]:
            raise SystemExit(f"{key}: frozen config {p['research_config']} was modified")
        src = ROOT / p.get("csv", f"logs/minutes-{p['hedge']}-{p['symbol']}.csv")
        header, rows = clean_rows(src)
        data[key] = (src, header, [r for r in rows if int(r["minute_ts"]) > start])
    ends = {k: int(rows[-1]["minute_ts"]) for k, (_, _, rows) in data.items() if rows}
    advanced = {k for k, e in ends.items() if e > last.get(k, start)}
    if not advanced:
        print(f"no new minutes since the previous run of {fdir.name}; nothing written")
        return None
    newest = max(ends[k] for k in advanced)
    out = fdir / "runs" / datetime.fromtimestamp(newest, TZ).strftime("%Y%m%d-%H%M")
    out.mkdir(parents=True, exist_ok=True)

    summary = dict(created_at=datetime.now(timezone.utc).isoformat(), freeze=fdir.name,
                   freeze_as_of=meta["as_of"], test_start=iso(start),
                   newest_minute=iso(newest), pairs={})
    for key, (src, header, rows) in data.items():
        p = meta["pairs"][key]
        base_entry = dict(minutes=len(rows), params=p["params"],
                          fees_bps=[p["entropy_fee_bps"], p["hedge_fee_bps"]],
                          source_csv_sha256=sha(src))
        if key not in advanced:
            seen = ends.get(key)
            base_entry["status"] = ("stale: no new minutes since "
                                    + (iso(seen) if seen else "the freeze"))
        elif len(rows) < MIN_TEST_MINUTES:
            base_entry["status"] = f"insufficient: {len(rows)} minutes"
        else:
            base_entry.update(replay_pair(key, p, header, rows, start, out, fdir))
        summary["pairs"][key] = base_entry
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (out / "report.md").write_text(render(summary))
    append_history(fdir / "history.csv", summary)
    last.update({k: ends[k] for k in advanced})
    last_path.write_text(json.dumps(last, indent=2))
    print(f"forward replay since {summary['test_start']} -> {out}")
    print(render(summary))
    return out


def render(s: dict) -> str:
    others = [sc for sc in SCENARIOS if sc is not BASE]
    lines = [f"# 前向回放（冻结参数）截至 {s['newest_minute']}", "",
             f"参数冻结于 {s['freeze_as_of']}（{s['freeze']}），之后不再调整。"
             f"每组回放到各自最后一条有效分钟；停更的组标为 stale，不计入 history。", "",
             f"模拟结果，非实盘：分钟末 L1 视为双腿同时全成；主情景每腿每次成交加 "
             f"{BASE.slip_bps:g} bps 不利滑点；期末持仓按 bid/ask 扣费扣滑点估值；资金费取各交易所"
             "公开逐小时费率，其中落在采集缺口（>3 分钟）内的部分另列，那段时间仓位不可观测。"
             "未计 USDG/USDC 兑换、成交失败、真实深度。", "",
             "| 对 | 截至 | 小时 | 分钟/缺口(最长min) | 中枢/上/下 bps | 成交批次 | 回到空仓 | "
             "期末Entropy仓位$ | 清算估值$ | 资金费$(缺口内) | 合计$ | "
             + " | ".join(f"{sc.label} 合计$(批次/空仓)" for sc in others) + " |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
             + "---:|" * len(others)]
    for key, e in s["pairs"].items():
        pr = e["params"]
        band = f"{pr['midline_bps']:+.1f}/{pr['upper_bps']:.1f}/{pr['lower_bps']:.1f}"
        if e.get("status") != "ok":
            lines.append(f"| {key} | {e['status']} | | {e['minutes']} | {band} |"
                         + " |" * (6 + len(others)))
            continue
        main = e["scenarios"][BASE.label]
        extra = " | ".join(
            f"{e['scenarios'][sc.label]['net_after_funding_usd']:+.3f} "
            f"({e['scenarios'][sc.label]['fills']}/{e['scenarios'][sc.label]['flat_returns']})"
            for sc in others)
        lines.append(
            f"| {key} | {e['test_end'][5:16]} | {e['hours']:.1f} | "
            f"{e['minutes']}/{e['gaps_gt3min']}({e['max_gap_minutes']:.0f}) | {band} | "
            f"{main['fills']} | {main['flat_returns']} | {main['entropy_position_usd']:+.0f} | "
            f"{main['liquidation_usd']:+.3f} | {main['funding_usd']:+.3f}"
            f"({main['funding_in_gaps_usd']:+.3f}) | {main['net_after_funding_usd']:+.3f} | "
            f"{extra} |")
    lines += ["", "“回到空仓”统计 Entropy 仓位归零的次数；批次不等于完整往返。"
              "期末仍有仓位时，合计中包含未实现估值。", ""]
    return "\n".join(lines)


HISTORY_FIELDS = ["run_newest_minute", "pair", "scenario", "test_end", "hours", "minutes",
                  "gaps_gt3min", "gap_minutes", "fills", "flat_returns",
                  "entropy_position_usd", "liquidation_usd", "funding_usd",
                  "funding_in_gaps_usd", "net_after_funding_usd", "max_drawdown_mid_usd"]


def append_history(path: Path, s: dict) -> None:
    new = not path.exists()
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HISTORY_FIELDS)
        if new:
            writer.writeheader()
        for key, e in s["pairs"].items():
            if e.get("status") != "ok":
                continue
            for label, sc in e["scenarios"].items():
                writer.writerow(dict(
                    run_newest_minute=s["newest_minute"], pair=key, scenario=label,
                    test_end=e["test_end"], hours=round(e["hours"], 2),
                    minutes=e["minutes"], gaps_gt3min=e["gaps_gt3min"],
                    gap_minutes=round(e["gap_minutes"], 1),
                    fills=sc["fills"], flat_returns=sc["flat_returns"],
                    **{k: round(sc[k], 4) for k in
                       ("entropy_position_usd", "liquidation_usd", "funding_usd",
                        "funding_in_gaps_usd", "net_after_funding_usd",
                        "max_drawdown_mid_usd")}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=str(ROOT / "logs/forward"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    freeze_p = sub.add_parser("freeze", help="fit and freeze thresholds now")
    freeze_p.add_argument("--fit-hours", type=int, default=48)
    freeze_p.add_argument("--as-of",
                          help="freeze at this earlier ISO time (default: newest common minute)")
    freeze_p.add_argument("--hl-address", default=os.environ.get("HL_ACCOUNT_ADDRESS") or None,
                          help="use this account's HL fee tier (default: base tier)")
    run_p = sub.add_parser("run", help="replay minutes after the freeze")
    run_p.add_argument("--freeze", help="freeze directory (default: newest active)")
    args = parser.parse_args()
    (freeze if args.cmd == "freeze" else run)(args)


if __name__ == "__main__":
    main()
