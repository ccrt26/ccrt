# 红枫 — 回滚方案: pipeline_engine v1.1

> 编制人: 红枫 | 日期: 2026-05-25

## 回滚触发条件

- 引擎 -Status 输出schema_version异常
- 流程执行中 executor 值不在7角色集合中
- gate 判定行为与设计文档§2.4不符
- 任何角色报告引擎行为异常

## 回滚步骤

1. 从git历史恢复 `pipeline_engine.ps1` v1.0:
   ```
   git checkout HEAD~1 -- 代码文件/监督机制/pipeline_engine.ps1
   ```
2. 恢复 CLAUDE.md §七:
   ```
   git checkout HEAD~1 -- CLAUDE.md
   ```
3. 重置 pipeline_active.json 为v1.0 schema:
   ```
   手动写入v1.0 inactive token
   ```

## 回滚影响

- 回滚后引擎回到6阶段模式，腰子确认需手动执行（回退到修复前的状态）
- 无数据丢失风险
- pipeline_history归档文件保留原始schema版本号，不受影响

## 回滚验证

- 引擎 -Status 输出 gate_1 字段（非 gate_1a/gate_1b）
- -Start 显示 "Stage 1/6"
