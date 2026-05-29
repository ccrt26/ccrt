# 飞书桥接 — 运维知识条目

> 类型：M类（元操作）| 关联：design_feishu_bridge_v1.1.md

## 概述

飞书群 @铁律量化助手 发指令 → launchd 每分钟触发 feishu_bridge.py → 写入 pending.json → Claude Code 执行 → 回传飞书群。

## 关键路径

| 内容 | 路径 |
|:-----|:-----|
| 桥接脚本 | `代码文件/tools/feishu_bridge.py` |
| 凭证文件 | `~/.feishu_bot_tmp.json` (chmod 600) |
| 指令队列 | `.claude/im_queue/pending.json` |
| 结果队列 | `.claude/im_queue/done.json` |
| 运行日志 | `临时报告/对话日志/feishu_bridge_YYYY-MM-DD.log` |
| launchd plist | `~/Library/LaunchAgents/com.tielv.feishu-bridge.plist` |
| 防休眠 plist | `~/Library/LaunchAgents/com.tielv.caffeinate.plist` |

## 常用命令

```bash
# 联通性验证
python3 代码文件/tools/feishu_bridge.py --init

# 启动
launchctl load ~/Library/LaunchAgents/com.tielv.caffeinate.plist
launchctl load ~/Library/LaunchAgents/com.tielv.feishu-bridge.plist

# 查看状态
launchctl list | grep feishu

# 停止
launchctl unload ~/Library/LaunchAgents/com.tielv.feishu-bridge.plist
launchctl unload ~/Library/LaunchAgents/com.tielv.caffeinate.plist

# 查看日志
tail -f 临时报告/对话日志/feishu_bridge_$(date +%Y-%m-%d).log
```

## 故障排查

1. **群内发指令无回复** → `launchctl list | grep feishu` 检查进程是否在运行
2. **日志出现 FATAL** → 检查 `~/.feishu_bot_tmp.json` 存在且权限 600
3. **API 返回 401** → Token 自动刷新，观察下次是否恢复
4. **API 返回 99992402** → 检查权限：需 `im:message` + `im:message.group_msg` + `im:chat:readonly`
