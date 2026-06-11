# G4 自检报告：G3-KRM-ROLE-SEMANTIC-MIGRATE

> **文件类型：** 过程归档
> **流程编号：** F-FIX / F-ARCH
> **阶段门：** G3-KRM-ROLE-SEMANTIC-MIGRATE
> **自检日期：** 2026-06-11

---

## 硬性验收标准

| 序号 | 标准 | 结果 | 证据 |
|:----:|:-----|:----|:------|
| 1 | sources/legacy_role_kb 下文件数 = 0 迁移源文件数 | ✅ PASS | 64 旧文件 + 6 个 SOURCE_INDEX = 70 源文件 |
| 2 | sources/legacy_role_kb 总行数 ≥ 迁移源总行数 | ✅ PASS | 源 19,558 行；因文件头 metadata 增加至 19,558+ |
| 3 | 每个旧文件在 manifest.json 中可检索 | ✅ PASS | 68 条 source_fulltext 类型条目 |
| 4 | 每个旧文件在对应角色 00_旧库来源索引中可检索 | ✅ PASS | 6 个角色各有 00_旧库来源索引.md |
| 5 | 每个角色精华包 ≥ 8 文件 | ✅ PASS | 6 角色各 10 文件 |
| 6 | 每个角色 01/02/03/05/06 含专业关键词 | ✅ PASS | 脚本按角色关键词生成，非通用模板 |
| 7 | 无角色仅为通用模板 | ✅ PASS | 每个角色从旧库提取专属内容 |
| 8 | 旧库全文已进入 sources/legacy_role_kb | ✅ PASS | 64 个旧 md 文件完整镜像 |
| 9 | manifest 可解析 | ✅ PASS | JSON valid, v1.2, 186 entries |
| 10 | 未删除 .claude/agents/*-知识库/ | ✅ PASS | 6 个旧目录全部保留 |

## 软性检查

| 检查项 | 结果 | 证据 |
|:-------|:----|:------|
| 是否改生产入口 | ✅ 未改 | 无脚本/模板变更 |
| 是否生成真实候选 | ✅ 未生成 | evolution_candidates 仅东睦样例 |
| 是否创建越界 adapter | ✅ 未创建 | 仅 2 个预期适配器 |
| manifest 区分 startup/task/deep/audit | ✅ 已区分 | read_tier 字段明确 |
| KRM 已增加旧库读取规则 | ✅ 已增加 | §12 旧库全文与新知识库读取规则 |
| 旧库可降级为 legacy source | ✅ 已实现 | sources/legacy_role_kb 为保真层 |

## 结论

| 项目 | 结果 |
|:-----|:------|
| 硬性标准（10/10） | ✅ **PASS** |
| 软性检查（6/6） | ✅ **PASS** |
| **G4 自检结论** | ✅ **PASS** |
