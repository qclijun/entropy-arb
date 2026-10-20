# Live arbitrage opportunity scan (2026-10-20)

Type: research
Status: finding recorded
Blocked by:

## Question

At the current market state, are there executable price differences between
Entropy (Hyperliquid `io` dex) and the supported hedge venues?

## Method

Public data only, read-only. Startup catalogs from all three venues, then
full L2 depth from both legs (Hyperliquid REST `l2Book`; zkLighter via the
project's own websocket `order_book` channel — Lighter publishes no REST
depth). Edges computed at a configurable USD notional after taker fees on
**both** legs (Entropy 0.9bps Growth Mode, verified 2026-10-17; lighter 0bps;
trade.xyz ~1bps).

Two-stage verification, because a single snapshot cannot distinguish an
opportunity from a stale quote:

1. **Sequential re-sampling** (6 rounds, 12s apart) — killed the strongest
   candidate: PRL showed +29bp in one snapshot but averaged −19bp and was
   positive only 17% of the time. Pure noise.
2. **Paired same-clock sampling** — one websocket per venue, both books
   recorded on one clock, so a moving market cannot manufacture an edge.
   Also re-checked with the fetch order reversed (Entropy-first vs
   Lighter-first) to rule out sampling-delay artifacts.

## Eligible universe

Entropy(io) lists 14 perps; 7 are common contracts with a hedge venue.
`H100` is `isDelisted: true` on **both** io and xyz — excluded.
`PRL` and `XIAOMI` exist only on Lighter.

## Findings

Net edge at $1,000 notional, after both legs' taker fees:

| Pair | Mean edge | Positive | Direction |
|---|---|---|---|
| SNDK / lighter | +9.9bp | 120/120 | BUY entropy, SELL lighter |
| DRAM / lighter | +9.1bp | 90/90 | BUY entropy, SELL lighter |
| NBIS / tradexyz | +3.6bp | 80/80 | SELL entropy, BUY tradexyz |
| DRAM / tradexyz | +2.3bp | 80/80 | (one direction only) |

**Size decay is the binding constraint.** Re-walking the book at larger
notional, SNDK/lighter holds +8.2bp at $10k but only +6.7bp at $50k; NBIS
goes negative past ~$10k. The edge is real but thin, and it shrinks exactly
where size grows.

Supporting checks: funding on io is negligible (0.0004%/h ≈ 0.004bp, so the
gap is not funding carry); Lighter multipliers are 1.0 (no scaling); both
venues' marks track the same external reference (Yahoo) within ~2bp.

## Caveats that remain open

- **Contract identity is unverified.** Issue #01 resolved that symbol
  equality does not prove cross-venue equivalence — no venue exposes a
  shared underlying identifier, and `szDecimals`/`maxLeverage` differ for
  every pair checked. These candidates are diagnostic-only until an
  explicit audited equivalence record exists.
- **Quote-basis risk is unmodelled.** Lighter quotes USDC/USDG, Entropy's
  io legs quote USDG. The scanner spec treats them as par and displays the
  risk; at a 2–10bp edge, a basis move of the same size erases it.
- **Execution risk is unmeasured.** These are resting quotes. No leg has
  been tested for fill probability, cancel/replace latency, or partial
  fills across two venues.
- SNDK/lighter-rh is much weaker than the earlier scan suggested (+2.6bp);
  the first pass read the wrong market id (lighter mainnet 139 instead of
  lighter-rh 32). A reminder that venue-specific ids are not interchangeable.

## Conclusion

Real, persistent mispricing exists on SNDK/lighter, DRAM/lighter, and
NBIS/tradexyz at sizes up to roughly $10k, in the 2–10bp range after fees.
It is thin, size-limited, and unproven on execution — consistent with this
being a genuine but heavily-competed inefficiency rather than free money.
