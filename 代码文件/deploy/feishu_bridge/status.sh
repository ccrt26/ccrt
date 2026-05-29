#!/bin/bash
# 飞书桥接 — 状态检查

echo "=== 飞书桥接状态 ==="
echo ""

echo "【launchd 服务】"
for svc in com.tielv.caffeinate com.tielv.feishu-bridge com.tielv.im-consumer; do
    if launchctl list | grep -q "$svc"; then
        pid=$(launchctl list | grep "$svc" | awk '{print $1}')
        echo "  🟢 $svc (PID: ${pid:--})"
    else
        echo "  🔴 $svc (未运行)"
    fi
done

echo ""
echo "【凭证】"
if [ -f "$HOME/.feishu_bot_tmp.json" ]; then
    perm=$(stat -f "%Lp" "$HOME/.feishu_bot_tmp.json" 2>/dev/null || stat -c "%a" "$HOME/.feishu_bot_tmp.json" 2>/dev/null)
    echo "  🟢 ~/.feishu_bot_tmp.json (权限: $perm)"
else
    echo "  🔴 ~/.feishu_bot_tmp.json 不存在"
fi

echo ""
echo "【队列目录】"
QUEUE_DIR="/Users/ccrt/ccrt/.claude/im_queue"
if [ -d "$QUEUE_DIR" ]; then
    for f in pending.json done.json processed_ids.json; do
        if [ -f "$QUEUE_DIR/$f" ]; then
            size=$(wc -c < "$QUEUE_DIR/$f" | tr -d ' ')
            echo "  📄 $f ($size bytes)"
        fi
    done
else
    echo "  🔴 队列目录不存在"
fi

echo ""
echo "【最新日志】(bridge)"
BRIDGE_LOG="/Users/ccrt/ccrt/临时报告/对话日志/feishu_bridge_$(date +%Y-%m-%d).log"
if [ -f "$BRIDGE_LOG" ]; then
    tail -3 "$BRIDGE_LOG" | sed 's/^/  /'
else
    echo "  无今日日志"
fi
