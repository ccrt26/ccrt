#!/bin/bash
# 飞书桥接 — 统一回滚脚本
# 用法: bash rollback.sh

LAUNCH_DIR="$HOME/Library/LaunchAgents"

echo "=== 飞书桥接回滚 ==="

for svc in com.tielv.caffeinate com.tielv.feishu-bridge com.tielv.im-consumer; do
    launchctl unload "$LAUNCH_DIR/$svc.plist" 2>/dev/null
    rm -f "$LAUNCH_DIR/$svc.plist"
    echo "  removed $svc"
done

echo "=== 回滚完成（飞书桥接已停用） ==="

# 可选：清理运行时文件
echo ""
echo "运行时文件（可手动删除）:"
echo "  rm -rf /Users/ccrt/ccrt/.claude/im_queue/"
echo "  rm ~/.feishu_bot_tmp.json"
