# IM指令消费者 — 设计补充

> 版本 v1.0 | 2026-05-29 | 情墨 | pipeline_stage: complete
> 关联：design_feishu_bridge_v1.1.md §四 数据流

## 背景

bridge 写入 pending.json，但无消费者读取执行。需补充消费者脚本完成闭环。

## 设计

```
im_consumer.py (~100行, L0)
  Cron/launchd 每60s触发
  → 读 pending.json (status=new)
  → 标记 processing
  → 调用 claude -p "指令" --output-format text
  → 等待完成 (timeout=300s)
  → 写 done.json (status=done/error)
```

## 关键决策

| 项 | 选择 | 理由 |
|:---|:-----|:-----|
| 执行方式 | `claude -p "cmd"` 非交互模式 | Claude Code CLI 原生支持 |
| 超时 | 300s (5分钟) | 深度分析可能较长，超过则标记 error |
| 并发 | 1 条/次 | 避免多个 claude 进程争抢 |
| 调度 | launchd 每60s | 与 bridge 解耦，独立进程 |
| 级别 | L0 | 纯消费者，无业务逻辑 |

## 代码结构

```
im_consumer.py
├── 读 pending.json → 取第一条 status=new
├── 标记 status=processing
├── subprocess.run(["claude", "-p", cmd], timeout=300)
├── 写 done.json
└── _log() 日志
```

## Token 影响

纯脚本，零 AI Token 消耗。`claude -p` 的 Token 属于用户正常使用，与本脚本无关。
