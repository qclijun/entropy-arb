# Maker 成交与 RH 对冲：接口保证核查

核查日期：2026-11-07。范围仅公开官方文档与官方 SDK；未访问账户、钱包、凭据或下单。Context7 先解析 Arcus/Lighter，再定位官方原文；以下是当日规范，不证明历史版本或生产端点实现已经逐项通过测试。Arcus 原文 OpenAPI 标记 `openapi-2026.11.06`。

## 结论

官方接口具备 post-only、成交增量/订单累计状态、历史补查以及 RH 带最差价格的 IOC 等构件，可以进入适配器与恢复协议设计。**IOC 不保证全成，ACK 不代表成交或撤单完成，client ID 不等于永久幂等键；跨平台 exactly-once 没有获得官方保证。** 当前基线仍是双 taker 同发，不能把既有终态 future 直接当作 maker 持续成交对冲器。

## Arcus

| 项目 | 官方已明确行为 | 实施边界 |
| --- | --- | --- |
| post-only | `ALO` 是 Add Liquidity Only；跨价会以 `POST_ONLY_WOULD_CROSS` 拒绝。 | 必须以引擎结果识别已挂上/被拒，不能以本地盘口判断替代。[下单](https://docs.arcus.xyz/api-reference/exchange/place-order.md) |
| 下单/撤单确认 | 常见响应 `202` 仅转发撮合引擎；`200` 是网关已知明确状态。下单须订阅 `orders`，逐笔交易另用 `userFills`。cancel 的 `202 CANCEL_ACKNOWLEDGED` 不是已撤终态，`200` 可含状态及 `filledSize`/`remainingSize`。 | 取消期间成交仍须核算；超时不能当作零成交。[下单](https://docs.arcus.xyz/api-reference/exchange/place-order.md)、[撤单](https://docs.arcus.xyz/api-reference/exchange/cancel-order.md) |
| 改单 | 保留 `orderId`、创建时间和已有 fill 状态；`quantity` 是包含已成交量的新**总量**。同价缩量保留队列位置；改价/增量重新排队。ALO 改单不会主动吃单。 | 引擎收到改单时先发 `CANCELED/MODIFY_CANCELED`，再发新状态；引擎拒绝新单也会移除原单；HTTP 400 则原单不变。不能把第一个 CANCELED 当作整个逻辑订单结清。[改单](https://docs.arcus.xyz/api-reference/exchange/modify-order.md) |
| 成交标识 | REST fills 的统一 Fill 模型也用于 WS 快照/更新；必需 `tradeId`（unique trade identifier）、`orderId`、`size`、价格、费用、角色和微秒时间。store-only 字段可在流式帧缺失。 | 去重应包含环境/账户/订单上下文；唯一性跨环境范围、完整流重放及 exactly-once **UNKNOWN**，不能凭字段名假定全局永久唯一。[fills](https://docs.arcus.xyz/api-reference/public/get-fills.md) |
| 累计量/顺序 | 单订单 REST 有 `originalSize`、`remainingSize` 和 `filledSize=originalSize−remainingSize`；orders 更新包含原量、余量、累计均价和账户 `sequenceNumber`。 | 修改会改变总量，不能只按原量减少推算成交；账户序号可排序，不应借用 L2 连续 +1 保证判定订单流丢帧。[订单状态](https://docs.arcus.xyz/api-reference/public/get-order-status.md)、[orders](https://docs.arcus.xyz/api-reference/account/orders.md)、[WS](https://docs.arcus.xyz/api-reference/websocket.md) |
| 断线补查 | orders 订阅快照含全部 open 与最多 100 条、28 天内的最近 closed；userFills 订阅含 recent fills。REST fills 可按 `from/to` 微秒窗口查询，history 返回 open/filled/canceled/rejected；单订单路径是 `/v1/order/{orderId}`。 | 快照有界，不能作为任意停机时长的完整成交账本。历史分页必须完整走完并保留重叠去重；完整历史保留期、持久游标恢复和读取滞后上界 **UNKNOWN**。[orders](https://docs.arcus.xyz/api-reference/account/orders.md)、[userFills](https://docs.arcus.xyz/api-reference/account/userfills.md)、[fills](https://docs.arcus.xyz/api-reference/public/get-fills.md)、[history](https://docs.arcus.xyz/api-reference/public/get-order-history.md) |
| 客户标识 | 活跃 `clientId` 重复会拒绝；终态释放该 slot；每账户最多 10,000 活跃 client IDs。cancel/modify 可按 clientId 定位。 | 重试已终态订单时可能重新创建，不能声称端到端幂等；请求结果不明时先查订单/历史/fills。没有取得“按已结束 clientId 永久查询”的明确保证。[下单](https://docs.arcus.xyz/api-reference/exchange/place-order.md)、[改单](https://docs.arcus.xyz/api-reference/exchange/modify-order.md) |
| 限频 | 每 IP 1,500 weight 桶、每分钟回补 1,500；账户 placement/cancel 分池并随成交量增加。429 含 Retry-After；`/v1/rateLimit` 只报告账户池。耗尽后每池 10 秒一个 action；dead-man scheduleCancel 消耗 cancel 池。 | 撤单/重挂/断线补查必须预算，不能把不同连接当成独立额度。具体账户可用池及交易时延未经账户验证。[限频](https://docs.arcus.xyz/api-reference/rate-limits.md) |

## Lighter RH

RH 官方说明使用与主网相同 transaction format、signer、REST、WS，因此一般接口文档适用；但它是独立交易所，账户、余额、API key、nonce、account index 不共享，需匹配 RH base URL 与 chain ID。[RH 专页](https://docs.lighter.xyz/developers/robinhood-chain/overview.md)

| 项目 | 已明确行为及限制 |
| --- | --- |
| IOC/价格保护 | 官方 trading 文档把 taker `price` 定义为最差可接受价，无法在该价或更优成交的余量取消。官方 Python `create_market_order_limited_slippage` 以 ideal price 和 max_slippage 计算价格，发送 MARKET+IOC，传递 `reduce_only`。价格边界并不保证数量全部成交，也不保证对冲价差或最终收益。[trading](https://apidocs.lighter.xyz/docs/trading)、[官方 SDK](https://github.com/elliottech/lighter-python/blob/main/lighter/signer_client.py) |
| reduce-only | 减仓到零；超出现有仓位的部分取消。适合退出/纠偏，不能把需要新开反向腿的 hedge 默认标为 reduce-only。[订单类型](https://docs.lighter.xyz/trading/order-types-and-matching.md) |
| 客户 ID/nonce | `client_order_index` 需跨市场唯一，用于改撤/查询；官方 core-concepts 区分 API/应用前失败与执行中拒绝是否消耗 nonce，重复 clientOrderIndex、错误 reduce-only 等执行中拒绝会消耗 nonce。nonce 消耗不代表有成交，恢复不能只看 nextNonce。[get-started](https://apidocs.lighter.xyz/docs/get-started)、[core-concepts](https://apidocs.lighter.xyz/docs/core-concepts) |
| 结果不明的可查询信息 | `/api/v1/accountOrders` 接受 account_index 与 client_order_indexes；Order 返回 status、filled_base_amount、filled_quote_amount、remaining_base_amount 等。`trades` 可按账户/订单查询，含 trade_id、tx_hash、size/price。`tx` 支持按 hash 或 sequence_index 查询。查询结果需与订单成交量及仓位交叉核对；未查到不等于交易未发生。[accountOrders](https://docs.lighter.xyz/api/orders/accountorders.md)、[trades](https://docs.lighter.xyz/api/orders/trades.md)、[tx](https://docs.lighter.xyz/api/transactions/tx.md) |
| 延迟/限频 | RH Standard：taker 300 ms、maker/cancel 200 ms；sendTx/sendTxBatch within 60 req/min，非 sendTx REST 60 req/min。Plus/Premium 不同，不能套用 Core 档位；标准账户逐次 fill→hedge 与补查会竞争预算。[RH 专页](https://docs.lighter.xyz/developers/robinhood-chain/overview.md) |

RH **UNKNOWN**：client ID 去重保留期/终态复用规则；accountOrders 的保留窗口与最坏可见性延迟；WS 任意断线完整补发、重复投递和 exactly-once；未知提交结果下重复发送完全相同签名的明确生产保证。这些需要规范补证和隔离测试，不可因未找到说明就宣称功能不存在。没有连接账户，因此实际 RH SPY 市场、最小量/精度/账户档位也未验证。

## 与现有引擎对照及交接

基线使用父 agent 已核实的 [engine-baseline](../assets/engine-baseline.md)，未重复探索代码：engine.py:434–437 同时 gather 双腿 send_taker；Lighter MARKET IOC；AccountOrdersFeed 忽略 open、在终态用累计量完成 future。启动严格仓位读取和周期对账可复用，但不能证明 maker 在途恢复已经具备。

后续需在设计票落实：持久化 maker/hedge 意图和确定的 ID；按增量 fill 产生尚未对冲量；记录 IOC 实际成交而非目标量；cancel/modify 状态与成交竞态处理；UNKNOWN 提交结果先查询再决定重试；重启先补 orders/fills、匹配在途 hedge，再恢复报价。仓位对账能发现净量偏差，不能独自证明逐笔 hedge 去重或准确历史损益。

本阶段目标是核实 Arcus maker 生命周期与 RH IOC 能支撑的执行保证。产出仅此研究 Markdown，未改实现、未交易、未连接账户。官方资料确认 ALO 拒绝跨价、改单总量与双事件、成交标识及累计状态、有限快照和历史查询；RH 确认共享接口规范、IOC 余量取消、价格界限、reduce-only 与独立 nonce/账户。验证采用 Context7 与官方公开原文/SDK；没有运行实盘或接口集成测试。待办为去重期限、断线重放、查询滞后和未知提交恢复的明确补证及隔离测试。证据链接逐项附上；提交及分支推送结果由交接消息报告。
