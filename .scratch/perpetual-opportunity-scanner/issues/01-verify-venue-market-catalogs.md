# Verify venue market catalogs and contract metadata

Type: research
Status: resolved
Blocked by:

## Question

Using primary sources and representative first-party API responses, what public catalog endpoints and contract metadata are available on Entropy, lighter, lighter-rh, and trade.xyz, and which fields can reliably establish that two listings represent the same perpetual exposure?

## Comments

- Claimed during initial charting for parallel research.

## Answer

All four venues expose unauthenticated startup catalogs, but none supplies a shared cross-protocol underlying identifier. Normalized symbols and available metadata may generate candidates, but admission to the ranked Common Contract set must use an explicit, auditable equivalence record that preserves raw venue identifiers, asserted underlying identity and provenance, multipliers, quote assumptions, and basis-risk flags. Exact-name candidates without sufficient evidence remain diagnostic-only; aliases such as `io:ANTH` to `ANTHROPIC` must be explicit.

Research asset: branch `research/venue-market-catalogs`, commit `06ce7918f0e086b66e14a70e0844aa1e746e1710`, path `.scratch/perpetual-opportunity-scanner/research/venue-market-catalogs.md`.
