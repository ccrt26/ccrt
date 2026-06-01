#!/bin/bash
# install_crontab.sh — 调度系统crontab安装脚本
# 设计: 审计报告/架构设计/design_scheduling_separation_v1.0.md
# 使用: bash 代码文件/tools/install_crontab.sh [--dry-run]
#
# 安全机制:
#   - 操作前自动备份当前crontab到 ~/ccrt/临时报告/crontab_backup_YYYYMMDD.txt
#   - --dry-run 仅显示将要添加的条目，不实际修改
#   - 检查重复条目，避免重复安装

set -euo pipefail

ROOT="$HOME/ccrt"
PYTHON="/usr/bin/python3"
BACKUP_DIR="$ROOT/临时报告"
DRY_RUN=false

if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE — 仅显示，不修改 ==="
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

# Define new crontab entries
# Format: "cron command" (tab-separated in actual crontab)
ENTRIES=(
    "# === 铁律量化调度系统 (installed $(date +%Y-%m-%d)) ==="
    "# 每小时git自动清扫"
    "7 * * * * $PYTHON $ROOT/代码文件/tools/git_autosweep.py"
    ""
    "# 信鸽事件采集 (交易日19:00)"
    "7 19 * * 1-5 $PYTHON $ROOT/代码文件/tools/daily_orchestrator.py --mode pigeon"
    ""
    "# 日报数据就绪检查+信号 (交易日15:37)"
    "37 15 * * 1-5 $PYTHON $ROOT/代码文件/tools/daily_orchestrator.py --mode daily"
    ""
    "# 深度分析信号 (周五20:30)"
    "30 20 * * 5 $PYTHON $ROOT/代码文件/tools/daily_orchestrator.py --mode deep"
    ""
    "# 模拟交易引擎 (交易日9:45) — 保持现有"
    "45 9 * * 1-5 /bin/bash $ROOT/模拟交易/工具/cron_runner.sh"
    ""
    "# 心跳监控 (每30分钟, 在03和33分触发)"
    "3,33 * * * * $PYTHON $ROOT/代码文件/tools/scheduler_health_check.py"
    ""    ""
    "# 日报流水线 (交易日15:35 — 盘后数据采集+评分+报告+归档)"
    "35 15 * * 1-5 $PYTHON $ROOT/代码文件/每日荐股/scripts/daily_workflow.py --mode daily_latest"
    ""
    "# 后评估正式链路 (交易日17:20, 晚于backfill 20min)"
    "20 17 * * 1-5 $PYTHON $ROOT/代码文件/每日荐股/scripts/daily_workflow.py --mode eval"
    ""
    "# 统一特征层构建 (交易日15:40)"
    "40 15 * * 1-5 $PYTHON $ROOT/代码文件/tools/build_unified_features.py"
    ""
    "# 报告结构化JSON同步 (交易日16:30)"
    "30 16 * * 1-5 $PYTHON $ROOT/代码文件/tools/sync_report_json.py"
    ""
    "# 后评估收益回填 (交易日17:00)"
    "0 17 * * 1-5 $PYTHON $ROOT/代码文件/tools/backfill_returns.py"
    ""
    "# DQ-Gate数据质量检查 (交易日17:10)"
    "10 17 * * 1-5 $PYTHON $ROOT/代码文件/监督机制/check_data_quality.py"
    ""

    "# === 结束 ==="
)

# Check for existing 铁律量化 entries
CURRENT=$(crontab -l 2>/dev/null || true)
if echo "$CURRENT" | grep -q "铁律量化调度系统"; then
    echo "WARNING: 检测到已有铁律量化调度系统crontab条目"
    echo "建议手动检查并清理旧条目后重新安装"
    if ! $DRY_RUN; then
        echo "已跳过安装。使用 --force 强制覆盖，或手动编辑 crontab -e"
        exit 1
    fi
fi

if $DRY_RUN; then
    echo ""
    echo "=== 将要添加的条目 ==="
    for entry in "${ENTRIES[@]}"; do
        echo "$entry"
    done
    echo ""
    echo "=== DRY RUN 完成，未修改crontab ==="
else
    # Build new crontab: keep existing non-铁律量化 entries + add new entries
    # Remove old 铁律量化 entries first, then append new ones
    CLEANED=$(echo "$CURRENT" | grep -v "铁律量化" | grep -v "daily_orchestrator" | grep -v "scheduler_health_check" | grep -v "git_autosweep" | grep -v "cron_runner" || true)

    # Remove any trailing blank lines
    CLEANED=$(echo "$CLEANED" | sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba')

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
    echo "新增条目:"
    echo "  - git自动清扫: 每小时:07"
    echo "  - 信鸽采集:   每日19:07 (交易日)"
    echo "  - 日报信号:   每日15:37 (交易日)"
    echo "  - 深度分析:   周五20:30"
    echo "  - 模拟交易:   每日9:45 (交易日, 保持现有)"
    echo "  - 日报流水线: 每日15:35 (交易日)"
    echo "  - 统一特征层: 每日15:40 (交易日)"
    echo "  - 日报信号:   每日16:05 (交易日)"
    echo "  - JSON同步:   每日16:30 (交易日)"
    echo "  - 收益回填:   每日17:00 (交易日)"
    echo "  - DQ检查:     每日17:10 (交易日)"
    echo "  - 后评估:     每日17:20 (交易日)"
    echo "  - 心跳监控:   每30分钟"
    echo ""
    echo "验证: crontab -l"
    echo "回滚: crontab $BACKUP_FILE"
fi
