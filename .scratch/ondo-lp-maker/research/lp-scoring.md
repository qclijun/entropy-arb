# Ondo Perps 流动性池计分细节核实

核实日期 2026-11-08。只用一手来源：官方文档、官方 X 账号、官方 app 公告页、app 前端静态 JS、未登录可访问的公开 API。未登录，未使用任何凭证。

来源缩写：

- [DOC] https://docs.ondoperps.xyz/usdc-rewards-program.md （官方奖励文档）
- [ANN] https://app.ondoperps.xyz/announcements/usdc-rewards-upgrade （官方公告，发布于 2026-10-27）
- [TOU] https://app.ondoperps.xyz/terms-of-use （服务条款，Last Updated 2026-08-21，第 27 条 Rewards and Promotional Campaigns）
- [SCHED] https://api.ondoperps.xyz/v1/rewards/v2/schedule （公开 API，无需鉴权，2026-11-08 读取）
- [X1020] https://x.com/OndoPerps/status/2112574307305980041 （2026-10-20 预告改版）
- [X1027] https://x.com/OndoPerps/status/2115071268202672591 （2026-10-27 第 1 周上线）
- [X1104] https://x.com/OndoPerps/status/2118057431263571982 及其后续 https://x.com/OndoPerps/status/2118057433549385909 （2026-11-04 第 2 周加码 + 合格市场列表）
- [BETA] https://docs.ondoperps.xyz/public-beta.md 、 https://docs.ondoperps.xyz/changelog.md （API 限频）
- [APP] https://app.ondoperps.xyz/rewards 的页面文案（`__NEXT_DATA__` 中的 i18n `rewardsPage` / `leaderboardPage`）及前端 chunk（`/_next/static/chunks/1049.*.js`）

## 结论表

| # | 问题 | 事实 | 来源 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | k 是否公开 | 只给出概念公式 `Quote Score = Σ(Order Size × e^(−k × Distance from Mid))`，k 值未给出；文档还声明 "The exact calculation and weights may be modified over time" | [DOC] | k = UNKNOWN |
| 2 | k 能否从公开信息推断 | 公开接口里没有任何分数、份额或分市场奖励数据（见 #14–#16），无法反推 k | [SCHED] [APP] | UNKNOWN |
| 3 | 衰减作用范围 | 指数衰减在各带内部同样生效："1 bp 比同额 4 bps 的乘数高" | [DOC] | VERIFIED |
| 4 | 85/10/5 分带与 e^(−kd) 怎样组合 | 文档没说清：是每带各自分池、带内再按 e^(−kd) 分，还是全局一个分数。另有一句 "Liquidity at the best bid or best offer within the reward ranges receives the highest multiplier"，与 "Distance from Mid" 的计法关系未说明 | [DOC] | UNKNOWN |
| 5 | 距离基准 | "Distance from mid is measured from the order book mid price"，即盘口 mid，不是 mark 或 oracle 价 | [DOC] | VERIFIED |
| 6 | 名义额口径 | Order size 按 USD 名义额计 | [DOC] | VERIFIED |
| 7 | 分带权重是否变过 | 10-20 预告为 80/15/5，10-27 上线时改为 85/10/5 | [X1020] [X1027] [ANN] | VERIFIED |
| 8 | 快照频率与随机方式 | "randomized intervals, approximately every minute"，周末照常；每次快照同时评估所有合格市场。间隔分布、种子、能否预测，均未公开 | [DOC] [ANN] | 频率 VERIFIED；随机方式 UNKNOWN |
| 9 | 周内聚合方式 | 每个市场的周奖励 = 你在该市场所有快照平均分中的占比 | [DOC] | VERIFIED |
| 10 | 计分单位：账户还是地址 | 文档只写 "a market maker's share"；奖励 "paid ... directly to your Ondo Perps trading account"；历史接口 `/v1/rewards/v2/history` 需登录（返回 401 auth_missing），按登录账户返回；另一条官方推文提到 "Wallets excluded from USDC Rewards"。平台有子账户（"Sub-accounts hold their own margin and positions"）。子账户是否单独计分、是否与主账户合并，均未说明 | [ANN] [APP] https://x.com/OndoPerps/status/2113316663697330651 | UNKNOWN |
| 11 | 多账户 | ToS 27(f) 禁止 "use of multiple accounts ... for the purpose of qualifying for or maximising rewards"，违者可取消资格、claw back（含已发放）| [TOU] | VERIFIED（子账户是否算 "multiple accounts" UNKNOWN）|
| 12 | 双边与单边 | 不要求双边；"Bid-side and ask-side liquidity are scored independently"，单挂一边即可。两侧是否各占市场预算的一半、还是合池计分，未说明 | [DOC] | 单边可得 VERIFIED；两侧预算怎么分 UNKNOWN |
| 13 | 最小单量 / 在线率 / API | 都没有要求；API 下单与 app 下单同等计算 | [DOC] | VERIFIED |
| 14 | 按 mid 高频重挂、刻意不挂最优价是否违规 | 奖励条款与 ToS 都只列名称：wash trading、self-trading、spoofing、layering、"any other manipulative or abusive trading activity"、"attempting to game the program in any other way"；ToS 禁止行为清单第 (w) 项的兜底是 "activity intended to artificially influence the price, volume, or market conditions"。两处都没给出 spoofing/layering 的定义，也没有撤单率、挂单最短存续时间之类的量化阈值。是否违规、如何认定，由官方 "sole discretion" 决定且为 final | [DOC] [TOU] | 是否违规 UNKNOWN（条款宽泛，裁量权在官方）|
| 15 | 官方对持续报价的表态 | 公告原文："consistent quoting earns the most"，"a smaller book quoted tightly can out-earn a larger one quoted wide" | [ANN] | VERIFIED |
| 16 | 违规后果 | 违规活动不计入奖励；可 withhold、reduce、reclaim 奖励，并移出计划；ToS 写明可追回已发放部分 | [DOC] [TOU] | VERIFIED |
| 17 | 重挂频率的硬约束 | API 默认限频 1 request/s，可发邮件到 support@ondoperps.xyz 申请提高；有 batch 下单 / 撤单接口和 dead man's switch | [BETA] https://docs.ondoperps.xyz/llms.txt | VERIFIED |
| 18 | 其他活动的反刷单口径 | 10-13 的手续费返还活动排除 "positions closed within 5 minutes of opening and self-matched fills"。这条是否适用于流动性池，未说明 | https://x.com/OndoPerps/status/2110005408714686475 | 对流动性池 UNKNOWN |
| 19 | 合格市场如何变化 | 列表 "subject to change over time. Any changes are announced at the start of a reward week"；文档页同步更新。第 1 周（10-27）与第 2 周（11-04 推文）都是同一组 20 个市场，含 SNDK、DRAM、CRCL、SOXL。没有公开的入选或剔除标准 | [ANN] [X1104] [DOC] | 变化机制 VERIFIED；入选标准 UNKNOWN |
| 20 | 预算如何变化 | 流动性池在所有合格市场之间均分（第 1 周每市场 5,000 USDC）。每周二 00:00 UTC 公布当周预算和上周结果。但第 2 周的加码（100K→112.5K）是 11-04 19:06 UTC 才发推宣布的，已在周中 | [DOC] [ANN] [X1104] | VERIFIED |
| 21 | 已排期预算 | 公开 schedule 接口：W1（10-27 起）maker/taker/activity = 100K/100K/20K；W2（11-03 起）112.5K/112.5K/25K；**W3（11-10 起）125K/125K/30K，W3 activity 仍为 open_interest**。W3 合格市场列表未在接口中出现 | [SCHED] | W3 预算 VERIFIED（接口数据，官方尚未发布公告）；W3 市场 UNKNOWN |
| 22 | 改版期限 | "will run through the end of the year and continue after that unless otherwise stated"；官方可随时修改、暂停或终止 | [X1020] [DOC] | VERIFIED |
| 23 | 历史结果是否公开 | 奖励页只有 "Your Reward" 个人发放历史（需登录）。公开榜单有两类：`/v1/points/leaderboard`（Ondo Points 总分）和 `app.ondoperps.xyz/api/leaderboards/usdc-campaign`（PnL、成交量、ROI，钱包地址打码），都不含流动性池分数、份额或分市场奖励 | [APP] https://api.ondoperps.xyz/v1/points/leaderboard https://app.ondoperps.xyz/api/leaderboards | 流动性池历史份额 = UNKNOWN（未公开）|
| 24 | 能否用公开数据校准份额 | 不能。唯一的路径是用自己账户的历史：前端字段显示每周只有 `makerUSDC` 等分池总额。是否按市场拆分，UNKNOWN | [APP] chunk 1049 | UNKNOWN |
| 25 | 旧计划规模 | 6 月起累计发放 3.5M+ USDC，旧计划每周 175K，按交易活动分配 | [ANN] [SCHED 旧版 https://api.ondoperps.xyz/v1/rewards/schedule] | VERIFIED |

## 对决策的含义（只陈述，不估算）

- 在 3–5 bps 挂单的得分折扣取决于 k 和 #4 的组合方式，两者都 UNKNOWN。官方页面与公开接口都没有任何可校准的数据，只能拿自有账户小额实测后，用 history 反推。
- 合规上，没有条款明文允许或禁止按 mid 持续重挂、或刻意挂在次优价。认定完全靠官方裁量，并可追回已发奖励。默认 1 req/s 限频本身就约束了重挂频率。
- 子账户能否并行计分 UNKNOWN，ToS 明确禁止用多账户套奖励，不能把拆账户当作放大份额的手段。

## 已查但未找到

- Wayback 没有该文档页的存档（CDX 返回空），无法核对文档的历史版本。
- 官方 X 时间线（2026-09-16 至 2026-11-08，共 162 条）里没有公布过 k、快照算法或周度流动性池结果。
