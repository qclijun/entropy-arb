# 数据与费用口径

## 定位与字段

从当前项目找到 `tools/analyze.py`、`record/` 和 `logs/`。优先使用可用的 `.venv/bin/python`；环境不可用时说明缺项，不自动安装依赖。

已知配对约定如下；以本次实际存在的文件和对应配置为准：

| 对冲场所 | 品种 | CSV | 配置 |
|---|---|---|---|
| lighter | EWY、NBIS | `logs/minutes-lighter-<SYMBOL>.csv` | `record/config-ewy.yaml`、`config-nbis.yaml` |
| lighter-rh | SNDK | `logs/minutes-lighter-rh-SNDK.csv` | `record/config-sndk.yaml` |
| tradexyz | DRAM、EWY、NBIS、SNDK | `logs/minutes-tradexyz-<SYMBOL>.csv` | `record/config-<symbol>-xyz.yaml` |

不要从旧文件名或旧机器路径猜测输入。缺失的配对逐一列出；不足 60 个有效分钟只能展示有限统计，不据此推荐参数或收益排名。

`minute_ts` 是 UTC 分钟标识。`entropy_bid/ask`、`hedge_bid/ask` 是分钟内最后一个有效样本；`premium_close_bps` 与该样本对应，`premium_mean_bps` 是分钟内均值。记录器定义见项目 `entropy_arb/recorder.py`。

公式（未扣费）：

```text
premium = (Entropy mid / hedge mid - 1) * 10000
sell edge = (Entropy bid / hedge ask - 1) * 10000
buy edge  = (hedge bid / Entropy ask - 1) * 10000
```

SELL 表示卖 Entropy、买对冲腿；BUY 表示买 Entropy、卖对冲腿。

## 数据检查与时间窗口

固定一次分析的截止时间 `as_of`，记录其时区；用户未指定时，选最后一条完整可用记录并说明。跨品种比较默认选各候选均有数据的共同时间窗口，披露各自缺测情况，不填充缺失盘口。

每份输入至少记录：文件路径和哈希、原始／有效行数、低样本行、非有限／非正价格、倒挂盘口、重复和乱序、超过 3 分钟的断档数量及最长断档。有效分钟通常沿用工具默认 `samples >= 10`，调整时说明。

发现重复或乱序时记录冲突。需要回放时在独立工作目录生成去重、排序副本，明确选择规则并保存副本哈希；价格冲突无法合理处理则暂停该组回放。项目加载器要求严格递增时间，不能默默改写原文件以通过加载。

同时计算时间跨度（首末有效分钟间的日历时长）、有效采样时长（去重有效分钟数除以 60）、覆盖率（有效分钟数除以窗口内应有分钟数）。长时间无数据不能计作连续采样证明。

最后时间落后只能说明数据未更新；没有进程／日志证据，不把原因直接归为采集器反复死亡。CSV 未记录逐腿报价年龄时，不能仅凭 `samples` 或价格不变证明盘口新鲜或陈旧。

全量、近 48 小时、近 6 小时均锚定同一 `as_of`。比较中枢、上下轨、方向偏斜、有效分钟与覆盖率；窗口不足时标记。漂移超过候选带宽、跨越零点或出现明显状态切换时重点说明，不用固定 5 bps 作为唯一判据。

`tools/analyze.py --hours N` 使用运行时钟；离线／历史报告先筛出 `[as_of-N小时, as_of]` 的副本，再不带 `--hours` 运行。全量也必须截到同一 `as_of`。

```bash
.venv/bin/python tools/analyze.py --csv <固定窗口副本.csv> --fees-bps <F>
```

该工具使用分钟末溢价估中枢，使用分钟内最大可见 edge 估候选带宽和触发分钟。候选上／下轨来自同一样本的分位数，均是样本内描述。每日频率以首末跨度归一，包含断档；报告明确分母，勿将“触发分钟／日”写成交易次数或完成往返数。

## 手续费与其他成本

分别记录 Entropy、对冲腿的每笔费率 `f_E`、`f_H`（bps）、来源、证据日期和状态：已核验／配置假设／`UNKNOWN`。同一交易所的账户层级、模式或返佣可能不同，不把别人的费率当成本账户费率。

传给 `--fees-bps` 的是**一次双腿操作**的合计费率 `F = f_E + f_H`，建仓和平仓各支付一次。等名义近似下往返费用约 `2F`；精确回放按四笔实际模拟成交名义分别计费。工具输出里“round-trip taker fees”的措辞不能改变这个参数语义。

历史配置曾采用 Entropy Growth Mode `0.9`、Lighter `0`、trade.xyz 假设 `1.0` bps；这只是待本次核验的条件，不能固化为当前事实。若比较 Entropy `9` bps 的情景，分别与各对冲腿费率相加并重新计算信号和收益。

盘口买卖价已含点差，不重复扣一份点差；另列不利滑点、净资金费、RH 的 USDG/USDC 兑换或币种基差。未知成本不能记作已发生的零成本；允许展示“未含该项”的条件结果，并说明盈亏平衡成本空间。
