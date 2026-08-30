# Verify public multi-market streaming capacity

Type: research
Status: resolved
Blocked by:

## Question

Using primary sources, what subscription shapes, connection/subscription limits, rate limits, heartbeat requirements, and reconnect constraints govern public order-book streaming for Entropy, lighter, lighter-rh, and trade.xyz at the scale of every common contract?

## Comments

- Claimed during initial charting for parallel research.

## Answer

Public depth can be multiplexed over three steady-state WebSockets: one Hyperliquid connection for Entropy and trade.xyz, one for Lighter mainnet, and one for lighter-rh. Hyperliquid documents IP-wide limits of 10 connections, 30 new connections per minute, 1000 subscriptions, and 2000 client messages per minute. Lighter's official SDK supports many order-book subscriptions on one socket, but no official connection or subscription ceiling was found; configurable sharding and observable subscription failures therefore remain required safety valves. Reconnects replay desired subscriptions, while a Lighter nonce gap invalidates only its affected market.

Research asset: branch `research/public-streaming-capacity`, commit `5e69fe228a05407b1f94d512534f74b33b546f29`, path `.scratch/perpetual-opportunity-scanner/research/public-streaming-capacity.md`.
