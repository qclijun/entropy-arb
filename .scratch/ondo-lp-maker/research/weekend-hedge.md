# 周末用 Lighter Core 对冲 SNDK：可行性与库存过周末风险

日期：2026-11-08（周日，约 12:30 UTC）。对应 ticket 03。只读：公开文档和未认证的公开 API，没有登录、没有下单。脚本在 `/tmp/wkh/`，未提交。

## 结论

- **对冲可行**：Lighter Core SNDK 周末照常撮合。价差中位 0.73 bps，±5 bps 内单边 $0.3–0.7M，0 手续费；周末资金费每个周末合计 −1 到 +4 bps。
- **真正的跳空点是周日 20:00 ET，不是周一 09:30。** 两所的外部价（Pyth 隔夜盘）都在周日 20:00 ET 恢复，价格会在一分钟内跳回外部价。起点文档里"周一开盘前撤单"这一条应改为**周日 20:00 ET 前撤单并把库存对冲完或平掉**。
- **未对冲的库存风险大**：从周日 19:55 到周一 09:35，单边价格变动中位 |290| bps，最大 639 bps。仅周日 20:00 那 20 分钟就有中位 |60| bps、最大 122 bps。周末内部（周五 20:00 至周日 19:55）的漂移中位 |65| bps，最大 416 bps。以 $5k 库存计，中位约 $145，最坏约 $320，远超周末奖励约 $62。
- **对冲后的残余风险小**：Ondo 相对 Lighter Core 有约 −8 bps 的持续折价，周末和工作日都存在。基差从周日 19:45 到周一 09:35 的变化中位 |2.7| bps，8 个周末中最大 12 bps。两所在 20:00 同时跳，跳的幅度几乎一样（例如 10-18：Lighter +122 bps，Ondo +121 bps）。

## 数据与口径

- **Lighter Core**：`GET https://mainnet.zklighter.elliot.ai/api/v1/candles?market_id=139&resolution=1m`，1m K 线覆盖 2026-08-31 23:40 至 11-08 12:13 UTC，共 98,674 根。另有 `orderBookOrders` 快照两次（11-08 12:07、12:24 UTC），以及 `fundings` 小时资金费（09-20 至 11-08）。仓库里的 `hedge=lighter` 指向 `mainnet.zklighter.elliot.ai`，与 `lighter-rh`（Robinhood Chain）不同，所以 `minutes-lighter-SNDK.csv` 的 hedge 列就是 Lighter Core（见 `entropy_arb/config.py` 的 `LIGHTER_PROFILES`、`record/config-sndk.yaml`）。
- **Ondo**：`GET https://api.ondoperps.xyz/v1/perps/trades?market=SNDK-USD.P` 全量翻页，共 517k 笔，时间 08-31 23:00 至 11-08 12:11 UTC。没有历史盘口；"价格"取 ≤T 的最后一笔成交，平均距 T 约 1 分钟。
- **本地文件**
  - `logs/minutes-lighter-SNDK.csv`（Entropy × Lighter Core）：10-21 00:15 至 10-25 08:50，加 11-08 09:43 至 12:04 UTC。**不含任何"周日晚→周一开盘"窗口。**
  - `logs/minutes-lighter-rh-SNDK.csv`（Entropy × Lighter RH）：10-10 至 11-08，含 **10-18→10-19** 这一个完整窗口（中间有若干 10–15 分钟缺口）。
  - `logs/ondo-depth.csv`：11-08 10:51 至 12:23 UTC，SNDK 94 行，只有周日白天，**没有采到重开时段**。
- **样本**：周日 09-13 至 11-01，共 8 个周末。09-06 剔除，因为 09-07 是劳动节，Ondo 的 SNDK 时刻表写明 09-06 closed、09-07 20:00 才开。11-08 这个周末未结束。时区：11-01 之前为 EDT（周日 20:00 ET = 周一 00:00 UTC），之后为 EST（= 01:00 UTC）。
- **基差** = Ondo 成交价 / 同一分钟 Lighter (H+L+C)/3 − 1，单位 bps；每个检查点取 10 分钟窗口内的中位数。

## 两所周末定价来源（官方文档）

| 项 | Ondo Perps（SNDK-USD.P） | Lighter Core（SNDK，market 139） |
|---|---|---|
| 外部价 | Pyth 与 Stork 均价，24/5（含隔夜） | Pyth Pro |
| 周末何时切内部价 | 按时刻表：周五 20:00 ET 至周日 20:00 ET。API 中 SNDK 的 `schedule.openHours` 为 Sun 20:00-23:59、Mon–Thu 全天、Fri 00:00-20:00、Sat closed | 按新鲜度：外部价 stale（主网阈值通常 1 分钟）就切。11-08 实测 `priceOracleInfo` 为 `internal_price` |
| 内部价算法 | 用 impact bid/ask（$1,000 规模）做连续时间 EMA，τ=1h，以周五最后外部价为起点 | impact 价做时间加权 EMA，index τ=30min，mark 分量 τ=2min；impact 价差超过 1% 的更新忽略 |
| 价格边界 | mark 限在参考价 ±1/max_lev 内（SNDK 为 5x，即 ±20%），周末不重锚；mark 每次更新最多变 50 bps | 自 2026-07-10 起 SNDK **不设** oracle 相对上限，但仍和其他交易场所做 risk check（阈值酌情调整） |
| 回切 | 外部数据恢复后，下一 tick 回到外部价；mark 每次最多走 50 bps | 一有新鲜外部价就立即切回 |
| 周末资金费 | 照常每小时结算，参考内部 oracle；乘数 0.5，基础利率 0.03%/日，基准约 0.0625 bps/h | 每小时结算；参考的 index 本身来自盘口 |

来源：[Ondo Weekend and Extended Hours Trading](https://docs.ondoperps.xyz/weekend-trading.md)、[Ondo Weekend Mechanics](https://docs.ondoperps.xyz/weekend-mechanics.md)、[Ondo External Pricing Derivations](https://docs.ondoperps.xyz/pricing-derivations.md)、[Ondo Funding Rates](https://docs.ondoperps.xyz/funding-rates.md)、`https://api.ondoperps.xyz/v1/markets`（SNDK-USD.P 条目，11-08）、[Lighter Internal Pricing Mechanism](https://docs.lighter.xyz/trading/internal-pricing-mechanism.md)、[Lighter RWAs](https://docs.lighter.xyz/trading/real-world-assets-rwas.md)、[Lighter Market Specifications](https://docs.lighter.xyz/trading/real-world-assets-rwas/market-specifications.md)、[Lighter Fair Price Marking / Risk Checks](https://docs.lighter.xyz/trading/fair-price-marking.md)、[Lighter Funding](https://docs.lighter.xyz/trading/funding.md)、`https://mainnet.zklighter.elliot.ai/api/v1/priceOracleInfo`（11-08）。

结论：两边都**不是固定锚点**，都是"本所盘口 impact 价的 EMA"，都在 Pyth 隔夜盘开始时（周日 20:00 ET，Blue Ocean ATS，[Pyth blog](https://www.pyth.network/blog/how-us-equities-actually-trade-sessions-gaps-and-what-most-data-providers-miss)）切回外部价。差别在 Ondo 按时刻表切换，Lighter 按 stale 切换；τ 分别为 1h 和 30min；Ondo 有 ±20% 的边界，Lighter 没有。

## Lighter Core SNDK 周末盘口与资金费

- **价差**：本地 `minutes-lighter-SNDK.csv`（周末行在 10-24/25 和 11-08，n=2061）中位 0.73 bps，p90 1.04。工作日 RTH 中位 0.87、p90 1.48。
- **深度**：11-08 周日两次快照，±2 bps 内买 $245–256k、卖 $340–364k；±5 bps 内买 $315–419k、卖 $634–681k；±25 bps 内买 $712–727k、卖 $865–997k。24h 成交 $7.6M，OI $7.3M（`orderBookDetails`）。
- **成交量**：1m K 线显示，周日 17:00–19:55 ET 约 $3–14k/分钟；20:00 之后升到 $6–22k/分钟。
- **费率与杠杆**：maker/taker 均为 0。SNDK 最低 IMF 5%（20x），默认 6.66%，MMF 3%（API）。
- **资金费**（正值表示多头付）：周末 n=348 小时，中位 0.04 bps/h，p5 −0.57、p95 +0.76。每个周末合计：09-20 +1.4、09-27 +0.9、10-04 +3.1、10-11 +4.3、10-18 +1.3、10-25 +2.5、11-01 +3.0、11-08（未完）−1.0 bps。工作日均值约 0.19 bps/h。

## 跳变分布（8 个周末，09-13 至 11-01）

### 单边价格（bps）

| 区间 | Lighter Core 中位 \|x\| / 最大 | Ondo 中位 \|x\| / 最大 |
|---|---|---|
| 周五 20:00 → 周日 19:55 ET（周末内部漂移） | 65 / 416 | 65 / 412 |
| 周日 19:55 → 20:15（重开跳空） | 60 / 122 | 61 / 121 |
| 周日 19:55 → 周一 09:35 | 292 / 639 | 289 / 635 |
| 周一 09:25 → 09:35（现货开盘） | 96 / 290 | — |
| 周日 19:55 起至周一 09:35 的最大不利偏离（Lighter 1m 高低点） | 326 / 668 | — |

各周末周日 19:55→周一 09:35 的 Lighter 变动：−286、+56、−302、−6、−637、+639、+94、−299 bps。

**20:00 那一分钟是离散跳变**：周日 17:00–19:55 的 1m 收益中位 1–6 bps，20:00–20:03 出现 +68（09-20）、−45（10-11）、+146（10-18）、−46（10-25）等单分钟跳动。周五 20:00 切到内部价时跳得较小：20:00–20:03 单分钟最大 37 bps（10-18），其余多在 ±25 bps 以内。

### 跨所基差 Ondo/Lighter Core（bps，10 分钟窗口中位）

| 周日 | 周五 19:30 | 周日 19:45 | 周日 20:05 | 周一 04:00 | 周一 09:35 | Δ(周日 19:45→周一 09:35) |
|---|---|---|---|---|---|---|
| 09-13 | −13.2 | −10.5 | −13.4 | −14.4 | −10.5 | 0.0 |
| 09-20 | +1.0 | −5.9 | +4.2 | +5.2 | +2.6 | +8.4 |
| 09-27 | −6.7 | −3.7 | −0.6 | −0.1 | −1.0 | +2.7 |
| 10-04 | — | — | −10.6 | −4.0 | −13.5 | — |
| 10-11 | −9.2 | −9.7 | −9.9 | −10.7 | −16.4 | −6.6 |
| 10-18 | −21.4 | −18.0 | −9.2 | −6.4 | −15.6 | +2.4 |
| 10-25 | −13.5 | −6.4 | −16.4 | −11.1 | −18.7 | −12.2 |
| 11-01 | −8.1 | −13.0 | −11.5 | −11.2 | −12.6 | +0.4 |

- Δ(周日 19:45→周一 09:35)：中位 +0.4，中位 |x| 2.7，最大 |x| 12.2（n=7）。Δ(周日 19:45→20:05)：中位 |x| 3.1，最大 10.1。
- 逐笔基差分布（p5 / p50 / p95）：周末 −18.4 / −7.6 / +1.9（n=50.7k）；工作日 −27.3 / −9.6 / +5.3（1/20 抽样）。逐笔数字含 Ondo 买卖跳动和分钟内时间错位，比检查点中位宽。
- 对照（本地 `minutes-lighter-rh-SNDK.csv`，10-18 19:55 → 10-19 10:00 ET）：Lighter RH +633 bps、Entropy +600 bps 至周一 09:35；Entropy/RH 基差从 +13.1 变为 −18.4 bps，摆幅 31 bps。比 Ondo/Core 的摆幅大。

## Ondo SNDK 周末盘口在何时变化

目前没有重开前后的盘口快照（ondo-depth.csv 只有 11-08 白天）。只能用成交做代理，取 8 个周末的平均：

| ET 时段 | 成交笔/h | 成交额/h | 相邻反向成交价差中位（价差代理） |
|---|---|---|---|
| 周五 15:00（现货收盘前） | 503 | $402k | 2.6 bps |
| 周五 20:00–23:00（进入内部定价） | 70–224 | $12–52k | 2.3–2.4 |
| 周六、周日白天 | 54–130 | $8–35k | 1.8–2.6 |
| 周日 18:00–19:00 | 250–301 | $54–72k | 3.1–3.3（最宽） |
| **周日 20:00（重开）** | **647** | **$732k** | 2.4 |
| 周日 21:00 | 571 | $440k | 1.7 |
| 周一 09:00（现货开盘） | 1092 | $780k | 3.3 |

- 11-08 周日白天的实测盘口（ondo-depth.csv，10:51–12:23 UTC）：价差中位 2.4 bps（p10 1.2、p90 3.6）。0–5 bps 内买中位 $132k、卖中位 $150k，但卖方最低时只有 $536。
- 推断：重开前 1–2 小时，成交增加、价差变宽；20:00 成交额约放大 10 倍。挂单的被动成交和逆向选择风险在这一刻最高，与价格跳空同时发生。

## 事实表

| 事实 | 来源 | 状态 |
|---|---|---|
| `hedge=lighter` 即 Lighter Core 主网（market_id 139） | `entropy_arb/config.py`、`tools/venue_costs.py`、orderBookDetails | 已核实 |
| Lighter Core SNDK 周末可交易，周日在用 internal_price，无价格上限 | priceOracleInfo 11-08；internal-pricing 文档（07-10 取消上限） | 已核实 |
| Lighter 内部价：impact EMA，τ=30min（index）/2min（mark），1% 价差过滤，stale 约 1 分钟即切 | Lighter 文档 | 已核实（文档） |
| Lighter SNDK 外部源为 Pyth Pro；周日 20:00 ET 回切 | market-specifications；1m K 线 20:00 跳变 | 来源已核实；回切时刻由数据推断 |
| Lighter Core 周末价差中位 0.73 bps | 本地 csv，10-24/25、11-08 | 已核实（样本少） |
| Lighter Core 周末深度（±5 bps 单边 $0.3–0.7M） | 11-08 两次快照 | 部分核实（单日） |
| Lighter Core 周末资金费每个周末 −1 到 +4 bps | fundings API，09-20 至 11-08 | 已核实 |
| Ondo 周末 = 周五 20:00 至周日 20:00 ET；SNDK 时刻表；内部 oracle τ=1h，impact $1,000 | Ondo 文档 + markets API | 已核实 |
| Ondo SNDK mark 边界 ±20%（5x），mark 每次更新最多 50 bps | Ondo 文档 + API maxLeverage=5 | 已核实 |
| Ondo 周末资金费基准约 0.0625 bps/h | Ondo funding 文档 + API multiplier 0.5 | 公式已核实；实际历史 **UNKNOWN**（未找到公开历史端点） |
| 单边跳变：周日 19:55→周一 09:35 中位 \|290\|、最大 639 bps | Lighter K 线 + Ondo 成交，8 周 | 已核实（n=8） |
| 基差变化（周日 19:45→周一 09:35）中位 \|2.7\|、最大 12 bps | 同上 | 已核实（n=7） |
| Ondo 盘口在重开前后的深度与价差 | — | **UNKNOWN**（只有成交代理） |
| Lighter Core 周末深度的时间变化（重开前后） | — | **UNKNOWN** |
| Lighter risk check 的阈值，以及极端跳空时是否拒绝推价 | 文档称阈值酌情调整 | **UNKNOWN** |
| 节假日周末 Lighter 的行为（如 09-07 劳动节） | — | **UNKNOWN**（未分析） |

## 对后续决策的含义

1. 风控规则改为：周日 19:30 ET 前撤掉 Ondo 挂单；剩余库存在 Lighter Core 对冲完毕，或在 Ondo 平掉；20:00 之后再按工作日规则决定是否挂单。
2. 周末内部也要对冲：周末内部漂移最大约 4%。库存上限应按"未对冲库存 × 4%"不超过奖励来定（例如周末奖励 $62，上限约 $1.5k），超过上限立即在 Lighter Core 吃单。
3. 对冲后的残余是 Ondo/Core 基差：持续 −8 bps 左右，过重开的变化 ≤12 bps。$5k 对冲后的库存过重开的风险约 $6 以内。
