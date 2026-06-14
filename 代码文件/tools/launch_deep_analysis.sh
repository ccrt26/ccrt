#!/bin/bash
# ============================================================
# 周度深度分析启动脚本 — 每只股票独立 Claude Code 会话，并行执行
# 由 scheduled_tasks.json 周五 20:30 cron 调用
#
# 用法: bash 代码文件/tools/launch_deep_analysis.sh [YYYYMMDD]
#  不带参数默认使用当天日期
# ============================================================

set -e

ROOT="/Users/ccrt/ccrt"
CONFIG="$ROOT/代码文件/信鸽信息采集/pigeon_config.json"
DATE="${1:-$(date +%Y%m%d)}"

echo "[$(date '+%H:%M:%S')] === 周度深度分析批量启动 ==="
echo "[$(date '+%H:%M:%S')] 日期: $DATE"

# 从权威源读取股票池
if [ ! -f "$CONFIG" ]; then
    echo "[$(date '+%H:%M:%S')] FATAL: pigeon_config.json not found at $CONFIG"
    exit 1
fi

STOCKS=$(python3 -c "
import json
cfg = json.load(open('$CONFIG'))
for s in cfg['target_stocks']:
    print(f\"{s['code']}:{s['name']}\")
")

if [ -z "$STOCKS" ]; then
    echo "[$(date '+%H:%M:%S')] FATAL: empty stock pool from pigeon_config.json"
    exit 1
fi

# 逐只启动独立 Claude Code 会话（后台并行）
LAUNCHED=0
PIDS=""
while IFS=: read -r code name; do
    echo "[$(date '+%H:%M:%S')] Launching deep analysis for $code $name (date=$DATE, D07_v1.2+砺石)"
    # 每只股票独立会话，后台运行
    # 约束：D07_v1.2 强制 + 砺石 method_review + MD+HTML 默认 + 禁止 PDF + 禁止 G5/G6 冒签
    claude run "基于 $DATE 数据生成 $code $name 深度分析周报。强制: (1) D07_v1.2 必检 (多假设/反证/证据缺口/结论强度/长期机构资金); (2) 砺石 method_review 必含 (D1-D5 五项审查); (3) 默认输出 MD+HTML, 不生成 PDF; (4) 禁止冒签 G5/G6/formal pipeline PASS。输出后运行 python3 scripts/check_deep_d07_lishi_gate.py --report <MD路径> 和 python3 代码文件/深度分析/parse_deep_analysis_report.py --validate <MD路径> 验证。" \
        --cwd "$ROOT" \
        --allowedTools "Bash,Read,Write,Edit,WebFetch,WebSearch,Agent" &
    pid=$!
    PIDS="$PIDS $pid"
    LAUNCHED=$((LAUNCHED + 1))
    sleep 3  # 避免并发文件创建冲突
done <<< "$STOCKS"

echo "[$(date '+%H:%M:%S')] $LAUNCHED 个独立会话已启动，等待全部完成..."
echo "[$(date '+%H:%M:%S')] PIDs:$PIDS"

# 等待全部会话完成
FAILURES=0
for pid in $PIDS; do
    if wait $pid; then
        echo "[$(date '+%H:%M:%S')] PID $pid done (OK)"
    else
        echo "[$(date '+%H:%M:%S')] PID $pid done (FAILED)"
        FAILURES=$((FAILURES + 1))
    fi
done

echo "[$(date '+%H:%M:%S')] 全部会话完成 ($FAILURES failures)"

# 质量闸门扫描
echo "[$(date '+%H:%M:%S')] 运行质量闸门..."
python3 "$ROOT/代码文件/深度分析/parse_deep_analysis_report.py" --validate-date "$DATE"
GATE_EXIT=$?

# 门户生成（即使有 FAIL 也生成，FAIL 的由 regen 消费者处理）
echo "[$(date '+%H:%M:%S')] 生成门户..."
python3 "$ROOT/代码文件/信鸽信息采集/generate_portal.py"

if [ $GATE_EXIT -eq 0 ]; then
    echo "[$(date '+%H:%M:%S')] === 深度分析批量完成：全部 PASS ==="
else
    echo "[$(date '+%H:%M:%S')] === 深度分析批量完成：有 FAIL，regen 信号已写入 ==="
fi

exit $GATE_EXIT
