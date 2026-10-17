#!/usr/bin/env bash
# entropy-arb watchdog — 每 15 分钟由 cron 调用，检查只读采集进程，死的拉起。
#
# 保活的 (symbol, hedge) 对有两个来源（single source of truth 分工）：
#   - Lighter 系：下面 BASE_PAIRS 显式列出（venue 各不相同，无法推导）；
#   - xyz 系：扫描 record/config-*-xyz.yaml 自动推导——加一个 pair 只需
#     用 tools/gen_xyz_configs.sh 生成配置文件，无需改本脚本。
#     （H100 已于 2026-10-17 从 Entropy(io) 下架，其配置文件已删除，
#      故不会被推导；若 io 重新上架，重新生成配置即可自动恢复保活。）
#
# 同一 symbol 跑在两个 hedge venue 上是刻意的（多组价差对），CSV 路径已按
# venue 区分（见 config.py 的 venue-aware 默认），不会互写。
set -euo pipefail

PROJ="$HOME/workspace/projects/entropy-arb"
LOG_DIR="$PROJ/logs"
WATCH_LOG="$LOG_DIR/watchdog.log"

# venue -> 日志/锁文件后缀（默认空，即 lighter 系沿用旧文件名）
declare -A VENUE_SUFFIX=( [tradexyz]="-xyz" )

# "SYMBOL HEDGE CONFIG"（空格分隔，避免冒号拼接解析）
BASE_PAIRS=(
  "SNDK lighter-rh record/config-sndk.yaml"
  "EWY lighter record/config-ewy.yaml"
  "NBIS lighter record/config-nbis.yaml"
)

PAIRS=( "${BASE_PAIRS[@]}" )
for cfg in "$PROJ"/record/config-*-xyz.yaml; do
  [ -e "$cfg" ] || continue
  base="$(basename "$cfg" .yaml)"                       # config-dram-xyz
  sym="$(echo "${base#config-}" | sed 's/-xyz$//' | tr '[:lower:]' '[:upper:]')"
  PAIRS+=( "$sym tradexyz record/${base}.yaml" )
done

for pair in "${PAIRS[@]}"; do
  read -r sym hedge cfg <<< "$pair"
  lower="$(echo "$sym" | tr 'A-Z' 'a-z')"
  suffix="${VENUE_SUFFIX[$hedge]:-}"
  logsuffix="${lower}${suffix}"
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
