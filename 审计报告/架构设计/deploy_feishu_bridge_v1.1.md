# 飞书桥接 — 红枫部署记录

> 日期：2026-05-29 | 版本：v1.1

## 部署步骤

| 步骤 | 操作 | 结果 |
|:---|:-----|:---:|
| 1 | 凭证文件 `~/.feishu_bot_tmp.json` (600) | ✅ |
| 2 | `--init` 连通性验证 (Token+消息拉取) | ✅ |
| 3 | 安装 plist → `~/Library/LaunchAgents/` | ✅ |
| 4 | `launchctl load` caffeinate + bridge | ✅ |
| 5 | 首次自动执行 (launchd RunAtLoad) | ✅ |

## 运行状态

```
com.tielv.caffeinate     → PID 34816, 持续运行 (防休眠)
com.tielv.feishu-bridge  → 每分钟触发一次，单次执行后退出
```

## 回滚方案

```bash
launchctl unload ~/Library/LaunchAgents/com.tielv.feishu-bridge.plist
launchctl unload ~/Library/LaunchAgents/com.tielv.caffeinate.plist
rm ~/Library/LaunchAgents/com.tielv.feishu-bridge.plist
rm ~/Library/LaunchAgents/com.tielv.caffeinate.plist
```

## 影响面

- 零文件修改（纯新增）
- 零 API 变更
- 零数据管线影响
