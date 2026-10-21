# SNDK 实盘上线清单（GO-LIVE CHECKLIST）

- 制定：2026-10-20（EWY/lighter 版）；2026-10-22 改写为 SNDK 版（EWY 版见本文件 git 历史）
- 改写原因：2026-10-21 23:56 截止的回放中，EWY 两组扣成本后约为零（每腿 2bps 滑点时 EWY/L ≈ $0.01、EWY/xyz −$1.08），SNDK 两组领先（证据：`.scratch/daily-analysis/2026-10-21/run-2358/`）
- 范围：把 SNDK 的一条对冲线从只读采集切换为小仓位实盘试单。对冲腿在第 1 节的门槛通过后二选一：**tradexyz（建议首选）** 或 lighter-rh
- 实盘配置 `live/config-sndk-<hedge>.yaml` 只留本地（`live/` 被 .gitignore 忽略，目前尚未创建）
- 红线：第 1 节全部通过、其余各节做完之前，不启动任何非 `--record-only` 进程

## 0. 现状快照（2026-10-22 00:41）

- 单进程只读采集 `tools/collect.py --list record/hedge-markets.json` 在跑（11 组，每组一把配对锁）；`tools/watchdog.sh` 的项目路径仍是旧目录且未挂 cron，**当前没有自动保活**
- 前向回放已冻结参数：`logs/forward/20261022-0050/`（拟合区间为此前 48h，费率按本账户实测 0.864bps：基础 4.5bps、推荐返佣 4%；`20261022-0041` 按默认档 0.8bps 冻结，已作废）；每日 09:00 由 systemd 用户定时器 `entropy-forward-replay.timer` 自动运行 `tools/forward_replay.py run`（日志：`journalctl --user -u entropy-forward-replay`）
- `.env`（权限 600）：`HL_PRIVATE_KEY`、`HL_ACCOUNT_ADDRESS` 已填（是否为 agent 钱包私钥待确认）；Lighter RH 已填并于 2026-10-22 核验：账户编号与钱包见 `.env`（与 HL 不是同一钱包）、API key index 4 与链上公钥一致、`accountLimits` 为 standard（taker/maker 0）。lighter SDK 已装入 `.venv`
- 未提交：`tools/venue_costs.py`、`tools/forward_replay.py`（以及采集相关的未跟踪文件）

## 1. 上线门槛（任一不过 → 不上线）

- [ ] **1.1 前向回放 ≥ 3 天**：看 `logs/forward/20261022-0050/history.csv`（每次运行、每组、每个情景一行）中所选对冲线**最新一行**：`hours` ≥ 72（按该组自己的最后有效分钟计；报告里标 stale 的组说明采集已停，不算天数）；`scenario=slip1` 与 `scenario=slip2` 的 `net_after_funding_usd`（清算估值+资金费）都为正；`flat_returns` ≥ 1（否则只是浮盈）；`funding_in_gaps_usd` 不是收益的主要来源。期间不得重新冻结参数再挑结果
- [ ] **1.2 实际费率**：`python3 tools/venue_costs.py fees --hl-address <主账户地址>` 得到 io:SNDK taker ≈ 0.864bps（2026-10-22 查得；Growth Mode 生效）；对冲腿 xyz:SNDK 同样核对。若选 lighter-rh，在 Lighter RH 前端或 `accountLimits` 确认账户为 Standard（0/0）。费率与冻结时的假设不同 → 用实际费率重新冻结，前向回放重新计时
- [ ] **1.3 资金费稳健性**：1.1 的合计已含回放期间的实际资金费，此处不再重复扣减，只检查两件事：(a) 同一行 `liquidation_usd`（不含资金费）也为正，即利润不是靠资金费撑起来的；(b) `python3 tools/venue_costs.py funding --symbol SNDK --hedge <hedge> --start <近7天>` 的两腿资金费差方向与回放期间一致，没有反转成对持仓方向不利。参考：10/17 起均值，持有空 Entropy/多对冲每天约付 0.9bps（RH）/1.8bps（xyz）
- [ ] **1.4 秒级持续性（建议）**：分钟数据无法证明价差能持续超过下单延迟（Lighter Standard taker 300ms）。选 lighter-rh 时此项必做；选 tradexyz 时至少用 `tools/snapshot_spread.py` 抽查触发时刻
- [ ] **1.5 兑换成本（仅 lighter-rh）**：RH 链保证金为 USDG，确认 USDC↔USDG 兑换与跨链成本，并计入 1.1 的结果

**对冲腿选择**：历史回放两者接近（含资金费：RH +$9.27、xyz +$9.06，单腿上限 $1000、1bps 滑点）。建议首选 **tradexyz**：与 Entropy 同属 Hyperliquid，可共用一个账户与 USDC，没有跨链兑换，没有 Lighter 的 300ms taker 延迟。代价是对冲腿多付约 0.8bps/边，下单步长为 0.001（RH 为 0.0001）。若 1.1 中 RH 明显更优且 1.4、1.5 通过，再选 RH。

## 2. 代码与配置

- [ ] **2.1 只读 ws 端点（仅 lighter-rh）**：`entropy_arb/config.py` 中 Lighter 主网与 RH 的 ws URL 带 `?readonly=true`，实盘需换回认证端点（该文件注释已说明）。tradexyz 走 HL，不涉及此项
- [x] **2.2 engine.py `trust_env`**：保留（2026-10-20 Jerel 决定）
- [x] **2.3 `.gitignore`**：`live/` 已忽略
- [ ] **2.4 生成实盘配置**：以 `logs/forward/<freeze>/SNDK-<hedge>.yaml` 为底本复制到 `live/config-sndk-<hedge>.yaml`，改为：两边 `max_position_usd: 200`、`max_order_notional_usd: 100`；`taker_fee_bps` 填 1.2 核实值；`inventory.scale_bps` 保持 10
- [ ] **2.5 步长与最小单**：确认引擎按各场所实际步长下单（io:SNDK 0.0001、xyz:SNDK 0.001、RH 0.0001 且最小 0.01），HL 最小名义 $10；`net_tolerance_base` 不小于两腿中较粗的步长（xyz 为 0.001）
- [ ] **2.6 全量测试**：`for f in tests/test_*.py; do .venv/bin/python $f || echo FAIL $f; done` 全部通过（venv 未装 pytest）

## 3. 凭据（.env）

- [ ] `HL_ACCOUNT_ADDRESS`：主账户地址（Entropy=io dex；选 tradexyz 时 xyz 默认共用该账户）
- [ ] `HL_PRIVATE_KEY`：确认是 **API/agent 钱包**私钥（只能交易、不能提现），不是主钱包私钥
- [ ] 选 lighter-rh 时：`LIGHTER_ACCOUNT_INDEX`、`LIGHTER_API_KEY_INDEX`、`LIGHTER_API_PRIVATE_KEY` 使用 **RH 链**账户与专用 API key（主网与 RH 是两套账户）
- [ ] `.env` 权限 600；永不提交；密钥不经聊天传递

## 4. 资金与保证金

- [ ] io:SNDK 只能逐仓（最高 15x），xyz:SNDK 最高 10x：两腿杠杆都设 **≤ 3x**，即每腿 $200 仓位至少放 ~$70 保证金，再加缓冲；建议每个账户/腿 ≥ $300
- [ ] 选 tradexyz：同一 HL 账户内 io 与 xyz 两个 dex 的保证金分别充足（逐仓按币种独立）
- [ ] 选 lighter-rh：RH 账户 USDG ≥ $300
- [ ] 估算单边强平价：SNDK 单日 ±10% 时两腿都不会被强平

## 5. 故障演练（实盘前，用最小单量）

- [ ] **单腿失败**：人为让一条腿无法成交（例如极小额度时撤掉对冲腿保证金），确认引擎的净敞口对冲（`_hedge`）在 `net_tolerance_base` 外会补单，或在 `max_consecutive_errors` 后 HALT
- [ ] **带仓重启**：有持仓时停机再启动，确认启动时严格对账（`_reconcile_positions(strict=True)`）读到正确仓位
- [ ] **断线**：断网几十秒，确认盘口 STALE 时不下新单，恢复后正常
- [ ] **HALT 后手动平仓**：演练一次在两个场所界面上对齐并平掉残余仓位（停机不会自动平仓）

## 6. 进程切换与启动

- [ ] 采集器与实盘引擎会争用同一配对锁与 CSV：在 `record/hedge-markets.json` 把所选 SNDK 配对设为 `collection_enabled: false`，SIGTERM 停掉 `tools/collect.py`，等下一分钟再按 README 重启（其余 10 组继续采集）
- [ ] 在项目根目录启动：`.venv/bin/python main.py --symbol SNDK --hedge <hedge> --config live/config-sndk-<hedge>.yaml`
- [ ] 日志在写、两边盘口新鲜（无 STALE），交易 CSV 已创建
- [ ] 告警：至少把 HALT / 连续断线接到能推送到手机的通道（当前只写日志）

## 7. 首笔成交验单（最关键）

第一笔往返出现后立刻核对，任一不对立即停机：

- [ ] **实际扣费**：用 `userFills`（HL）逐笔 `fee` ÷ 名义，Entropy 腿 ≈ 1.2 核实值；若接近 9bps，说明 Growth Mode 已失效，策略前提不存在，停机
- [ ] **双腿对齐**：两腿都成交、数量一致，净敞口在容差内
- [ ] **成交价差**：入场 premium 达到 midline ± 带宽（不是误触发）；实际成交价相对信号的滑点记录下来，与回放的 1bps 假设比较

## 8. 运行守则（试单期）

- 每天看 `logs/forward/.../history.csv` 与实盘交易 CSV：实盘已实现盈亏应与同期前向回放同号、量级相近；持续偏差说明执行模型过于乐观
- 中枢 24h 漂移超过当前带宽的一半 → 停下来重新冻结参数（新冻结后前向回放重新计时）
- 美股休市、开盘前后、SNDK 财报日：两场所价格来源可能失步，暂停开新仓或把 `max_position_usd` 降半
- 试单满 48h、验单全过、已实现（扣资金费）为正 → 仓位上限升到 $500/腿，单笔 $250；再满 48h 升到 $1000/$500

## 9. 停机线（任一触发，立即停）

- 实际扣费偏离 1.2 核实值（Growth Mode 退出）
- **单日亏损**（已实现 + 按中价估值，含资金费）超过 $10（试单期）
- 中枢 24h 漂移 > 当前带宽
- 引擎 HALT（`max_consecutive_errors: 3`），先查因再重启
- 任一场所 ws 长断或 STALE 反复出现
- 净敞口长时间压不回容差内
- 任一腿保证金率接近强平

停机方法：kill 实盘进程即停新单；**停机不会自动平仓**，停后立即核对两边仓位，残余仓位在交易所界面手动对齐或平掉，记录到当日日志。

## 10. 回滚

- 代码：`git checkout -- entropy_arb/config.py`（若改过 2.1）
- 采集：把 SNDK 配对恢复 `collection_enabled: true`，重启 `tools/collect.py`
- 凭据：删除 `.env` 中实盘项，并在 HL（API 钱包）/ Lighter 侧吊销 key
