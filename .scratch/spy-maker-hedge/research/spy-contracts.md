# SPY 合约身份、数量与对冲时段核实

核实日期：2026-11-07；只读公共资料。结论：公开目录足以区分两端永续与 RH 现货，但不足以批准自动实盘。**Arcus ≠ 本仓库现有 entropy 路由；Lighter RH SPY 永续 26 ≠ SPY/USDG 现货 2065。** 以下 UNKNOWN 必须保留。

## 来源与采样

每项来源访问日期均为 **2026-11-07**。API 数值仅代表采样瞬间，不是冻结交易配置。

|编号|官方来源与关键证据|
|---|---|
|A1|[Arcus 市场目录](https://api.arcus.xyz/v1/markets)：公共 HTTP 200；SPY 记录摘录见下表。2026-11-07 02:54:31 UTC；响应 SHA256 `640392d385a2b1aed85e0f0f85f826c768889d37af99bb014904957b0550b756`。|
|A2|[Arcus 永续概述](https://docs.arcus.xyz/concepts/perpetuals/overview)：无到期交割；SPY 列在 index ETFs；24/7 包含假日，但须检查 ONLINE/OFFLINE。|
|A3|[Arcus RWA 机制](https://docs.arcus.xyz/concepts/perpetuals/real-world-assets)：RTH 04:00–20:00 ET，节假日/提前收市另处理；USDG 抵押；休市采用较高初始保证金、SOFR funding、内部 mark 与价格带；公司行动进入 oracle。|
|A4|[Arcus 价格](https://docs.arcus.xyz/concepts/perpetuals/prices)：mark 是风险/PnL/清算基准；开市 oracle 使用外部数据，休市依赖内部 mark；公开页未指定 SPY 外部供应商的完整 feed 身份。|
|A5|[Arcus 资金费](https://docs.arcus.xyz/concepts/perpetuals/funding)：每小时收取；RWA 年化基准 SOFR+0.5%，按 360×24 换算；开市加 premium/8，休市切换基准。|
|A6|[Arcus 目录接口规范](https://docs.arcus.xyz/api-reference/public/get-markets) 与 [架构](https://docs.arcus.xyz/concepts/exchange-architecture)：独立 off-chain CLOB/appchain/EVM settlement 架构。|
|L1|[Robinhood 官方 Lighter Domains](https://docs.robinhood.com/chain/lighter-domains/)：RH 与 Core 分离合约、执行、流动性；RH API 为 `api.rh.lighter.xyz`；合约 `0x94bAB9693Ba2f6358507eFfcbd372b0660AFfF9d`；USDG assetIndex=3。|
|L2|[RH orderBookDetails](https://api.rh.lighter.xyz/api/v1/orderBookDetails)：公共 HTTP 200；02:54:31 UTC；SHA256 `c62af8dde554107d26ebaf67865e6ed09e6e399db68c6dffba413f5db96ce74d`。|
|L3|[RH assetDetails](https://api.rh.lighter.xyz/api/v1/assetDetails)：公共 HTTP 200；02:55:26 UTC；USDG=asset_id 3、6 decimals；SPY=asset_id 20；SHA256 `3702cec89a461a6e40cef5b5ab94dbed249ce16b9436aaa97456d985e1f1880c`。|
|L4|[Lighter RH 差异说明](https://apidocs.lighter.xyz/docs/lighter-rh)：经 Context7 官方文档索引实时返回，RH 主抵押为 USDG 6位；公共 API/签名格式沿用，但账户、余额、密钥、nonce 不通用。直连文档本次访问失败，故依据标明为 Context7 抓取。|
|L5|[Lighter 市场数据](https://apidocs.lighter.xyz/docs/market-data) 与 [整数精度](https://apidocs.lighter.xyz/docs/core-concepts)：经 Context7 返回，market_id、size/price decimals、最小数量/金额来自目录，不能照搬主站ID。|
|L6|[Lighter funding](https://docs.lighter.xyz/trading/funding)：每小时整点结算，正费率多付空；position×index×rate；参数按市场目录，默认值非通用。|

API 全量快照只保存在本机 `/tmp/spy-public-0.txt`（RH）、`/tmp/spy-public-1.txt`（Arcus）、`/tmp/spy-extra-2.txt`（RH assets），不作为额外交付资产提交。上述摘录与哈希已在本文固定。部分 docs 根目录、`.md`、RH API 文档直连遭 403/不可访问；没有以历史作者帖代替接口规范。

## 合约身份与数量

|项目|Arcus|Lighter RH|
|---|---|---|
|产品|`SPY-USD`，`fullAssetName=SPDR S&P 500 ETF Trust`，`type=PERPETUAL`，`category=INDICES` [A1,A2]|`symbol=SPY`，`market_type=perp` [L2]|
|市场ID|`marketId=23` [A1]|`market_id=26` [L2]|
|报价|`baseAsset=SPY`、`quoteAsset=USD` [A1]|perp `base_asset_id=0, quote_asset_id=0`，不能据此映射资产币种；USD 名义单位/具体结算字段语义仍需确认 [L2,L3]|
|抵押/结算|USDG 抵押已确认；SPY 盈亏、资金费最终入账币种的接口级约束 UNKNOWN [A3]|主抵押 USDG 6位已确认；不能把 asset_id=0 自动解释成 USDG，SPY PnL settlement 具体约束 UNKNOWN [L1–L4]|
|最小数量|`minOrderSize=0.001` SPY [A1]|`min_base_amount=0.0100` [L2]|
|最小金额|`minOrderNotional=5` USD [A1]|`min_quote_amount=10.000000` [L2]|
|数量步长|`stepSize=0.0000001`；`assetResolution=10000000000` 是另一字段，不应混作数量步长 [A1]|`supported_size_decimals=size_decimals=4`，即数量编码格点 0.0001 [L2,L5]|
|价格精度|当前 `tickSize=0.01`；分档 tick：≤5000 为0.01、≤10000 为0.02、≤20000 为0.05、≤50000 为0.1、≤100000 为0.2，以上0.5 [A1]|`supported_price_decimals=price_decimals=2`；`supported_quote_decimals=6` [L2]|
|乘数|没有明示经济合约乘数字段；`baseAsset=SPY` 暗示按 SPY 基础数量，但 1单位=1股经济Delta 的完整 PnL/公司行动约束 UNKNOWN [A1,A4]|perp `multiplier=1.000000000000000000, quote_multiplier=1`；字段值已确认，但公司行动后的经济数量变化仍须另核 [L2]|
|采样状态|`ONLINE`、`isOutsideRth=true` [A1]|`active`、`is_frozen=false`、`force_reduce_only=false` [L2]|

**禁止误用 RH 现货：** 同一目录另有 `SPY/USDG`、`market_type=spot`、`market_id=2065`、base_asset_id=20、quote_asset_id=3、multiplier=`1.001717991187472003` [L2,L3]。它不是 perp 26；不能将该 multiplier 用到永续，更不能凭符号过滤取第一条。

数量匹配推导（非已验证下单规格）：若双方经济乘数均证实为1，基础量相同才具有一阶数量中性，公共格点为0.0001 SPY；最小量还须同时满足双方 min size 与 min notional，故 `q >= max(0.01,5/P_A,10/P_L)` 并向格点上取整。真实 maker/taker/平仓豁免规则未核实，必须保守要求两项最小值均满足。若乘数为 m_A,m_L，应满足 `q_A*m_A = q_L*m_L`，再考虑离散余量。**当前不能把“双方相同美元金额”视为已证明的数量对冲。**

## 价格、时段与休市

- Arcus 开市使用外部 underlying 数据，同日价值调整进入 oracle；`pythId=1398` 是目录原值，未找到足够公开材料证明它对应哪个完整 Pyth feed，不当作已验证供应商身份。mark 与 oracle 不同，风险取 mark [A1,A4]。
- Arcus RTH=美国交易日04:00–20:00 America/New_York；API 为 start=14400、end=72000、isOvernight=false。此窗口含盘前盘后，**不是只指09:30–16:00现金连续交易**。假日全天 off-hours，提前收市窗口提前结束，应读 `isOutsideRth`/状态，不按台湾固定钟点硬编码 [A1,A3]。
- Arcus perp 可24/7交易，OFFLINE例外。休市初始保证金采样0.03（开市0.02），maintenance=0.013334；内生 mark、价格带约束成交/mark。采样 anchor=736.06、lower=728.70、upper=743.42，全部是瞬时值 [A1,A2,A3]。
- Arcus 下班封存 mark 的5分钟EWMA为anchor，休市 mark 使用 impact mid 的2.5分钟EWMA；band 从0.5x按0.5x/1x/2x/4x阶梯扩展，周末沿用周五anchor。休市风险会内生化，不能把RH报价差直接称无风险价差 [A3]。
- **Lighter RH SPY 交易日历、盘前盘后、周末、节假日、停牌和 stale oracle 行为 UNKNOWN。** 目录 `market_config.trading_hours=""`、start_timestamp=end_timestamp=0 只说明字段空/零，不能据此推断24/7，也不能推断与Arcus同RTH [L2]。Lighter RH 独立部署亦不能由 Core 规则推定 [L1,L4]。
- **Lighter RH SPY index feed供应商、更新时间/陈旧阈值、公司行动及停牌回退规则 UNKNOWN。** 目录仅给 index_price=737.07、mark_price=737.08；与Arcus oracle=736.32的非同步差值不能作可成交套利收益 [A1,L2]。

## Funding 与剩余基差

Arcus：每小时收费；RWA基准 `(SOFR+0.5%)/360/24`，开市加 premium/8（同日oracle），休市只用SOFR基准 [A5,A3]。采样 fundingRate=`0.00000511574074074`、nextFundingRate=`0.00000474537037037`、nextFundingAt=1794020400 [A1]；这些仅为API原值，未凭字段名年化。

Lighter：通用文档为小时整点，正率多付空，以 signed position×index×rate计算；RH文档称沿用API，**RH SPY精确事件时间/费率单位/休市特殊规则仍需RH源验证** [L4,L6]。SPY目录 `base_interest_rate="0.0032"`、`funding_clamp_small="0.0500"`、`funding_clamp_big="4.0000"`、`funding_premium_multiplier=50` [L2]；未获得字段整数/百分率换算的RH专属约束，禁止直接将50或0.0032作为无量纲费率。主站默认参数不得覆写这些实值。

剩余基差（分析推导）：独立订单簿与标记价；现金/盘前盘后/周末不同时段；Arcus休市内部anchor和bands与RH未知fallback；SOFR/同日结算调整差；股息拆股等公司行动差；USD名义与USDG抵押兑价差；funding时点及计算差；数量舍入与未对冲小额。以上都不能仅凭反向同数量仓位消除。

## 与现有 entropy 路由的边界

本地源码证据（不是官网产品事实）：`entropy_arb/config.py:31` 为 `https://api.hyperliquid.xyz`；`:355`默认dex=`io`；`:360–368`构造entropy `kind="hl"`。`config.example.yaml:46–47`同样指向io；`entropy_arb/venue_hl.py:1`解释HIP-3，`:92–96`向`/info`请求，`:100–115`解析perpDexs/meta并构造`io:SYMBOL`。这是 Hyperliquid Entropy 路由，不是上述 Arcus REST/appchain。不能只改SPY符号就声称具备Arcus适配。

核实范围：直接读取上述确切源码段；graph index_status=ready，generation=2026-11-06T18:57:59Z；对 config.py、venue_hl.py、config.example.yaml 做check_index_coverage，均metadata_match、no_recorded_issue。工具明确为best-effort，非完整性证明；未声称完成全仓结构审计。父agent可在主工作区进一步核验。

## 实做前阻塞与交接

1. 需要真正Arcus适配器、对应公开市场/订单字段和账户环境隔离，现有entropy=HL io不能替代。
2. 核实双方经济数量/PnL乘数、SPY公司行动处理、结算币种。RH必须锁定perp26，拒绝spot2065。
3. 补RH SPY的交易日历、休市/停牌、oracle陈旧/回退、资金费费率单位与实收时点。补Arcus OFFLINE/停牌挂单处理细节。
4. 在公开只读行情验证双边可成交深度、时间戳、状态、价格带；只有双边可对冲且数量合规时才可能进入后续执行评估。UNKNOWN应阻止开仓。非同步mark价差不满足该要求。

阶段交接：目标是辨清Arcus与Lighter RH的SPY真实产品和可对冲时段，现已以两份市场目录、RH资产目录及官方概念页建立参数表，并标明现有仓库走Hyperliquid io而非Arcus。已确认Arcus市场23、RH永续26，特别排除RH现货2065；最小量、tick/step与Arcus休市机制已有证据。验证仅公开只读，未连接账户、未交易；交付仅本文，临时API快照及哈希见来源节。待办是经济乘数、结算、RH时段/停牌/oracle与资金费细则；这些仍阻止实盘。提交和推送状态以父agent最终回报为准。
