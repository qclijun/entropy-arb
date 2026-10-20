# Entropy Daily Spread Analysis

## Purpose

- Produce the daily spread report for the seven entropy-arb read-only pairs and deliver it to the user in the main chat.

- Never stay silent. The user asked for this report every day, including days when nothing looks tradeable.

## Pair map and data

- Work in `/home/hatch/workspace/projects/entropy-arb` and call the project interpreter at `.venv/bin/python`.

- Analyze SNDK/lighter-rh, EWY/lighter and NBIS/lighter with `--fees-bps 0.9`.

- Analyze DRAM/tradexyz, EWY/tradexyz, NBIS/tradexyz and SNDK/tradexyz with `--fees-bps 1.9`.

- Read each pair from `logs/minutes-<venue>-<SYMBOL>.csv`, for example `logs/minutes-lighter-EWY.csv` and `logs/minutes-tradexyz-SNDK.csv`.

- Remember the history shape. The lighter series start 2026-10-10 with a collector restart on 2026-10-17, the xyz series start 2026-10-17, and all files were renamed to the venue and symbol scheme on 2026-10-21 with history carried into the same files.

## Fee basis

- Treat `--fees-bps` as the two legs combined taker fee for one crossing, entry or exit. Lighter pairs charge 0.9 because the Entropy leg costs about 0.9 bps under Growth Mode and Lighter costs 0. Xyz pairs charge 1.9 because the xyz leg adds an assumed 1.0 bps.

- State the premises when they matter. The xyz 1.0 bps leg is an unverified assumption. If Growth Mode ends and the Entropy leg returns to the standard 9 bps, every conclusion built on 0.9 collapses and the report must say so.

## Procedure

- Check each CSV before analyzing it. Read the line count and the last row timestamp, and mark a pair as data-insufficient instead of inventing numbers when the file is missing or under 60 rows.

- Suspect collector trouble when a file stops growing. The seven record-only processes are kept alive by `tools/watchdog.sh` on a 15 minute cycle, so a stale file means repeated deaths worth one line in the report.

- Run `tools/analyze.py` twice per pair. Omit `--hours` for the full sample, then run again with `--hours 48` for the recent regime.

- Take the suggested `thresholds:` block from each run. The full sample sets the headline midline, upper and lower. The 48 hour run exists to catch midline drift.

- Flag drift when the 48 hour midline differs from the full sample midline by more than 5 bps. Call the full sample thresholds stale for that pair and present the 48 hour values as the tradeable ones.

- Save the seven raw analyze outputs as one text file per pair under `~/workspace/goals/entropy-arb-cross-exchange-arbitrage-scouting/hidden_files/daily-analysis/<YYYY-MM-DD>/`.

## Discounts before concluding

- Treat every threshold as in-sample. The thresholds come from the same data they would trade on, and the 48 hour window is only the least stale view, not an out-of-sample proof.

- Trust the executable edges over mid-price optimism. The analyze suggestions already build on the recorded executable edges, and any extra check should do the same.

- Suspect data quality before signal quality when a window looks abnormally good. The EWY/lighter session on 2026-10-18 carried stale-feed rows for about 40 percent of its minutes.

- Keep excluding the xyz pairs unless their executable numbers change materially. They have never survived their own fee assumption in backtests so far.

## Report shape

- Write in Chinese and lead with the conclusion. Name the pair with the cleanest signal, name the excluded pairs, and say whether any threshold moved enough to matter.

- Give one compact line per pair with its span and sample size, the full sample midline, upper and lower, the 48 hour midline, and the round trip net the two bands imply.

- State the data limits inside the report. Sample sizes differ per pair and the xyz history is still short.

- Log a one line observation to `~/memory/YYYY-MM-DD.md` after delivering. Never edit `MEMORY.md` directly.

## Extension, round trip backtest

- Replay the strategy when the user asks for a backtested return instead of thresholds. Enter when the premium crosses midline plus upper or midline minus lower, and exit when it returns to the midline, reading `logs/minutes-<venue>-<SYMBOL>.csv`.

- Run two calibers and report both. Minute close fills are the optimistic caliber, and fills from `sell_edge_max_bps` and `buy_edge_max_bps` are the executable caliber that matches the engine.

- Deduct the fee per crossing twice per round trip, 0.9 bps per crossing for lighter pairs and 1.9 for xyz pairs.

- Force-close an open trade at the last price before any data gap over 3 minutes and at the end of the file. Count and report the forced exits.

- Report trades, win rate and net bps, and give a dollar figure only at a stated size per leg with the depth caveat attached. Refuse to annualize a sample that holds only a few effective days of minutes.
