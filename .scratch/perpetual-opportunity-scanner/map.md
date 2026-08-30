# Specify the Entropy-Anchored Perpetual Opportunity Scanner

Label: wayfinder:map

## Destination

Produce an implementation-ready specification for a read-only, continuously refreshed scanner that discovers and ranks executable price differences between Entropy and lighter, lighter-rh, and trade.xyz across their common perpetual contracts.

## Notes

- Domain language lives in [`CONTEXT.md`](../../../CONTEXT.md); every session must consult and maintain it with the `domain-modeling` skill.
- Use `grilling` for product decisions, `research` for external venue facts, `prototype` for terminal interaction, and `codebase-design` for module seams.
- The scanner is Entropy-anchored, public-data-only, and strictly separate from trade execution.
- The agreed baseline uses one configurable USD scan notional, taker fees on both legs, complete-depth fills, a one-second terminal refresh, startup-only market discovery, and exact include/exclude filters.
- GitHub Issues are disabled for this repository, so this local Markdown tree is the canonical tracker.

## Decisions so far

- [Verify venue market catalogs and contract metadata](issues/01-verify-venue-market-catalogs.md) — Public catalogs discover candidates but cannot prove cross-protocol equivalence; ranking requires explicit auditable mappings.
- [Verify public multi-market streaming capacity](issues/02-verify-streaming-capacity.md) — Three multiplexed sockets fit the known protocol shape; Lighter's unpublished hard limits require configurable sharding and diagnostics.

## Not yet specified

- Final specification structure and any additional test seams depend on the contract-identity, feed-architecture, and evaluation-model decisions.

## Out of scope

- Automatic or manually triggered trade execution.
- Arbitrage pairs that do not include Entropy.
- Historical opportunity persistence or replay.
- Live USDG/USDC quote-basis normalization; the first version treats them as par and displays the risk explicitly.
- Runtime discovery of newly listed or delisted contracts.
- Multiple simultaneous scan notionals.
- Web UI, service API, or structured machine-output modes.
- Account-specific fee discovery or any requirement for private credentials.
- Long-duration live venue soak testing; the specification may preserve a configurable sharding seam without making rollout depend on a live soak.
