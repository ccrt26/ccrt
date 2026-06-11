#!/bin/bash
# install_crontab.sh — 调度系统crontab安装脚本
# 使用: bash 代码文件/tools/install_crontab.sh          # dry-run（默认）
#        bash 代码文件/tools/install_crontab.sh --dry-run  # dry-run（显式）
#        bash 代码文件/tools/install_crontab.sh --install  # 真实安装（需用户确认后执行）
#
# 安全机制:
#   - 默认 DRY_RUN=true，不带参数只做 dry-run
#   - --install 才执行真实安装，且提示已获得用户确认
#   - 自动备份当前crontab
#   - 自动清理旧铁律数据链条目，防止新旧叠加

set -euo pipefail

ROOT="$HOME/ccrt"
PYTHON="/usr/bin/python3"
BACKUP_DIR="$ROOT/临时报告"
DRY_RUN=true

# 参数解析：默认 dry-run；--install 为真实安装
if [ "${1:-}" = "--install" ]; then
    DRY_RUN=false
    echo "=== 真实安装模式 ==="
    echo "  请确认已获得用户授权"
    echo ""
elif [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE — 仅显示，不修改 ==="
    echo ""
else
    # 无参数或未知参数 → 默认 dry-run
    echo "=== DRY RUN MODE（默认） — 仅显示，不修改 ==="
    echo "  使用 --install 执行真实安装"
    echo ""
fi

# Backup current crontab
BACKUP_FILE="$BACKUP_DIR/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p "$BACKUP_DIR"

if $DRY_RUN; then
    echo "当前crontab内容:"
    crontab -l 2>/dev/null || echo "(空)"
    echo ""
else
    crontab -l 2>/dev/null > "$BACKUP_FILE" || true
    echo "已备份当前crontab到: $BACKUP_FILE"
fi

# 完整清理旧条目（全部匹配删除，防止新旧叠加）
CLEANUP_PATTERNS=(
    "铁律量化"
    "daily_orchestrator.*mode daily"
    "daily_orchestrator.*mode pigeon"
    "daily_orchestrator.*mode deep"
    "daily_workflow.*daily_latest"
    "daily_workflow.*data_only"
    "daily_workflow.*mode eval"
    "tushare_history_sync.*daily"
    "run_daily_data_retry_once"
    "Invoke-DailyReportParser"
    "run_daily_report_one_by_one"
    "build_unified_features"
    "sync_report_json"
    "backfill_returns"
    "check_data_quality"
    "check_freshness_alerts"
    "git_autosweep"
    "scheduler_health_check"
    "cron_runner"
)

CURRENT=$(crontab -l 2>/dev/null || true)
CLEANED="$CURRENT"
for pattern in "${CLEANUP_PATTERNS[@]}"; do
    CLEANED=$(echo "$CLEANED" | grep -v -E "$pattern" || true)
done

# 删除所有旧注释行（保留有效的非注释指令即可）
# 注释仅由新 ENTRIES 提供，确保预览干净无旧描述残留
CLEANED=$(echo "$CLEANED" | grep -v -E '^#' || true)

# 删除连续空行（压缩为单空行）
CLEANED=$(echo "$CLEANED" | cat -s)

# 删除首尾空行
CLEANED=$(echo "$CLEANED" | sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba')

# 推荐的新数据链 crontab 条目（仅有一套，无日报生成/parser/逐票任务）
ENTRIES=(
    "# === 铁律量化调度系统 (installed $(date +%Y-%m-%d)) ==="
    "# git自动清扫"
    "7 * * * * $PYTHON $ROOT/代码文件/tools/git_autosweep.py"
    ""
    "# 信鸽采集 (交易日19:00)"
    "7 19 * * 1-5 $PYTHON $ROOT/代码文件/tools/daily_orchestrator.py --mode pigeon"
    ""
    "# 数据链 (交易日): 15:55日频同步 → 16:05加工归档 → 16:12健康检查 → 16:15signal"
    "55 15 * * 1-5 $PYTHON $ROOT/代码文件/tools/tushare_history_sync.py --daily"
    "5 16 * * 1-5 $PYTHON $ROOT/代码文件/每日荐股/scripts/daily_workflow.py --mode data_only"
    "12 16 * * 1-5 $PYTHON $ROOT/scripts/check_daily_data_chain_health.py --date \$(date +\%Y\%m\%d)"
    "15 16 * * 1-5 $PYTHON $ROOT/代码文件/tools/daily_orchestrator.py --mode daily"
    ""
    "# 深度分析 (周五20:30)"
    "30 20 * * 5 $PYTHON $ROOT/代码文件/tools/daily_orchestrator.py --mode deep"
    ""
    "# 模拟交易引擎 (交易日9:45)"
    "45 9 * * 1-5 /bin/bash $ROOT/模拟交易/工具/cron_runner.sh"
    ""
    "# 后评估 (交易日17:20)"
    "20 17 * * 1-5 $PYTHON $ROOT/代码文件/每日荐股/scripts/daily_workflow.py --mode eval"
    ""
    "# 心跳监控 (每30分钟)"
    "3,33 * * * * $PYTHON $ROOT/代码文件/tools/scheduler_health_check.py"
    ""
    "# === 结束 ==="
)

if $DRY_RUN; then
    echo ""
    echo "=== 将要清理的旧条目 ==="
    found_any=false
    for pattern in "${CLEANUP_PATTERNS[@]}"; do
        matches=$(echo "$CURRENT" | grep -E "$pattern" || true)
        if [ -n "$matches" ]; then
            found_any=true
            echo "  [删除: $pattern]"
            echo "$matches" | sed 's/^/    /'
        fi
    done
    if ! $found_any; then
        echo "  (无匹配)"
    fi
    echo ""
    echo "=== 安装后的最终 crontab 预览 ==="
    echo ""
    if [ -n "$CLEANED" ]; then
        echo "$CLEANED"
        echo ""
    fi
    for entry in "${ENTRIES[@]}"; do
        echo "$entry"
    done
    echo ""
    echo "=== DRY RUN 完成，未修改 crontab ==="
    echo "如需安装，执行: bash $0 --install"
    echo "回滚备份: crontab $BACKUP_FILE"
else
    TMPFILE=$(mktemp)
    if [ -n "$CLEANED" ]; then
        echo "$CLEANED" > "$TMPFILE"
        echo "" >> "$TMPFILE"
    fi
    for entry in "${ENTRIES[@]}"; do
        echo "$entry" >> "$TMPFILE"
    done
    crontab "$TMPFILE"
    rm -f "$TMPFILE"
    echo ""
    echo "=== crontab 安装完成 ==="
    echo "验证: crontab -l"
    echo "回滚: crontab $BACKUP_FILE"
fi
