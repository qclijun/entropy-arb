# Ondo SNDK 库存的对冲场所比较

日期：2026-11-08（周日，UTC 12:17 取实时快照）。对应 ticket 12。只读：只用公开文档和未认证的公开 API，没有登录、没有读 `.env`、没有下单。本文不选定场所，只给比较结果和证据缺口。Lighter Core 的周末细节见 ticket 03（`weekend-hedge.md`），这里只放到对比层面。

## 数据与口径

- **Ondo 价**：`GET https://api.ondoperps.xyz/v1/perps/trades?market=SNDK-USD.P` 全量翻页，共 361k 笔，时间 2026-10-08 19:45 至 2026-11-08 12:14 UTC。每分钟取成交价中位数（Ondo 价差约 2.4 bps，因此单分钟有约 ±1 bps 的买卖跳动噪声）。没有成交的分钟不参与计算。
- **Entropy、Lighter Core、Lighter RH、tradexyz**：本地 `logs/minutes-{lighter,lighter-rh,tradexyz}-SNDK.csv`，取 hedge_bid/ask 的中价，entropy 取同文件的 entropy_bid/ask。三份文件起点分别为 Core 2026-10-21、RH 2026-10-10、xyz 2026-10-16，终点都是 11-08 12:14 UTC。采集**断断续续**：10-30 那个周末完全缺失，11-06 周末只有 68 分钟。
- **Binance**：`fapi/v1/klines?symbol=SNDKUSDT&interval=1m` 的收盘价，2026-10-10 00:00 至 11-08 12:1x UTC，共 42,507 分钟。
- **基差** = (场所价 / Ondo 价 − 1) × 1e4（bps）。"周末"取 Ondo 文档的内部 oracle 窗口：周五 20:00 至周日 20:00 ET。
- 脚本放在 `/tmp/hv/`（pull.py、live.py、bn.py、fetch2.py、basis.py），没有提交。

## Binance 和 Coinbase：是否上架（先核实）

- **Binance：有。** USDⓈ-M `SNDKUSDT` 的 `contractType=TRADIFI_PERPETUAL`、`underlyingType=EQUITY`、`status=TRADING`，onboardDate 为 2026-04-07（[fapi exchangeInfo](https://fapi.binance.com/fapi/v1/exchangeInfo)，2026-11-08 查询）。现货另有 `SNDKBUSDT`，SNDKB 是 bStocks 代币化股票，`isMarginTradingAllowed=true`（[api/v3 exchangeInfo](https://api.binance.com/api/v3/exchangeInfo?symbol=SNDKBUSDT)）。发行方据第三方资料是 BTech（[CoinGecko](https://www.coingecko.com/en/coins/sandisk-bstocks-tokenized-stock)），官方发行文档未核。下面只比较永续合约，现货只给一行深度。
- **Coinbase：有，但只在 International/Global Exchange（非美国用户）。** Coinbase Exchange 现货与 Advanced Trade 公开产品列表中都没有 SNDK。INTX 公开 API `api.international.coinbase.com/api/v1/instruments` 在 2026-11-08 返回 502，无法取数。官方帮助页列出了 `SNDK-PERP`（USDC 结算、24/7、最高 10x、默认 IM 20%），但页面对本工具返回 403，内容转引自搜索摘要（[产品规格](https://help.coinbase.com/en/international-exchange/stock-perpetual-futures-basics/stock-perpetual-futures-product-specifications)）。因此 SNDK-PERP 已上架这一点只算**部分核实**，Coinbase 的盘口和基差为 UNKNOWN。

## 比较表

深度/成本的口径：2026-11-08 12:17 UTC（周日）**单次**盘口快照。往返成本 = 按名义额吃单的卖出 VWAP 与买入 VWAP 之差（bps），单边成本约为其一半。

| 场所 | 周末可交易 | $5k / $10k / $20k 往返成本 bps | ±25bps 深度（买/卖） | 周末定价机制 | 与 Ondo 机制相似度 | 费率 maker/taker | 资金费 | 保证金/杠杆 | 接入 | 仓库代码 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Ondo**（参照） | 是 | 2.4 / 2.4 / 2.5 | $295k / $384k | impact 价 EMA，τ=1h，步长上限 0.1τ，外部价恢复后下一 tick 即跳回 | — | 1 / 2.5（11-13 起 2 / 5） | UNKNOWN（未取数） | 5x，MMR 10% | 见 ondo-trading-api.md | `tools/ondo_lp.py`（只读，仅在主工作区） |
| **Lighter Core** | 是（实测 24h 量 $7.6M） | 1.23 / 1.38 / 1.58 | $734k / $1.07M | 外部价 stale（通常超过 1 分钟）即切内部价：impact 价时间加权 EMA，τ=30min，impact 价差超过 1% 的更新忽略；新外部价一到立即切回。11-08 API 显示 `internal_price`，`price_cap_bps=0` | 高（同为 impact EMA，τ 为 Ondo 的一半；按 stale 触发而非按时刻表） | 0 / 0（API；Standard 档 taker 延迟 300ms） | 周末均值 +0.044 bps/h，工作日 +0.267 | 默认 IMF 6.66%（15x），最低 5%（20x），MMF 3% | 钱包账户，SDK 签名 | `entropy_arb/venue_lighter.py`（taker IOC），market_id 139 |
| **Lighter RH** | 是（24h 量 $8.7M） | 2.34 / 2.77 / 3.36 | $282k / $178k | API 同样为 `internal_price`。RH 专属文档没有写定价，按推断与 Core 是同一套软件，但订单簿和流动性独立 | 推断为高（未核实） | 0 / 0（API） | 周末 +0.039，工作日 +0.169 | 默认 IMF 50%（2x），最低 10%（10x），MMF 6% | Robinhood Chain，USDG 入金；准入地区 UNKNOWN | `venue_lighter.py`，market_id 32；ws 端点为 `?readonly=true`，实盘需改 |
| **tradexyz**（`xyz:SNDK`） | 是（24h 量 $23.0M，OI 166k 股） | 0.99 / 1.60 / 2.23 | $219k / $241k | 周五 20:00 至周日 20:05 ET 为内部价：impact 价连续时间 EMA，τ=30min（2026-04-30 从 1h 下调），步长上限 c=0.1，某侧深度不足时该侧不参与；外部价恢复后下一 tick 跳回；mark 含 150s 基差 EMA | **最高**（与 Ondo 公式几乎一样，只是 τ=30min 对 1h） | Growth Mode 0.3 / 0.9 bps（docs Tier 0；repo 配置约 1.0） | 周末 +0.050，工作日 +0.175 | 最高 10x，支持全仓/逐仓 | HL 钱包，无 KYC；可与 entropy 共用账户 | `entropy_arb/venue_hl.py`（IOC），dex xyz |
| **Entropy**（`io:SNDK`） | 是（24h 量 $5.9M） | 3.42 / 4.83 / 6.52 | **$23k / $29k** | 休市时 oracle = 内部价与外部价按流动性加权混合，内部权重上限 0.95；内部价为 mid 的 EMA（半衰期 5min）；外部价若无获批盘后场所则冻结在最后一个 tick；mark 截在 ±1/ℓmax 内；开盘第一个可见 tick 切回公开价 | 低（输入是 mid EMA 而非 impact 价，并与冻结外部价混合） | Growth Mode 0.3 / 0.9 | 周末 +0.004，工作日 +0.211；休市乘数 m=0.125（盘中 0.5） | 最高 15x | HL 钱包，无 KYC | `venue_hl.py`，dex io；引擎把 entropy 固定为其中一条腿 |
| **Binance**（`SNDKUSDT` 永续） | 是，24/7（周末日量 $58M–$621M） | **0.12 / 0.23 / 0.98** | **$1.40M / $1.85M** | `tradingSchedule` 中周五 20:00 至周日 20:00 ET 为 `NO_TRADING`（指底层停市，合约照常交易）。股票类 TradFi 永续自 2026-05-16 起周末用 Orderbook EWMA：指数取本合约 impact mid 做 EWMA 平滑，有变化上限；τ 未公开 | 中高（同为 impact 类 EWMA，参数不透明） | **UNKNOWN**（官方费表未取到；第三方称促销为 0 / 4 bps，标准 USDⓈ-M 为 2 / 5） | 8h 结算，上限 ±2%；周末 59% 的结算为 0，均值 −0.025 bps/h；工作日 +0.253 | 最高 10x（Academy），exchangeInfo 中 required 5% / maint 2.5%，强平费 1.5% | 需 KYC，并签 TradFi 协议（`POST /fapi/v1/stock/contract`）；地区限制 UNKNOWN；**以 USDT 计价** | 无 |
| **Coinbase INTX**（`SNDK-PERP`） | 文档写 24/7 | UNKNOWN（API 502） | UNKNOWN | 周五 20:00 至周日 20:00 ET：内部指数 = 本合约 mark 的 1h EMA，可用时结合代币化股票 feed；周五以 19:55–20:00 的 5 分钟 TWAP 为锚，单股钳位 ±5%；周日 20:00 用 30 分钟线性 bridge 回到外部价 | 中高（τ=1h 与 Ondo 相同，但输入是 mark 而非 impact 价；回切是平滑 bridge，不是跳回） | UNKNOWN | 1h 结算，Premium=(mark−index)/index/24 | 最高 10x，默认 IM 20% | 仅非美国用户；准入 UNKNOWN | 无 |

参考：Binance 现货 SNDKB 往返成本 0.99 / 2.29 / 3.69 bps，现货 24h 量 $4.6M。

## 周末基差（相对 Ondo，bps）

**整体水平**（全样本中位数，RTH = 工作日 10:00–15:30 ET，夜盘 = 20:00–04:00 ET）：

| 场所 | RTH 中位 | 夜盘中位 |
|---|---|---|
| Entropy | +1.2 | +4.6 |
| Core | +8.7 | +8.7 |
| RH | +5.4 | +5.6 |
| xyz | +4.0 | +3.4 |
| Binance | +18.6 | +20.2 |

Binance 高出的约 11 bps 来自计价货币：同时点 USDCUSDT = 1.00113（[ticker](https://api.binance.com/api/v3/ticker/price?symbol=USDCUSDT)），以 USDT 对冲会附带一份 USDT/USD 敞口。

**各周末**（周五 20:00 至周日 20:00 ET），格式为 中位 [p5, p95] / 标准差：

| 周末（周五） | Entropy | Core | RH | xyz | Binance |
|---|---|---|---|---|---|
| 10-09 | 样本不足（n=71） | 无数据 | 样本不足（n=71） | 无数据 | 18.3 [14.5, 22.6] / 2.9 |
| 10-16 | 11.5 [2.3, 24.7] / 9.4 | 无数据 | 5.7 [−3.0, 14.3] / 9.7 | 5.0 [−4.3, 14.6] / 9.6 | 23.4 [15.5, 32.3] / 9.4 |
| 10-23（n=814） | 3.6 [−4.5, 10.1] / 5.0 | 9.4 [2.7, 15.8] / 4.6 | 3.9 [−4.2, 10.3] / 4.8 | 3.6 [−2.1, 10.1] / 4.4 | 19.4 [13.0, 25.2] / 4.4 |
| 10-30 | 无数据 | 无数据 | 无数据 | 无数据 | 17.5 [12.3, 23.9] / 4.1 |
| 11-06（截至周日 07:14 ET） | 样本不足（n=68） | 样本不足 | 样本不足 | 样本不足 | 19.5 [13.1, 25.4] / 4.3 |

各场所周末标准差相近（同一周末 4–10 bps），说明这部分波动有不少来自 Ondo 一侧（成交价跳动加 oracle 的 EMA 滞后），不是某个对冲场所独有。

**周日 20:00 ET 与周一 09:30 ET 的跳变**：跳变 = 基差中位数的前后变化。"周日 20:00"比较 19:00–19:55 与 20:10–21:00，"周一 09:30"比较 09:00–09:29 与 09:35–10:00。

| 周末 | Binance 周日 20:00 | Binance 周一 09:30 | Binance \|周一开盘后基差 − 周末各分钟基差\| 中位 / p90 |
|---|---|---|---|
| 10-09 | +2.9 | +3.3 | 2.8 / 5.8 |
| 10-16 | −7.6 | +4.8 | 3.3 / 9.1 |
| 10-23 | −0.7 | −3.4 | 2.3 / 6.1 |
| 10-30 | −3.4 | +9.3 | 12.4 / 16.5 |

- **本地三场所和 entropy 只有 10-16 一个周末有开盘前后数据：**

  | 场所 | 周日 20:00 跳变 | 周一 09:30 跳变 | \|开盘后 − 周末\| 中位 / p90 |
  |---|---|---|---|
  | RH | −9.0 | +5.6 | 4.4 / 10.5 |
  | xyz | −13.6 | +4.3 | 4.8 / 11.1 |
  | Entropy | −15.4 | −9.5 | 15.5 / 24.1 |

  同一周末 Binance 为 −7.6 / +4.8 / 3.3 / 9.1。
- 解读：周末在任一场所对冲、持有到周一开盘，相对 Ondo 的基差变化（即对冲误差）典型值为 2–12 bps，p90 为 6–17 bps。只有一个周末的数据时，entropy 明显更差。样本只有 1–4 个周末，**不足以排序**。

## 资金费

工作日的数据点是 2026-10-10 至 11-08 每小时的资金费率。周末均值的口径是 Fri20–Sun20 ET 窗口，共 229 个小时点；Binance 是 29 次 8 小时结算，已折算成每小时。单位为 bps/h，正值表示多头付费：

| 场所 | 周末均值 | 工作日均值 |
|---|---|---|
| Binance | −0.025 | +0.253 |
| Entropy | +0.004 | +0.211 |
| xyz | +0.050 | +0.175 |
| Core | +0.044 | +0.267 |
| RH | +0.039 | +0.169 |

按每个周末 48 小时折算，各场所周末资金费都在 ±2.5 bps 以内，量级小于基差跳变。Ondo 的资金费未取数，所以两腿的资金费净差为 UNKNOWN。

## 证据缺口（UNKNOWN）

1. **Coinbase SNDK-PERP 的盘口、费率、基差**：INTX API 返回 502，帮助页返回 403。规格只能转引搜索摘要。
2. **Binance TradFi 永续的官方费率**、Orderbook EWMA 的 τ 和变化上限、用户所在地区能否签 TradFi 协议。
3. **Lighter RH 的周末定价文档**（目前只有 API 字段佐证）和 RH 的账户准入。
4. **深度只有一次周日快照**，没有周末时序，也没有周一开盘前后的深度。可以给 `tools/ondo_lp.py sample` 补采各对冲场所的深度。
5. **本地分钟数据断档**：Core、RH、xyz、entropy 只有 10-16 一个周末能算开盘跳变，10-30 整个周末缺失。11-09 周一开盘后可以补算 11-06 这个周末。
6. **Ondo 周末 oracle 的实际切换时刻**（文档自相矛盾，见 ondo-trading-api.md #31）和 Ondo 的资金费。
7. Binance 以 USDT 计价，USDT/USD 波动对对冲的影响没有量化；样本期 USDCUSDT ≈ 1.0011。
8. 仓库只有 HL（io/xyz）和 Lighter（Core/RH）的 taker 连接器，引擎把 entropy 固定为一条腿。没有 Ondo、Binance、Coinbase 的交易代码。

## 来源

- Ondo：[weekend-trading](https://docs.ondoperps.xyz/weekend-trading.md)，以及本目录 `ondo-trading-api.md`
- trade.xyz：[oracle-price](https://docs.trade.xyz/perpetuals/mechanics/oracle-price.md)、[oracle-time-constant-updates](https://docs.trade.xyz/perpetuals/changelog/oracle-time-constant-updates.md)、[equities-internal-session-hours](https://docs.trade.xyz/perpetuals/changelog/equities-internal-session-hours.md)、[fees](https://docs.trade.xyz/perpetuals/mechanics/fees.md)、[margin-modes](https://docs.trade.xyz/perpetuals/risk-and-margining/margin-modes.md)
- Entropy：[oracle-price](https://docs.entropy.io/equity-perp-mechanics/oracle-price.md)、[funding-rate](https://docs.entropy.io/equity-perp-mechanics/funding-rate.md)、[fees](https://docs.entropy.io/equity-perp-mechanics/fees)
- Lighter：[internal-pricing-mechanism](https://docs.lighter.xyz/trading/internal-pricing-mechanism.md)、[RWA market-specifications](https://docs.lighter.xyz/trading/real-world-assets-rwas/market-specifications.md)、[priceOracleInfo](https://docs.lighter.xyz/api/info/priceoracleinfo.md)、[trading-fees](https://docs.lighter.xyz/trading/trading-fees)、[Robinhood Chain Lighter Domains](https://docs.robinhood.com/chain/lighter-domains/)；API `/api/v1/{orderBookDetails,orderBookOrders,priceOracleInfo,fundings}`（Core 与 RH，2026-11-08）
- Binance：[stock perps（Academy）](https://www.binance.com/en/academy/articles/how-to-trade-stock-perpetual-contracts-on-binance)、[derivatives change log](https://developers.binance.com/docs/derivatives/change-log)；`fapi/v1/{exchangeInfo,depth,premiumIndex,fundingInfo,fundingRate,klines,tradingSchedule}`
- Coinbase：[stock perps 价格机制（帮助页）](https://help.coinbase.com/en/global-exchange/stock-perpetual-futures-basics/how-do-stock-perpetual-futures-stay-in-line-with-the-underlying-stock-or-equity-index-price)、[产品规格](https://help.coinbase.com/en/international-exchange/stock-perpetual-futures-basics/stock-perpetual-futures-product-specifications)；两页内容均经搜索摘要转引
- 仓库：`record/hedge-markets.json`、`entropy_arb/{config,venue_hl,venue_lighter}.py`、`docs/go-live-checklist.md`（主工作区）
