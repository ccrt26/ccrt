# G4 自检报告：角色知识集中治理与入口瘦身（G3-KRM-ROLE）

> **文件类型：** 过程归档
> **读取级别：** 审计时读（L3）
> **流程编号：** F-KNOW + F-ROLE + F-GATE + F-FIX
> **阶段门：** G3-KRM-ROLE
> **自检人：** 执行模型
> **日期：** 2026-06-11

---

## 1. 新增文件清单

| 类别 | 文件/目录 | 说明 |
|:-----|:----------|:------|
| 知识入口 | `00_项目地基/07_知识进化/knowledge/README_KRM_知识入口.md` | 知识正文统一入口 |
| manifest | `00_项目地基/07_知识进化/knowledge/manifest.json` | 210条知识源索引 |
| role dirs | `roles/{yuye,qingshan,liujin,xinge,shanmao,yaozi}/` | 六个角色目录 |
| shared dirs | `shared/{evidence_rules,risk_rules,output_rules,collaboration_rules,counterexamples,parameters}/` | 共享规则目录 |
| 脚本 | `scripts/kb_consolidation/build_knowledge_manifest.py` | manifest 构建 |
| 脚本 | `scripts/kb_consolidation/generate_role_entry_patch.py` | 入口瘦身补丁 |
| 脚本 | `scripts/kb_consolidation/check_knowledge_consolidation.py` | 治理检查 |
| KRM 更新 | `L2_INDEX_知识库读取分层与执行文件清单_v1.0.md` | 新增 knowledge/ 引用 v1.0.2 |

## 2. 检查结果

| 检查项 | 命令/证据 | 结果 |
|:-------|:----------|:------|
| knowledge README 存在 | `find 07_知识进化/knowledge -name "README*"` | ✅ PASS |
| manifest.json 可解析 | `python3 -c "import json; json.load(open(...))"` | ✅ PASS (210条) |
| roles 六目录 | `ls knowledge/roles/` | ✅ PASS |
| shared 六目录 | `ls knowledge/shared/` | ✅ PASS |
| .claude/agents 启动协议 | `grep -c "启动协议" .claude/agents/*.md` | ✅ PASS (15/15) |
| .claude/agents 知识正文 | 15个文件仍含知识正文 | ⚠️ WARN（物理迁移属后续步骤，本轮仅建结构） |
| KRM 指向 knowledge | `grep -c "knowledge/README" L2_INDEX_` | ✅ PASS (2 处引用) |
| 未创建真实候选 | `ls evolution_candidates/` 仅东睦样例 | ✅ PASS |
| 未创建越界 adapter | `ls scenario_adapters/` 仅2个预期 | ✅ PASS |
| 未修改生产入口 | `git diff scripts/pipeline_engine.py 0 lines` | ✅ PASS |
| 外部源不进启动上下文 | manifest 中 132 个外部源 enter_startup_context=false | ✅ PASS |
| 未声称 formal pipeline PASS | 无文件声明 | ✅ PASS |

## 3. 综合结论

| 项目 | 结果 |
|:-----|:------|
| PASS | 11 / 12 |
| WARN | 1（agent 文件知识正文物理迁移属后续步骤）|
| BLOCK | 0 |
| **G4 自检结论** | ✅ **PASS（带 WARN）** |
