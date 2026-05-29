#!/bin/bash
# 飞书桥接 — 统一部署脚本
# 用法: bash deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"

echo "=== 飞书桥接部署 ==="

# 1. 复制 plist
for plist in com.tielv.caffeinate.plist com.tielv.feishu-bridge.plist com.tielv.im-consumer.plist; do
    if [ -f "$SCRIPT_DIR/$plist" ]; then
        cp "$SCRIPT_DIR/$plist" "$LAUNCH_DIR/"
        echo "  cp $plist → $LAUNCH_DIR/"
    else
        echo "  ⚠ 缺失: $plist"
    fi
done

# 2. 先卸载旧服务（如果存在）
for svc in com.tielv.caffeinate com.tielv.feishu-bridge com.tielv.im-consumer; do
    launchctl unload "$LAUNCH_DIR/$svc.plist" 2>/dev/null && echo "  unloaded $svc" || true
done

# 3. 加载服务
for svc in com.tielv.caffeinate com.tielv.feishu-bridge com.tielv.im-consumer; do
    launchctl load "$LAUNCH_DIR/$svc.plist" && echo "  loaded $svc" || echo "  ⚠ load failed: $svc"
done

echo "=== 部署完成 ==="
bash "$SCRIPT_DIR/status.sh"
