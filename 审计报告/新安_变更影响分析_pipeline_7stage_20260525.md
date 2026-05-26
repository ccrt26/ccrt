# 新安 — 变更影响分析: pipeline_engine v1.1

> 分析人: 新安 | 日期: 2026-05-25

## 变更摘要

pipeline_engine.ps1 v1.0→v1.1: 6阶段→7阶段 + gate_1拆分为gate_1a/gate_1b

## 影响范围

| 文件 | 影响等级 | 说明 |
|:-----|:--------|:-----|
| pipeline_engine.ps1 | **核心** | 全部函数涉及阶段数组引用，但均为 `$STAGE_EXECUTORS` 数组驱动 |
| CLAUDE.md §七 | 低 | 行级文档更新 |
| engineering-delivery-pipeline.md | 低 | memory同步 |

## 下游影响

| 下游模块 | 影响 | 原因 |
|:---------|:----:|:-----|
| pipeline_token.ps1 | 无 | wrapper委托给engine，不硬编码阶段号 |
| pre-commit-check.ps1 | 无 | 只读 active+executor 字段 |
| write_protection_hook.ps1 | 无 | 同上 |
| pipeline_active.json | schema升级 | v1.0→v1.1自动迁移（gate_1→gate_1a/gate_1b） |

## 风险评级

**低风险**。变更完全在engine内部，CLI接口不变，下游零影响。
