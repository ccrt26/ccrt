# IM消费者 — 红枫部署记录

> 日期：2026-05-29

| 步骤 | 操作 | 结果 |
|:---|:-----|:---:|
| 1 | im_consumer.py (147行, L0) | ✅ |
| 2 | plist → ~/Library/LaunchAgents/ | ✅ |
| 3 | launchctl load | ✅ |

## 运行状态

```
com.tielv.caffeinate      → PID 34816  防休眠
com.tielv.feishu-bridge   → 每60s      拉取消息→写入pending
com.tielv.im-consumer     → 每60s      读取pending→claude执行→写入done
```

## 完整回路

```
飞书群 → bridge(拉取) → pending.json → consumer(执行) → done.json → bridge(回传) → 飞书群
```

## 回滚

```bash
launchctl unload ~/Library/LaunchAgents/com.tielv.im-consumer.plist
rm ~/Library/LaunchAgents/com.tielv.im-consumer.plist
```
