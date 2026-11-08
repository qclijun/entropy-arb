# Ondo Perps 交易 API 与保证金规则核实

日期：2026-11-08（周日，ET 07:08 取证）。来源：官方文档 `docs.ondoperps.xyz`（Mintlify，`/llms.txt` 索引 171 页全量抓取后检索）+ 未认证公开 GET `api.ondoperps.xyz`。未登录、未用凭据、未下单。

## 结论

**能程序化交易。** API Key 走 HMAC 签名的 REST 下单/撤单/批量下撤，WS 推送私有订单/成交，并支持 post-only（会撞单就拒，返回 400，不会改价）、按账户的死人开关、沙盒环境。**没有改单接口**，重挂只能撤单再下。阻碍决策的有三点：
1. **限频说法冲突**：Public Beta 页写默认 1 次/秒，Spot 指南写下单 30 次/秒、账户级动作 30/s，Spot 与 Perps 共享。账户实际限额 UNKNOWN。按 1 次/秒算，多市场持续重挂不可行。
2. **断线不补发**：没有序列号，只能用 REST 对账补齐。
3. **周末内部 oracle 由盘口冲击价驱动**：我方挂单可能推动周末 oracle 和 mark。

## 事实表

| # | 事实 | 来源 | 状态 |
|---|---|---|---|
| 1 | REST 认证有两种。一是 API Key：请求头 `ONDO-KEY-ID` / `ONDO-TIMESTAMP`（毫秒）/ `ONDO-SIGN`，签名为 hex(HMAC-SHA256(secret, timestamp+METHOD+path含query+body))，时间戳最多落后服务器 10s、超前 1s。二是 SIWE 登录换 JWT（Bearer） | [api_key_authentication](https://docs.ondoperps.xyz/api-reference/api_key_authentication.md)、[create-order](https://docs.ondoperps.xyz/api-reference/orders/create-order.md) securitySchemes、[get-siwe-login-challenge](https://docs.ondoperps.xyz/api-reference/auth/get-siwe-login-challenge.md) | VERIFIED |
| 2 | API Key 在网页端创建，可选权限范围（scope）。可设 IP 白名单，最多 16 个 IPv4；白名单为空时允许任意 IP | [api_key_authentication](https://docs.ondoperps.xyz/api-reference/api_key_authentication.md) | VERIFIED |
| 3 | 下单 `POST /v1/perps/orders`，类型 limit/market，TIF 只有 GTC/IOC，另有 `postOnly`、`reduceOnly`、`clientOrderId`（≤64 位，字母数字及 `_-`），可附 TP/SL | [create-order](https://docs.ondoperps.xyz/api-reference/orders/create-order.md) | VERIFIED |
| 4 | 批量下单 `POST /v1/perps/orders/batch`，单批最多 20 单，非原子（可能部分成功），无内部错误即返回 2XX | [create-batched-orders](https://docs.ondoperps.xyz/api-reference/orders/create-batched-orders.md) | VERIFIED |
| 5 | 撤单有三种：单撤 `DELETE /v1/perps/orders/{orderID}`（可用 `client:{clientOrderId}`）、批撤 `DELETE /v1/perps/orders/batch?orderIDs=...`、全撤 `DELETE /v1/perps/orders`（可限定单个市场） | [cancel-order-by-id](https://docs.ondoperps.xyz/api-reference/orders/cancel-order-by-id.md)、[batch-cancel-orders](https://docs.ondoperps.xyz/api-reference/orders/batch-cancel-orders.md)、[cancel-all-orders](https://docs.ondoperps.xyz/api-reference/orders/cancel-all-orders.md) | VERIFIED |
| 6 | **无改单（amend/replace）接口**：API 索引中只有 get/create/batch/cancel 类订单接口。文档明确写批量“不是原子的撤单再下单”，且 Spot 与 Perps 用的是同一套接口 | [llms.txt](https://docs.ondoperps.xyz/llms.txt)、[spot-api-guide §8](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md) | VERIFIED |
| 7 | post-only：下单时会撮合即拒，返回 400 `post_only_has_match`，文档未提到改价或滑价模式 | [create-order](https://docs.ondoperps.xyz/api-reference/orders/create-order.md) | VERIFIED |
| 8 | 自成交防护：新单若会撞上本账户挂单，**被撞的挂单撤销**，新单继续成交 | [order-types](https://docs.ondoperps.xyz/order-types.md) | VERIFIED |
| 9 | post-only 新单遇本账户反向挂单时，是触发 SMP 撤旧单还是直接拒新单，文档未写 | — | UNKNOWN |
| 10 | 下单其他拒单码包括 `insufficient_margin`、`too_many_open_orders`、`order_price_outside_safe_bounds`、`trading_disabled`、`must_use_delayed_path`、`account_in_liquidation` 等 | [create-order](https://docs.ondoperps.xyz/api-reference/orders/create-order.md) | VERIFIED |
| 11 | 单账户最大挂单数（`too_many_open_orders` 阈值）未公开 | — | UNKNOWN |
| 12 | 文档只在 Spot 写了“delayed 下单路径”（被拒后需改走 `/delayed` 并重签）。Perps 下单也可能返回 `must_use_delayed_path`，但 Perps 文档未列出对应 delayed 端点 | [spot-api-guide §5](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md)、[create-order](https://docs.ondoperps.xyz/api-reference/orders/create-order.md) | UNKNOWN（Perps 侧） |
| 13 | WS 地址 `wss://api.ondoperps.xyz/ws`，登录支持 JWT 或 API Key，签名为 HMAC-SHA256(secret, time+"ondo_perps_ws_login")。单条消息上限 32KB，限频 25 req/s（burst 50），空闲 180s 断开，需 `{"op":"ping"}` 保活 | [connection/connect](https://docs.ondoperps.xyz/api-reference/connection/connect.md)、[connection/login](https://docs.ondoperps.xyz/api-reference/connection/login.md) | VERIFIED |
| 14 | WS 客户端操作只有 ping/login/subscribe/unsubscribe/sendMessage，**文档未提供 WS 下单**，下单只能走 REST。`sendMessage` 的用途未说明 | [connection/connect](https://docs.ondoperps.xyz/api-reference/connection/connect.md) | VERIFIED（无 WS 下单）/ UNKNOWN（sendMessage） |
| 15 | 私有频道有 `ordersPerps`、`fillsPerps`、positions、balance、liquidation、order-summaries 等，可按 markets 过滤 | [perps-orders](https://docs.ondoperps.xyz/api-reference/private-channels/subscribe:-perps-orders.md)、[perps-fills](https://docs.ondoperps.xyz/api-reference/private-channels/subscribe:-perps-fills.md) | VERIFIED |
| 16 | **断线不补发**：只在订阅期间推送，断线期间的成交会丢失。没有全局序列号，也没有原子账户快照。官方流程是重连→登录→重订阅→缓冲事件→REST 拉挂单和重叠时段成交→按 fill `id` 去重。补成交可用 `GET /v1/perps/fills`（支持 startTime/endTime/cursor） | [integration_guide「Resynchronize」](https://docs.ondoperps.xyz/api-reference/integration_guide.md)、[spot-api-guide「Recover after a disconnect」](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md)、[get-fills](https://docs.ondoperps.xyz/api-reference/fills/get-fills.md) | VERIFIED（原文写在 builder/spot 指南中，未单独针对 perps 频道表述） |
| 17 | 死人开关 `cancelAllOrdersAfterPerps`（`timeout_seconds`）：超时未收到心跳即撤掉全部挂单。Spot 版另写明：作用于整个账户、断线后仍保持武装、收到 ping 会重置计时、服务重启后不保证生效 | [perps-dead-mans-switch](https://docs.ondoperps.xyz/api-reference/private-channels/subscribe:-perps-dead-mans-switch.md)、[spot-api-guide §12](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md) | VERIFIED（Perps 细节只能参照 Spot 版推断） |
| 18 | **限频冲突**：Public Beta 页（lastmod 2026-11-05）及 2026-07 changelog 写“API 默认 1 request/second，可邮件 support@ondoperps.xyz 申请提高” | [public-beta](https://docs.ondoperps.xyz/public-beta.md)、[changelog](https://docs.ondoperps.xyz/changelog.md) | VERIFIED（原文） |
| 19 | **限频冲突**：Spot 指南（lastmod 2026-10-02）的“标准默认值”为下单/撤单 30/s（burst 60）、批撤 10/s、全撤 2/s、其他接口 10/s。另有账户级下单与撤单各 30 动作/s（burst 60），**Spot 与 Perps 共享**，一批 N 单计 N 个动作，多开 Key 不增加额度。超限返回 HTTP 429 | [spot-api-guide §10](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md) | VERIFIED（原文） |
| 20 | 本账户实际生效的限额（1/s 还是 30/s），以及 Perps 各端点的具体限额 | — | UNKNOWN |
| 21 | 价格/数量精度看 `/v1/markets` 的 `quoteIncrement`/`baseIncrement`，必须为其整数倍。实测 SNDK-USD.P 为 0.1 / 0.001，DRAM 0.01 / 0.1，CRCL 0.01 / 0.1 | [create-order](https://docs.ondoperps.xyz/api-reference/orders/create-order.md)、公开 GET `https://api.ondoperps.xyz/v1/markets`（2026-11-08） | VERIFIED |
| 22 | Perps 最小下单量和最小名义额。只有 Spot 写明“最小 = 1 个 baseIncrement，无最小名义额”；观测到 SNDK 有 0.001 的成交，但不能据此证明最小单量 | [spot-api-guide §4](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md)、`/v1/perps/trades?market=SNDK-USD.P` | UNKNOWN（Perps） |
| 23 | 价格保护：Perps 挂单以 mark 为参照校验，允许区间按市场不同。GTC 只限制方向（买价过高或卖价过低才拒），被动方向偏离远不会被拒；Spot 回退值为 10% | [mark-price-protection](https://docs.ondoperps.xyz/mark-price-protection.md)、[spot-api-guide](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md) | VERIFIED（Perps 具体百分比 UNKNOWN） |
| 24 | **挂单占保证金**：每个市场 `used_margin = max(buy_side_margin, sell_side_margin) + open_losses`，挂单与持仓一起计入，多空两侧取较大值而非相加。挂单“预留保证金但不影响强平价” | [leverage](https://docs.ondoperps.xyz/leverage.md)、[positions-balances](https://docs.ondoperps.xyz/positions-balances.md)、[def](https://docs.ondoperps.xyz/def.md) | VERIFIED |
| 25 | 挂单 `buy_side_margin` 按挂单价还是 mark 计价、`open_losses` 的定义 | — | UNKNOWN |
| 26 | 全仓（无逐仓），初始保证金 = 名义额/杠杆（杠杆为 1..市场上限的整数，可逐市场设置）。实测 SNDK-USD.P：maxLeverage 5，MMR 10%，单档 $1M，`maxPositionBaseSize` 650。Public Beta 期间单市场持仓上限 $1M | [leverage](https://docs.ondoperps.xyz/leverage.md)、[public-beta](https://docs.ondoperps.xyz/public-beta.md)、`/v1/markets` | VERIFIED |
| 27 | 强平：`margin_balance < total_maintenance_margin` 触发。先禁新单并撤全部挂单；再用限价单在盘口平仓（名义额 > $1k 时每次约 10%，间隔 5s），收 1.5% 强平费；约 1 分钟后保险基金介入，可放宽到 mark 的 5% 以内，之后 ADL | [def](https://docs.ondoperps.xyz/def.md)、[auto-deleveraging](https://docs.ondoperps.xyz/auto-deleveraging.md) | VERIFIED |
| 28 | 周末强平按实时 mark 进行（持仓与抵押品都实时盯市，无冻结） | [weekend-mechanics](https://docs.ondoperps.xyz/weekend-mechanics.md) | VERIFIED |
| 29 | 交易时段 24/7（可能因公司行动等暂停）。实测佐证：周日 ET 07:05 SNDK-USD.P 仍有成交，`tradingState`=TRADING | [markets](https://docs.ondoperps.xyz/markets.md)、`/v1/perps/trades?market=SNDK-USD.P` | VERIFIED |
| 30 | `/v1/markets` 的 `schedule.openHours`（ET，按周日到周六）对 SNDK/DRAM/CRCL 为：周日 20:00 起开、周一至周四全天、周五 20:00 止、周六 closed。但这段时间内仍有成交，所以它不是交易时段；推测是外部报价时段。该字段无文档 | `/v1/markets`、[get-markets](https://docs.ondoperps.xyz/api-reference/markets/get-markets.md)（未列此字段） | UNKNOWN（字段语义） |
| 31 | 周末定义的文档自相矛盾：weekend-mechanics 写周末为周五 20:00 至周日 20:00 ET；weekend-trading 写外部 feed 在周五 16:00 ET 收盘后冻结 | [weekend-mechanics](https://docs.ondoperps.xyz/weekend-mechanics.md)、[weekend-trading](https://docs.ondoperps.xyz/weekend-trading.md) | VERIFIED（矛盾本身）/ UNKNOWN（实际切换时刻） |
| 32 | 休市定价：内部 oracle 从周五最后一个外部价起步，按 impact bid/ask 以 EMA 调整，τ 默认 1 小时，Δt 上限为 τ 的 10%；某侧深度不足时该侧不参与调整。外部数据恢复后下一次更新直接跳回外部价 | [weekend-trading](https://docs.ondoperps.xyz/weekend-trading.md) | VERIFIED |
| 33 | mark 取三者中位数：oracle、oracle + 150s 基差 EMA、中位数(best bid, best ask, last)。每次更新最多变动 50bps。周末 mark 被限制在 参考价 ×(1 ± 1/max_leverage) 内（SNDK 5x 即 ±20%），不重锚；超出区间的买单（高于上界）和卖单（低于下界）受限 | [weekend-trading](https://docs.ondoperps.xyz/weekend-trading.md) | VERIFIED |
| 34 | 计算 impact 价所用的“配置交易额”：API 返回 `impactPriceQuoteSize: "1000"`，但文档未说明该字段就是这个参数 | `/v1/markets`、[weekend-trading](https://docs.ondoperps.xyz/weekend-trading.md) | UNKNOWN（对应关系） |
| 35 | 沙盒环境 `api.ondoperps-sandbox.xyz` / `wss://api.ondoperps-sandbox.xyz/ws`，提供演示资金，接口与生产相同 | [integration_guide「Sandbox vs Production」](https://docs.ondoperps.xyz/api-reference/integration_guide.md) | VERIFIED |
| 36 | 超时后应先用原 `clientOrderId` 查询再重下。重复使用已被接受的 ID 返回 `clientOrderID_collision`；超时后马上查到“不存在”也不能证明该单不会成交 | [spot-api-guide §9](https://docs.ondoperps.xyz/api-reference/spot-api-guide.md) | VERIFIED |

## 对策略的含义（推断，非来源事实）

- 重挂 = 撤单 + 下单，每次 2 个动作。若默认限额是 1/s，单市场双边每次重挂约需 4 秒，必须先向 support 申请提额（#18–20）。
- 周末 oracle 跟随 impact 价（#32、#34）。如果每边 $1k 的冲击价落在我方 3–5bps 的挂单上，我方报价会推动周末 oracle 和 mark，按 mid 重挂可能形成自我反馈。这需要在 ticket 06（报价规则）里决定。
- 挂单按 max(两侧) 占保证金（#24），双边对称挂单不会重复占用。SNDK 5x 意味着每 $5k 挂单约占 $1k 初始保证金（按 1/杠杆 推算）。

## 未公开 / 待向官方确认

#9 post-only 遇自成交的处理、#11 最大挂单数、#12 Perps delayed 路径、#14 sendMessage、#20 实际限频、#22 Perps 最小单量、#23 Perps 价格保护百分比、#25 挂单保证金计价基准、#30 schedule 字段语义、#31 周末切换时刻、#34 impact 数量参数。
