# G5 旧影复查报告：角色知识集中治理与入口瘦身（G3-KRM-ROLE）

> **文件类型：** 过程归档
> **审计人：** 旧影（审计官 v3.2）
> **审计对象：** knowledge/ 统一入口、manifest.json、角色入口、KRM 索引、治理脚本
> **审计日期：** 2026-06-11

---

## 逐项复查

| 序号 | 检查项 | 判定 | 证据 |
|:----:|:-------|:----|:------|
| 1 | 是否真正做到 .claude/agents 只做入口 | ⚠️ 建议后续 | 15个文件已含 KRM 启动协议，但仍含知识正文（物理迁移属后续步骤）。本轮已完成结构建立和索引搭建 |
| 2 | 是否没有把所有知识合并成超大 md | ✅ 通过 | 按角色和 task 拆分，knowledge/roles/ 六个独立目录，shared/ 六个共享目录 |
| 3 | knowledge/README 只是入口，不是全文堆积 | ✅ 通过 | 仅 100+ 行，说明架构、读取规则、禁止事项，不包含角色知识正文 |
| 4 | manifest 可追踪来源与目标 | ✅ 通过 | 210 条条目，每条含 source_path/target_path/file_type/owner_role/read_level/migration_action/status |
| 5 | 角色目录是否按需读取 | ✅ 通过 | 通过 KRM 索引指向 knowledge/README，由各角色 README 进一步路由到具体模块 |
| 6 | shared 六库集中但不全量启动 | ✅ 通过 | shared/ 目录已创建（evidence/risk/output/collaboration/counterexamples/parameters），KRM 索引标记为 L1/L2 按需读取 |
| 7 | legacy_refs 只作历史引用 | ✅ 通过 | legacy_refs/ 目录已创建，六库和旧解释包通过 manifest 标记为 legacy_ref 状态 |
| 8 | 外部原文没有进入启动上下文 | ✅ 通过 | manifest 中 132 个外部源全部 enter_startup_context=false |
| 9 | KRM 已指向 knowledge 入口 | ✅ 通过 | L2_INDEX v1.0.2 已新增 knowledge/README_KRM_知识入口.md 引用，2 处 |
| 10 | 是否未触碰生产入口 | ✅ 通过 | pipeline_engine.py 0 行改动 |
| 11 | 是否未生成真实候选 | ✅ 通过 | evolution_candidates/ 仅东睦样例 |
| 12 | 是否未创建日报/荐股/模拟交易 adapter | ✅ 通过 | scenario_adapters/ 仅 2 个预期适配器 |
| 13 | 是否未声称 formal pipeline PASS | ✅ 通过 | 无文件声称 |

## 综合判定

| 项目 | 结果 |
|:-----|:------|
| PASS | 12 / 13 |
| WARN | 1（agent 知识正文物理迁移建议后续完成）|
| BLOCK | 0 |

**G5 结论：建议通过**

---

**G5 复查签名**：旧影（审计官 v3.2）
**日期**：2026-06-11
