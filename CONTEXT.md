# Entropy Arbitrage

The domain language for discovering and evaluating perpetual-futures price
differences between Entropy and supported hedge venues.

## Language

**Opportunity Scanner**:
A read-only, continuously refreshed view of price-difference opportunities across the eligible market universe. It discovers and ranks opportunities but never executes trades.
_Avoid_: Screener, trading engine, auto-trader

**Entropy-Anchored Pair**:
The same perpetual contract represented by Entropy on one side and exactly one supported hedge venue on the other.
_Avoid_: Venue pair, cross pair

**Common Contract**:
A perpetual contract listed on Entropy and a supported hedge venue whose normalized identity and available contract metadata establish that both listings represent the same underlying exposure.
_Avoid_: Shared symbol, matching ticker

**Eligible Market Universe**:
The automatically discovered common contracts that remain after configured inclusion and exclusion filters are applied.
_Avoid_: Symbol list, scan list

**Raw Spread**:
The price difference implied by the best opposing quotes of an Entropy-anchored pair, before fees and order-book depth are accounted for.
_Avoid_: Profit, edge

**Executable Net Edge**:
The estimated return available at the scan notional after order-book depth and fees on both legs are accounted for. It excludes quote-basis risk unless the quote assets have been normalized explicitly.
_Avoid_: Spread, guaranteed profit

**Scan Notional**:
The configured USD-sized amount used consistently to estimate executable net edge across the eligible market universe.
_Avoid_: Order size, quantity

**Quote-Basis Risk**:
The unaccounted value difference between the quote assets of an Entropy-anchored pair, such as USDC and USDG.
_Avoid_: Trading fee, spread

**Trading Direction**:
One of the two ways to cross an Entropy-anchored pair: buy on Entropy and sell on the hedge venue, or buy on the hedge venue and sell on Entropy.
_Avoid_: Side, route

**Rankable Opportunity**:
An Entropy-anchored pair with confirmed contract equivalence, fresh order books, and enough depth on both legs to fill the scan notional. Its better trading direction determines its position in the opportunity scanner.
_Avoid_: Candidate, partial fill
