#!/usr/bin/env bash
# entropy-arb watchdog — 每 15 分钟由 cron 调用，检查只读采集进程，死的拉起。
#
# 保活的 (symbol, hedge) 对：
#   SNDK/lighter-rh  EWY/lighter  NBIS/lighter          (Lighter 系)
#   DRAM/tradexyz    EWY/tradexyz NBIS/tradexyz SNDK/tradexyz  (xyz)
# 注意 H100 已于 2026-10-17 从 Entropy(io) 下架，不再保活。
#
# 同一 symbol 跑在两个 hedge venue 上是刻意的（多组价差对），CSV 路径已按
# venue 区分（logs/minutes-<sym>-<venue>.csv），不会互写。
set -euo pipefail

PROJ="$HOME/workspace/projects/entropy-arb"
LOG_DIR="$PROJ/logs"
WATCH_LOG="$LOG_DIR/watchdog.log"

# "SYMBOL:HEDGE:CONFIG" 三元组
PAIRS=(
  "SNDK:lighter-rh:record/config-sndk.yaml"
  "EWY:lighter:record/config-ewy.yaml"
  "NBIS:lighter:record/config-nbis.yaml"
  "DRAM:tradexyz:record/config-dram-xyz.yaml"
  "EWY:tradexyz:record/config-ewy-xyz.yaml"
  "NBIS:tradexyz:record/config-nbis-xyz.yaml"
  "SNDK:tradexyz:record/config-sndk-xyz.yaml"
)

for pair in "${PAIRS[@]}"; do
  sym="${pair%%:*}"; rest="${pair#*:}"
  hedge="${rest%%:*}"; cfg="${rest#*:}"
  lower="$(echo "$sym" | tr 'A-Z' 'a-z')"
  # venue 后缀：xyz 进程的日志独立，避免和 lighter 系混写
  logsuffix="$lower"; [ "$hedge" = "tradexyz" ] && logsuffix="${lower}-xyz"
  pattern="main.py --record-only --symbol ${sym} --hedge ${hedge} "
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    continue
  fi
  (
    flock -n 9 || exit 0
    pgrep -f "$pattern" >/dev/null 2>&1 && exit 0
    cd "$PROJ"
    nohup "$PROJ/.venv/bin/python" main.py --record-only --symbol "$sym" --hedge "$hedge" \
      --config "$cfg" --no-dashboard \
      >> "$LOG_DIR/stdout-${logsuffix}.log" 2>&1 &
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: restarted ${sym}/${hedge} (pid $!)" >> "$WATCH_LOG"
  ) 9>"$LOG_DIR/.watchdog-${logsuffix}.lock"
done
