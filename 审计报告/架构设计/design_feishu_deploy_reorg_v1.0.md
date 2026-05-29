# 飞书桥接文件重组 — 架构设计

> 版本 v1.0 | 2026-05-29 | 情墨 | pipeline_stage: complete

## 背景

飞书桥接的 plist/脚本/文档散落在5个位置，需集中管理。

## 方案

### 目标结构

```
代码文件/deploy/feishu_bridge/   ← 新建统一目录
├── README.md                     # 部署说明
├── deploy.sh                     # 统一部署（cp plist + launchctl load）
├── rollback.sh                   # 统一回滚（launchctl unload + rm）
├── status.sh                     # 状态检查
├── com.tielv.feishu-bridge.plist
├── com.tielv.im-consumer.plist
└── com.tielv.caffeinate.plist
```

### 变更

| 操作 | 文件 |
|:---|:-----|
| 新建 | `代码文件/deploy/feishu_bridge/` 目录 |
| 新建 | `deploy.sh` / `rollback.sh` / `status.sh` |
| 移动 | 3 个 plist 从 `代码文件/tools/` → `代码文件/deploy/feishu_bridge/` |
| 删除 | `代码文件/tools/com.tielv.*.plist`（旧位置） |
| 更新 | `~/Library/LaunchAgents/` 重新同步 plist |

### 级别

全部 L0（工具/部署类，无业务逻辑）

### Token 影响

纯文件移动 + shell 脚本，零 AI Token。
