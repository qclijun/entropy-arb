#!/usr/bin/env bash
# entropy-arb watchdog (DRAFT — 2026-10-12, 未启用)
#
# 用途：采集进程死于 VM 重建后自动拉起。设计为由 cron 每 15 分钟调用一次。
# cron 由 runtime 托管，VM 重建后依然会触发；常驻进程做不到这一点。
#
# 行为：
#   - 对 SNDK / EWY / NBIS 逐个 pgrep 检查 "main.py --record-only --symbol <SYM>"
#   - 缺失则 nohup 拉起（--record-only 只读模式，无需密钥、不下单），日志续写到 logs/stdout-<sym>.log
#   - 每次拉起记一行到 logs/watchdog.log；flock 防 cron 重叠时双重启动
#
# 前置条件（启用前必须先验证）：
#   1. Jerel 拍板"重启"；
#   2. 主聊天上下文先做一次连通性实测：worker 上下文曾出现出口代理 403，
#      若主上下文同样 403，则采集根本连不上交易所，watchdog 无意义，先修网络再说。
#
# 启用方式（主 agent，Jerel 同意重启后）：
#   chmod +x tools/watchdog.sh
#   cron.add(id="entropy-arb-watchdog", schedule={kind:interval, every:"15m"},
#            body=<下方 CRON_BODY>, owner=goal:goal_1d4007e2ef52)
set -euo pipefail

PROJ="$HOME/workspace/projects/entropy-arb"
LOG_DIR="$PROJ/logs"
WATCH_LOG="$LOG_DIR/watchdog.log"
SYMBOLS=("SNDK" "EWY" "NBIS")
# hedge venue per symbol: EWY/NBIS delisted from lighter-rh (2026-10-17), use lighter mainnet
hedge_for() {
  case "$1" in
    SNDK) echo "lighter-rh" ;;
    *)    echo "lighter" ;;
  esac
}

for sym in "${SYMBOLS[@]}"; do
  lower="$(echo "$sym" | tr 'A-Z' 'a-z')"
  if pgrep -f "main.py --record-only --symbol ${sym} " >/dev/null 2>&1; then
    continue
  fi
  (
    flock -n 9 || exit 0
    pgrep -f "main.py --record-only --symbol ${sym} " >/dev/null 2>&1 && exit 0
    cd "$PROJ"
    nohup "$PROJ/.venv/bin/python" main.py --record-only --symbol "$sym" --hedge "$(hedge_for "$sym")" \
      --config "record/config-${lower}.yaml" --no-dashboard \
      >> "$LOG_DIR/stdout-${lower}.log" 2>&1 &
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: restarted ${sym} (pid $!)" >> "$WATCH_LOG"
  ) 9>"$LOG_DIR/.watchdog-${lower}.lock"
done
