# SPY maker–RH hedge：费用、返佣与积分证据

核查：2026-11-07（Asia/Taipei）。仅研究公开来源，不访问账户、不交易。用户允许有限现金损失换激励；预算金额、周期、阈值及积分估值尚未决定。本资产不替用户选择。

## 结论与平台映射

当前官方域名、文档和公开API共同指向 **Arcus**：支持Stock Tokens、加密资产和永续的自托管协议；本策略对象是其 **SPY-USD perpetual（marketId=23）**，不是现货。当前官网身份与产品由[官网](https://www.arcus.xyz)、[官方积分公告](https://www.arcus.xyz/blog/introducing-arcus-points)、[perp概览](https://docs.arcus.xyz/concepts/perpetuals/overview)和[实时市场费表](https://api.arcus.xyz/v1/markets/feeSchedules)交叉确认。没有核实到旧Entropy规则向Arcus逐项迁移的官方映射，故不继承旧Entropy费用/积分承诺。

RH是独立Lighter实例；[Robinhood官方](https://docs.robinhood.com/chain/lighter-domains/)明确其执行、排序、流动性独立，API为`https://api.rh.lighter.xyz`。不得套Core费用、LIT质押或Core激励规则。

## 已核实费用与资格

### Arcus SPY专属费率

来源：[费用模型](https://docs.arcus.xyz/concepts/perpetuals/fees)、[市场费表实时API](https://api.arcus.xyz/v1/markets/feeSchedules)、[全局档位实时API](https://api.arcus.xyz/v1/feetiers)、[档位单位说明](https://docs.arcus.xyz/api-reference/public/get-fee-tier-table)。访问日期均2026-11-07。

| 档位 | 30日已成交名义量门槛USD | SPY maker bps | SPY taker bps |
| --- | ---: | ---: | ---: |
| Base | 0 | 0 | 2.25 |
| Bronze | 2,500,000 | 0 | 1.90 |
| Silver | 10,000,000 | 0 | 1.60 |
| Gold | 50,000,000 | 0 | 1.35 |
| Platinum | 200,000,000 | 0 | 1.15 |
| VIP | 500,000,000 | −0.20 | 1.00 |
| Max | 1,500,000,000 | −0.30 | 0.95 |

证据：SPY的`hasCustomSchedule=true`；API费率单位ppm，`100 ppm=1 bp`。`volume_threshold`单位USD×1e9。全局基础档maker150/taker450ppm不能替换SPY专属0/225ppm。成交手续费=`成交名义量×ppm/1e6`。表为核查时点快照，文档明确费表可无需版本发布而变化。

同钱包子账户共享滚动30日已成交量与档位；升档周期计算，并非跨门槛的该笔立即生效；旧成交滚出后也可降档。实际等级及折扣需后续授权的账户只读证据（`account/stats?include=feeTier`），本轮 **UNKNOWN**，不能预订VIP返佣。

负maker费是**逐笔贷记**，且同笔maker rebate上限为该笔taker实收手续费。返佣不能仅按负费率乘量忽略上限。邀请注册可对正maker/taker手续费打95折，零费和负maker返佣不受影响。不能将折扣误记成额外收入。

### Arcus referral commission与结算

来源：[费用模型](https://docs.arcus.xyz/concepts/perpetuals/fees)、[实时commissionrates](https://api.arcus.xyz/v1/commissionrates)、[commission说明](https://docs.arcus.xyz/api-reference/public/get-referral-commission-rate-schedule)、[claim说明](https://docs.arcus.xyz/api-reference/referral/claim-accrued-commission)。访问2026-11-07。

佣金以受邀者的**交易手续费**为基数，不是名义成交量。实时表T1 Base–Platinum=1000bps（10%）、VIP/Max=1500bps（15%），T2=300bps（3%）、T3=200bps（2%）；文档规定有效T1=`max(t1_rate_bps−referee_discount_bps_at_binding,0)`。受邀人折扣在绑定时锁定，不可拿表面比例推个人佣金。

佣金有accrued余额、claim提交和claim历史；服务器以pending balance/cutoff计算确定性transferId以保证重试幂等。**accrued、claim请求成功、实际到账是不同状态**。未见足够依据承诺固定到账时延、个别账户可领取额度或到账资格，均UNKNOWN。此机制不是本钱包自身maker负费；不得把它与同笔手续费的负数再加一遍。

### Lighter RH现行账户费用

来源：[RH官方overview原文](https://docs.lighter.xyz/developers/robinhood-chain/overview.md)，访问2026-11-07。

| RH账户 | maker / taker bps | taker / maker / cancel延迟 |
| --- | --- | --- |
| Standard（默认） | 0 / 0 | 300 / 200 / 200 ms |
| Plus | 1.5 / 1.5 | 300 / 200 / 200 ms |
| Premium，14日量<$1M | 1.2 / 3.5 | 200 / 0 / 0 ms |
| Premium，14日量>$500M | 0.84 / 2.45 | 150 / 0 / 0 ms |

Premium中间档位依14日量降费；不依LIT质押。默认Standard是公开默认值，不证明用户账户当前等级。账户实际等级、市场例外及逐笔实收仍须只读核验。降档有24小时冷却与子账户数量条件，不能假定即时切换。

**来源冲突保留：** Context7检索到的官方旧索引（`apidocs.lighter.xyz/docs/lighter-rh`）Plus为0.005%/0.005%；本次直接官方overview正文为0.015%/0.015%。本表采用直接当前正文，旧索引不作为运行时费用依据。Standard两来源均0/0。

## 资金费与其他现金成本

来源：[Arcus funding](https://docs.arcus.xyz/concepts/perpetuals/funding)、[Lighter funding](https://docs.lighter.xyz/trading/funding.md)，访问2026-11-07。

Arcus funding按小时收付；RWA盘内受实时premium影响，盘外改用每小时更新的SOFR+0.5%年化，不是盘外零资金费。资金费是交易者间转移，与交易手续费分开。Arcus实时positions的cumulativeFunding为正表示收入，负表示支出，并有逐笔funding记录。对冲两端资金费不可假定抵消。

Lighter通用funding文档描述整点结算及逐市场参数；本轮未读账户或RH SPY实时市场参数，因此 **RH该市场实际费率、具体计提/结算适用性UNKNOWN**，不把通用默认利率直接当RH SPY现金成本。

Arcus文档称平台自身入出金零费，第三方兑换/跨链成本另计。策略还需记录真实执行滑点、紧急对冲、链上gas/桥接、可能借贷利息与强平费用；没有真实路径、持仓和流水，不给个体全成本数值。

## 积分：计分方式、时段、资格与估值边界

### Arcus

来源：[Introducing Arcus Points官方公告（2026-10-01；现行正文）](https://www.arcus.xyz/blog/introducing-arcus-points)，访问2026-11-07。

- S0覆盖7月1日至9月30日，积分总数仍暂不展示；S1已开始，每周固定250K points，周三15:00 **ET**发放，个人及周总量见dashboard。计划最迟2027上半年末结束；不是永续发行承诺。
- 计分考虑交易方式等多因素，可调整；**不只成交量**。做市明确奖励紧报价、深度、持续性；留存抵押和邀请也参与。具体权重、队列排名、SPY单位成交量产分率、未成交挂单各自贡献均未公开，不能由成交量线性外推。
- 当前RWA活动加成；RWA perpetual盘外加成窗口：美东交易日20:00–次日04:00，加周末和有报价的美股假日。公告的正常时段包含盘前盘后04:00–20:00。采用ET并自动跟随夏令时，不能全年固定EST/台北时差。加成不等于其他时段不计分；倍数未公开，UNKNOWN。
- Robinhood Wallet的Arcus执行**现货swap**加成只在spot积分内，不把它套到SPY perp或Lighter RH。
- 公告列明wash trading、self-matching、deliberate clustering、反复存入/交易/提出的rapid churning及其他识别为gaming的活动可能减分或无分；可因欺诈/违反条款slash，扣分重分给他人。这是计分风险事实，不推定真实跨平台风险对冲自动违规，也不假设刷量有效。
- 公告明确积分只是参与度指标、分配由Arcus裁量；[Protocol Terms Annex C](https://arcus.xyz/legal/protocol-terms)被其引用，本轮未逐条核实该法律附录，不扩展其结论。公告写明不向美国、加拿大、英国等受限地区开放；用户地区、账户活动资格UNKNOWN，无需本票替用户认证。

### Lighter RH

来源：[Points API分类](https://docs.lighter.xyz/api/points.md)、[Referral API分类](https://docs.lighter.xyz/api/referral.md)、[API实例说明](https://apidocs.lighter.xyz/docs/get-started)，访问2026-11-07。

官方证实live points、leaderboard及referral-points端点为RH专属；仅有接口存在**不能证明**当前SPY成交可计分、权重、结算周期或活动持续。已查页面未给足RH具体活动发放、排除或现金兑付规则，因此RH积分活动当前可用性与用户资格、单位成交量收益、返佣比例/领取条件均UNKNOWN；不能挪用Core规则补空。

**两个平台积分的现金价值、兑付权、代币映射、兑现日期和个人最终分配均UNKNOWN**。不是默认0，也不是确定收益；报表可展示积分数量及UNKNOWN现金值，现金预算单独约束。

## 规格建议：成本口径与避免双记

以下是建模建议，不是交易阈值或预算决定。

一次正常往返为四次真实成交：Arcus开仓maker、RH开仓IOC/taker、Arcus平仓maker、RH平仓IOC/taker；部分成交需按每个fill加总。正常交易费：

`C_fee = Σ(N_A_open/close × f_A_maker) + Σ(N_RH_open/close × f_RH_taker)`。

基础SPY+RH Standard的公开表仅支持“这四笔表面交易费可为0”，不代表现金损失为0。maker是否成立以fill角色为准；RH IOC只是执行约束，未成交量无成交费但会产生裸露风险。紧急taker按真实平台、方向、数量和当时费档替换相应费率：Arcus Base SPY紧急taker是2.25bps/单边，RH Standard仍表面0，但滑点、资金费与余额风险照计。不得把四笔全用同一名义量，或将双边成交额误当净仓位。

- **交易现金账**：成交价现金流/已实现PnL、正手续费、资金费与其他到账成本；负maker费作为负手续费，若已包含在exchange净PnL不得再次相加。若PnL由真实成交价算出，执行滑点只作归因，不再次扣损。
- **已到账affiliate现金账**：用平台+claim/transferId去重，关联commission来源；转账到账只确认一次。此前已按应计确认的佣金，到账只搬状态，不能再计一次收入。
- **预期返佣账**：accrued/未领取/处理中/争议状态、资格及证据独立列；在现金预算上不抵亏损，不把预计maker rebate与已贷记负手续费叠加。
- **积分账**：平台、season、distribution ID/时间、pending/发放/扣回数量、可归因活动；不能与现金或未结佣金合并。现金估值字段保留UNKNOWN，不用0制造虚假精确。

预算后续需要独立查看交易现金损失、到账激励和积分数量；已到账激励是否允许补充亏损额度、预算按毛损失还是净现金损失计算，由用户后续决定。保证预算执行不依赖积分未来价格，且不因预期返佣放大允许损失。

## 后续预算决策前所需证据

1. 用户定义金额、币种、周期、重置时点、毛/净现金口径，以及到账激励是否回补额度；本票不预设。
2. 经单独授权的只读等级/折扣/活动资格证据；交易前实时SPY费表和RH等级/市场配置快照。无账户信息不报个人返佣或成本。
3. 四次成交关联ID、成交角色/名义量/实收fee、对冲未成交与紧急taker记录；跨平台资金费、充值/兑换/借贷/提币实际成本。
4. maker rebate同笔上限及实际贷记，affiliate accrued→claim→到账对应关系；勿以API静态示例替代实值。
5. Arcus/RH实际weekly distribution与扣回历史、当期boost/排除规则；在没有这些证据前，不承诺每美元损失可换多少积分。

## 阶段交接

目标是核实SPY跨平台做市对冲的费用、现金返佣与积分边界，供后续预算和实现票使用。本阶段只产出本研究文件，未读账户或凭据，未交易。官方公开API已确认Arcus SPY自定义费表、30日档位及佣金表；直接RH正文确认Standard零费和300ms对冲延迟，并发现Plus费率与索引缓存不一致。已核对Arcus积分按报价质量等多因素计分、盘外加成和减分条件；RH计分细则、账户实际资格及积分现金价值保留UNKNOWN。验证为官方页面/API现查、单位换算及正常四成交/紧急成本分账检查；待后续用户决定预算金额周期并补授权只读证据。本资产及下列来源构成可复核交接，运行时仍须刷新费用和活动规则。
