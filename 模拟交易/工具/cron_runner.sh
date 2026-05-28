#!/bin/bash
# cron_runner.sh — 模拟交易每日自动执行入口
# 由 crontab 调用: 45 9 * * 1-5 /bin/bash ~/ccrt/模拟交易/工具/cron_runner.sh

ROOT="$HOME/ccrt"
LOG_DIR="$ROOT/模拟交易/日志"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/cron_${DATE}.log"

echo "===== Cron Runner $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG_FILE"
cd "$ROOT" || exit 1

# Run orchestrator (covers both Key Stock + Daily Pick tracks)
python3 模拟交易/sim_orchestrator.py --date "$DATE" >> "$LOG_FILE" 2>&1

echo "Exit: $?" >> "$LOG_FILE"
