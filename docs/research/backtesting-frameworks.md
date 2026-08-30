# 两场所套利回测框架调研

调研日期：2026-08-29。仅采用框架维护者的官方 GitHub 仓库/文档。

## 策略和数据约束

`Engine._scan()` 每次行情更新会同时评估两个方向；`plan_arb()` 以买方 ask、卖方 bid、**两腿各自的 taker fee** 和深度来确定可成交数量。随后策略还会处理信号持续时间、冷却、各场所持仓上限和库存惩罚、订单频率、双腿部分成交及净 delta 补单。

当前 `MinuteRecorder` 的每行却只是每分钟最后一个 L1 bid/ask（另有分钟内价差统计），没有逐笔时间、各价位尺寸、成交量或两腿真实回报。因此回测最多能在每根一分钟 bar 的收盘快照上，按「假定立即、完全吃到该 bid/ask」重放；它不能验证队列位置、冲击成本、分钟内 persistence，或真实的部分成交概率。这个限制来自本仓库的数据格式，而不是回测框架。

## 候选比较

| 框架 | 与本项目所需能力的匹配 | 主要代价/缺口 |
| --- | --- | --- |
| [vectorbt](https://github.com/polakowo/vectorbt) | `Portfolio.from_order_func` 允许每个时间步运行自定义逻辑；`flexible=True` 允许一个 bar 内为同一 symbol 产生多笔订单。订单可传 `fees`，并可按列使用不同费率；列和分组/cash-sharing 可表达多资产组合。适合作为快速参数扫描、敏感性分析的加速器。 | 为复刻双腿原子执行、每场所独立现金/仓位、持仓梯子及未匹配腿补单，必须把状态机重写为 NumPy/Numba 回调；其官方说明也明确没有完整订单管理，命令会立即成交/拒绝，且期货高级保证金不是其强项。它不能从本 CSV 补回丢失的订单簿深度。 |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader)（事件驱动） | `BacktestEngine` 可直接控制场所、instrument、内存数据和策略；官方示例可把 bid/ask CSV 转为 `QuoteTick`，并使用 L1 盘口。可配置 `HEDGING` OMS 和保证金账户，适合保留两条腿的独立头寸；其 `FillModel` 可配置限价成交概率与市价滑点。适合日后拿到逐笔 quote/L2 数据后，做延迟、部分成交、订单状态和资金/保证金更逼真的回测。 | 必须把本 CSV 转成两个 venue/instrument 的 `QuoteTick`，再重写策略、合约定义和账户配置；只有当前 L1 分钟快照时，模型仍无法合理推断深度、队列或部分成交。对第一版而言，框架复杂度远高于收益。 |

## 推荐

第一版采用**轻量、仓库内的事件回放器**，不新增第三方回测框架：逐行读一个 hedge 专属 `logs/minutes-<hedge>.csv`，把每行当成同时可见的 L1 快照，并复用（或严格镜像）现有的阈值、费用、仓位上限、库存惩罚、persistent/cooldown 和净 delta 规则。每一笔应输出订单/成交账本、两场所仓位、现金、费用、配对/未配对量和 mark-to-market PnL。这样结果可直接审计，并且不会把「一分钟关闭快照」伪装成可验证的撮合仿真。

填充假设应显式做成参数：基准为两腿以同一行的 ask/bid 全额成交；悲观情形至少包含额外 bps 滑点、单腿失败/部分成交率、以及下一根 bar 才能补 hedge。策略不能使用同一根 bar 的 `high/max` 来决定当根是否成交，以避免前视偏差。

数据升级为逐笔 quote（带两边价格和尺寸）或 L2 快照、订单发送/回报时间戳和资金费率后，再评估迁移 NautilusTrader。vectorbt 则保留给在已验证的简化模型上批量扫描 `midline_bps`、上下阈值、滑点和费率情景。

## 官方依据

- vectorbt 的 [`Portfolio.from_order_func` 源码与 API 文档](https://github.com/polakowo/vectorbt/blob/master/vectorbt/portfolio/base.py) 说明自定义订单回调、`fees`、`cash_sharing` 和 `flexible=True`；其中的文档还说明 flexible 模式解除「每个 tick/symbol 一笔订单」的限制。
- vectorbt 维护者在[官方仓库讨论](https://github.com/polakowo/vectorbt/discussions/185)说明其订单会立即执行/拒绝、没有完整订单管理，且高级保证金和期货交易不是其覆盖重点。
- NautilusTrader 的[回测 API 文档](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/concepts/backtesting/apis-and-runs.md)说明低层 `BacktestEngine` 与场所配置；[高层回测示例](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/getting_started/backtest_high_level.py)展示 CSV bid/ask 到 `QuoteTick` 的转换。
- NautilusTrader 的[一分钟 bid/ask 回放教程](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/tutorials/backtest_fx_bars.py)展示 `QuoteTickDataWrangler.process_bar_data` 和 `FillModel`；其[执行模型文档](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/concepts/execution.md)说明 `HEDGING` 可保留多个头寸。
- NautilusTrader 的[回测数据与场所文档](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/concepts/backtesting/data-and-venues.md)明确指出不能由低粒度 quote/bar 生成更高粒度 L2/L3 数据。
