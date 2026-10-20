# EWY/lighter 实盘上线清单（GO-LIVE CHECKLIST）

- 制定：2026-10-20（待 Jerel 过目批准后执行）
- 修订：2026-10-21 按 Jerel 决定，本清单自 `live/` 移入 `docs/` 入库（公开仓库可见）；实盘配置 `live/config-ewy-lighter.yaml` 仍只留本地（`live/` 继续被 .gitignore 忽略）
- 范围：把 entropy-arb 的 EWY/lighter 从只读采集切换为小仓位实盘试单
- 配套配置：`live/config-ewy-lighter.yaml`（阈值近 48h：midline −3.1 / upper 1.5 / lower 2.0；仓位上限 $500/腿）
- 红线：本清单全部做完之前，不启动任何非 `--record-only` 进程

## 0. 现状快照（2026-10-20 晚）

- 7 个 `--record-only` 采集进程运行中（watchdog 每 15 分钟保活）
- 工作区未提交改动：`entropy_arb/engine.py`（trust_env，见 1.2）、未跟踪的 `tools/snapshot_spread.py`（与上线无关，不动）
- 无 `.env`（实盘凭据尚未配置）；`record/config-ewy.yaml` 是采集配置，不可用于实盘

## 1. 代码改造

- [ ] **1.1 撤 Lighter ws 只读端点**：`entropy_arb/config.py` 第 55、58 行附近，Lighter 主网与 Robinhood 的 ws URL 带 `?readonly=true`（只读行情）。EWY 只用主网：至少把主网那条换回认证端点；该文件上方注释本身就写明 "Authenticated live-trading sessions should revert"。改完跑全量测试（29 个）确认无回归。
- [x] **1.2 engine.py 的 trust_env 决策**：当前未提交改动给 aiohttp 会话加了 `trust_env=True`（走系统代理环境变量）。本 VM 出口依赖代理。**2026-10-20 Jerel 拍板：保留**（工作区改动不撤销，就此定稿）。
- [x] **1.3 .gitignore**：**2026-10-20 已把 `live/` 加入 `.gitignore`**（Jerel 拍板），上线文件只留本地、不进公开仓库。（2026-10-21 例外：本清单已移入 `docs/` 入库，见页首修订说明；`live/` 其余文件仍只留本地。）

## 2. 凭据（.env，项目根目录新建）

需要 5 个变量（`.env.example` 有模板）：

- [ ] `HL_ACCOUNT_ADDRESS`：Hyperliquid 账户地址（Entropy = HL 的 io dex，资金与仓位都在这个账户）
- [ ] `HL_PRIVATE_KEY`：下单签名密钥。**建议用 HL 的 API/agent 钱包私钥，不要用主钱包私钥**（agent 钱包只能交易、不能提现）
- [ ] `LIGHTER_ACCOUNT_INDEX`：Lighter 主网账户 index
- [ ] `LIGHTER_API_KEY_INDEX` + `LIGHTER_API_PRIVATE_KEY`：在 Lighter 界面/API 生成一对专用 API key（只给这个 bot 用）

纪律：`.env` 权限 600；已被 .gitignore 覆盖，永不提交；密钥不经聊天传递，走安全录入或只注入进程环境。

## 3. 资金

- [ ] HL 账户 USDC ≥ **$600**（仓位上限 $500 + 缓冲）
- [ ] Lighter 主网账户 USDC ≥ **$600**（同上）
- [ ] 确认 EWY 在两个所都可交易且盘口在线（采集数据本身就是证明，看当日 minutes-lighter-EWY.csv；注意采集进程切到 dev 代码后才写这个文件名，此前历史文件是 minutes-ewy.csv）

## 4. 配置定稿

- [ ] 启动当天用最新数据重跑：`.venv/bin/python tools/analyze.py --csv logs/minutes-lighter-EWY.csv --fees-bps 0.9 --hours 48`（采集未切 dev 代码前，文件仍是 logs/minutes-ewy.csv，用哪个名字以实际存在的为准），把 midline/upper/lower 刷进 `live/config-ewy-lighter.yaml`（中枢漂移很快：全量 −2.0 → 近 48h −3.1，隔夜就可能失效）
- [ ] 复核 `entropy.taker_fee_bps: 0.9` 未被改动

## 5. 进程切换与启动

- [ ] **先摘 watchdog**：把 EWY base 进程从 `tools/watchdog.sh` 的保活名单里去掉（否则你停掉采集进程，15 分钟内它会被自动拉回来，和实盘进程抢写同一个 CSV）
- [ ] 停掉 EWY 的 record-only 进程（其余 6 个采集进程不动）
- [ ] 在**项目根目录**启动实盘：
  `python3 main.py --symbol EWY --hedge lighter --config live/config-ewy-lighter.yaml`
- [ ] 确认日志在写：`logs/engine-ewy-live.log`（若落点不同以实际为准）、`logs/trades-ewy.csv` 已创建；dashboard 或日志里两边盘口都是新鲜的（无 STALE）

## 6. 首笔成交验单（最关键的一步）

第一笔往返出现后立刻核对，任一不对立即停机排查：

- [ ] **实际扣费**：Entropy 腿成交的实际手续费 ≈ **0.9bps**（在 HL 账户成交记录里看）。这是验证 Growth Mode 还在的唯一可靠办法；若是 9bps，策略前提不存在，停机
- [ ] **双腿对齐**：`logs/trades-ewy.csv` 里两腿都成交、数量对齐，引擎净敞口 ≈ 0（net_tolerance 0.001）
- [ ] **成交价差**：入场 premium 达到阈值（≥ midline+upper 或 ≤ midline−lower），不是误触发

## 7. 运行守则（试单期）

- 每日日报（21:44）出来后对照中枢：漂移 >5bps 就停下来刷新阈值再跑
- 每天瞄一眼两边账户余额/保证金和 `trades-ewy.csv` 的累计已实现盈亏
- 试单满 24h 且验单全过 → 把两边 `max_position_usd` 提到 1000、`max_order_notional_usd` 提到 500，再观察

## 8. 停机线（任一触发，立即停）

- 实际扣费 ≠ 0.9bps（Growth Mode 退出）
- 中枢 24h 漂移 > 5bps（阈值失效）
- 引擎连续报错（自带 `max_consecutive_errors: 3` 自动停机，触发后先查因）
- 任一所 ws 长断 / 盘口 STALE 反复出现（本 VM 上采集进程有周期性断线史，实盘期断线 = 裸敞口窗口）
- 净敞口长时间压不回 0

**停机方法与善后**：kill 实盘进程即可停新单；注意**停机不会自动平仓**——停后立刻核对两边仓位，残余仓位在两个所的界面上手动对齐/平掉，并记录到当日日志。

## 9. 回滚

- 代码：`git checkout -- entropy_arb/config.py`（+ engine.py 按 1.2 的决定）
- 进程：把 EWY 加回 watchdog 名单，采集自动恢复
- 凭据：删除 `.env` 或把 API key 在 Lighter/HL 侧吊销
