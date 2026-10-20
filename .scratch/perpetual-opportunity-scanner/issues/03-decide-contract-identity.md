# Decide canonical contract identity and matching policy

Type: grilling
Status: open
Blocked by: 01

## Question

Given the venue metadata actually available, what canonical identity, normalization rules, metadata checks, explicit alias schema, and unmatched-market diagnostics should determine whether two listings form a Common Contract?

## Answer

No venue exposes a shared cross-protocol underlying identifier (issue #01). So
identity cannot be *discovered* — it must be *asserted and recorded*, then
defended against drift. The policy below splits those two jobs deliberately:
an equivalence ledger for what we assert, and startup reconciliation for
whether the assertion still holds.

### Canonical identity

**Underlying ID, not ticker.** A `UnderlyingId` is a stable, human-authored
slug (`sandisk`, `dram`, `nebbius`, `ishares-ewy`, `xiaomi`) that names the
economic exposure. Tickers are venue *listings* of that underlying, never the
identity itself. Two listings match iff they resolve to the same
`UnderlyingId` — never because their symbols are equal.

Normalization (uppercase, strip separators, collapse `IO:`/`XYZ:` prefixes) is
applied only to *generate candidates* and to *look up* in the ledger. It is
never sufficient on its own to admit a pair.

### The equivalence ledger

A checked-in, human-editable file (`config/contract-equivalence.yaml`) is the
single source of truth, one record per underlying:

```yaml
sandisk:
  listings:
    io:      {market: SNDK}
    lighter: {market_id: 139, quote: USDC}
    lighter-rh: {market_id: 32, quote: USDG}
    xyz:     {market: SNDK}
  quote_basis: mixed      # USDC and USDG both present
  provenance: "operator-verified 2026-10-20; both legs track SNDK spot"
  multiplier: {io: 1.0, lighter: 1.0, lighter-rh: 1.0, xyz: 1.0}
```

Per-venue entries carry the *raw* venue identifier (HL coin name, Lighter
numeric `market_id`) because those are not interchangeable — during this
research a scan read Lighter mainnet's `market_id=139` while intending
lighter-rh, whose SNDK is `market_id=32`, producing a fictitious +10bp edge
that was really +2.6bp. `provenance` is mandatory and dated: it is the audit
trail for *why* a human believed the match, which is the only evidence that
exists.

### Metadata checks (consistency, not proof)

Ledger assertions are cross-checked at startup against live catalogs. These
checks **gate rankability** but never create identity:

- **Existence & liveness** — every asserted listing must be present and not
  `isDelisted`. A delisted listing disqualifies the pair (`H100` is
  `isDelisted: true` on both io and xyz and is excluded).
- **Size decimals** — recorded per venue and carried into the scan notional
  conversion. `szDecimals` legitimately differs across venues (io:SNDK=4,
  xyz:SNDK=3) so it is *not* an identity check; it is a quantity-rounding
  input.
- **Multiplier** — must be recorded; a multiplier ≠ 1 must be normalized
  before any price comparison. All Lighter perps are currently 1.0.
- **Quote asset** — recorded per listing. `quote_basis: mixed` sets the
  quote-basis-risk flag (issue #05 must display it; USDC/USDG are not
  normalized in v1).

A metadata *mismatch* (e.g. an asserted `market_id` that no longer exists, or
a listing that changed venue) is a **loud startup failure naming the record**,
never a silent drop — a pair vanishing from the ranking is the one failure
mode that looks like "no opportunity".

### Diagnostic-only candidates

Exact-name matches absent from the ledger are surfaced separately, ranked or
labelled `diagnostic`, and **never** admitted to the ranked Common Contract
set. Today that set is 7 symbols (`SNDK`, `DRAM`, `NBIS`, `EWY`, `PRL`,
`XIAOMI`, `H100`) of which `H100` is delisted. This keeps the scanner honest
about what it does not know instead of silently widening its universe.

Aliases are explicit ledger records, not inference: `io:ANTH` maps to
`ANTHROPIC` because a human wrote it down. The reason is that ticker
collisions are *latent*, not hypothetical — `io:XIAOMI` at ~$3.41 is a real
match to Xiaomi (HK$26.66 ≈ US$3.41), but nothing in the venue data *proves*
that, and a future `io:PRL`-style token or a re-used ticker would silently
become a ranked "opportunity" if matching were name-based. Name equality
correlates with truth today; it must not be the mechanism.

### Unmatched-market diagnostics

At startup, report three explicit sets so an empty ranking is explainable:

1. **unmatched on Entropy** — io listings with no ledger entry and no
   same-name candidate (today: `ANTH`, `GPRO`, `IONQ`, `MOONSHOT`, `OAI`,
   `SBE`, `TCNT` — no hedge venue at all).
2. **candidate, not admitted** — same-name matches with no ledger record
   (diagnostic-only).
3. **asserted but absent** — ledger entries whose listings no longer exist
   (the loud-failure case above).

### Open risk to carry forward

Identity here is *asserted*, not proven. The strongest available corroboration
is price agreement: the four live pairs (SNDK, DRAM, NBIS, EWY) track the same
external reference (Yahoo) within ~2bp and each other within ~10bp, which is
consistent with — but not proof of — shared underlying. `PRL`'s 128bp io-vs-
lighter gap is unexplained and is a reason to keep it out of the ledger until
someone verifies what it is. Issue #05 must therefore keep quote-basis risk
visible next to every edge, since a 2–10bp edge is the same magnitude as the
residual uncertainty this policy accepts.
