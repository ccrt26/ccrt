# D04 回滚手册

> **流程编号**：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE
> **阶段门**：G3（实施阶段）
> **日期**：2026-06-09
> **版本**：v1.0（STEP4 落盘）
> **用途**：STEP4 实施后如需回退的逐文件操作指南

---

## 一、回滚核心原则

| 原则 | 说明 |
|:-----|:------|
| ① 禁止整文件 checkout | 任何存在 pre-existing dirty 的文件不得使用 `git checkout --`。仅保存 patch → 人工审核 → 逐块回退 |
| ② 禁止 git reset | 不执行 `git reset --hard` 或 `git reset --soft` 等破坏性操作 |
| ③ 不默认 rm | 新增文件仅在用户单独确认后处理，不做默认删除 |
| ④ 先保存 patch | 修改文件前先 `git diff` 保存完整 diff |
| ⑤ 人工审核 | 回退前人工逐行审核 patch 内容，确认只回退 STEP4 新增/修改块 |
| ⑥ 保护 dirty | pre-existing dirty 段落在任何回滚路径中不得被覆盖 |
| ⑦ 回滚后验证 | 回滚后重新运行全部验收命令确认状态 |
| ⑧ 回滚不回退架构 | 回滚仅取消文件修改，不改变 D04 架构结论（架构由 G2 方案保障） |

---

## 二、受影响文件清单

### 2.1 修改文件

| # | 文件 | 修改性质 | pre-existing dirty | 回滚方式 |
|:-:|:-----|:---------|:------------------|:---------|
| M1 | `.gitignore` | M | ⚠️ 有（STEP2 新增 L2 排除规则） | 逐块移除 STEP4 新增行 |
| M2 | `runtime_entry_registry.json` | M | ✅ 无（纯 STEP4 修改） | 逐块移除 STEP4 新增/修改条目 |
| M3 | `win_legacy_migration_register.json` | M | ✅ 无（纯 STEP4 重写） | 逐块移除 STEP4 新增条目 |
| M4 | `金融铁律/金融铁律_v1.17.md` | M | ⚠️ 有 pre-existing dirty | **禁止整文件 checkout**。仅逐块移除 D04/L1/L2/L3 口径同步段落 |
| M5 | `AUDIT_验收规则与模板_v1.0.md` | M | ✅ 无（纯 STEP4 追加） | 逐块移除 D04 §4 审计接入段落 |

### 2.2 新增文件

| # | 文件 | 状态 | 回滚方式 |
|:-:|:-----|:-----|:---------|
| N1 | `STEP4_旧入口最终处置矩阵.md` | 新增文档 | 用户单独确认后处理；不得默认 rm |
| N2 | `D04_运行手册.md` | 新增文档 | 用户单独确认后处理 |
| N3 | `D04_回滚手册.md` | 新增文档（本文件） | 用户单独确认后处理 |
| N4 | `D04_常规审计接入报告.md` | 新增文档 | 用户单独确认后处理 |
| N5 | `STEP4_地基脚本收口报告.md` | 新增文档 | 用户单独确认后处理 |
| N6 | `STEP4_验收命令结果.md` | 新增文档 | 用户单独确认后处理 |
| N7 | `五步优化最终总结.md` | 新增文档 | 用户单独确认后处理 |
| N8 | `STEP4_G2_玉夜数据事实确认.md` | G2 角色确认产物 | 用户单独确认后处理 |
| N9 | `STEP4_G2_新安测试验收确认.md` | G2 角色确认产物 | 用户单独确认后处理 |
| N10 | `STEP4_G2_腰子金融口径前置确认.md` | G2 角色确认产物 | 用户单独确认后处理 |

---

## 三、逐文件回滚步骤

### 3.1 回滚 M2：runtime_entry_registry.json

**风险：低（无 pre-existing dirty）**

```bash
# 保存当前状态
cp 00_项目地基/06_调度与运行/runtime_entry_registry.json /tmp/runtime_entry_before_rollback.json

# 查看 STEP4 新增的 5 个条目（E3-E7）
# 手动删除以下条目：
#   - daily_workflow.ps1（status 改为 forbidden 的行）
#   - batch_data_collector.ps1（status 改为 forbidden 的行）
#   - check_d04_health.py
#   - check_freshness_degradation_l2
#   - check_numeric_source_consistency_kline_l2
# 恢复 E1/E2 的 note 字段（删除 L1 日报编排入口/数据采集核心 注释）

# 回滚后验证
python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json
```

### 3.2 回滚 M3：win_legacy_migration_register.json

**风险：低（纯 STEP4 重写，但涉及 13 条原有记录的保留）**

```bash
# 从 STEP3 快照中恢复原始 19 条记录（删除末尾新增的 12 条）
# 新增条目清单：
#   - archive_data.ps1（forbidden）
#   - gen_monthly_report.ps1（under_review）
#   - catchup_launcher.ps1（under_review）
#   - _win32_legacy/（legacy_isolated，6 条）
#   - build_docx.ps1（forbidden）
#   - gen_pdf.ps1（forbidden_when_python_available，3 条）
#   - _split_fetcher.py（active，2 条）

# 回滚后验证
python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json
```

### 3.3 回滚 M4：金融铁律/金融铁律_v1.17.md

**风险：高（有 pre-existing dirty + 金融规则保护）**

```bash
# 禁止整文件 checkout
# 1. 保存当前完整 diff
git diff 金融铁律/金融铁律_v1.17.md > /tmp/financial_iron_step4.diff

# 2. 人工搜索以下关键字段落的 STEP4 新增内容并删除：
#    - "| 14 | D04 数据中台" 整行（数据源表新增行）
#    - "### 1.2.3 数据中台架构（D04 / L1/L2/L3）" 整节（含表格+说明）
#    - "| [14] | D04 数据中台（C-D04-0001）" 整行（实测状态表新增行）

# 3. 确认删除后不残留 D04/L1/L2/L3 关键字（应恢复为 0 处引用）
grep -c "D04\|L1/L2/L3\|C-D04-0001" 金融铁律/金融铁律_v1.17.md
# 预期：0

# 4. 验证未触碰金融规则
grep -c "rule-no-fabrication\|rule-pe-calc\|rule-style-freeze" 金融铁律/金融铁律_v1.17.md
# 预期：与回滚前一致
```

### 3.4 回滚 M5：AUDIT_验收规则与模板_v1.0.md

**风险：低（无 pre-existing dirty）**

```bash
# 删除末尾 "## 4. D04 数据中台常规审计接入" 至文件末尾的全部内容
# 恢复文件末尾为原始版本号声明行：
# "*本文件整合自 `阶段验收报告模板.md`..."
```

### 3.5 回滚新增文件（N1-N10）

**风险：低，需用户单独确认**

```bash
# 仅在用户确认后执行，不得默认 rm
# for f in STEP4_旧入口最终处置矩阵.md ...; do
#   read -p "确认删除 $f？(y/N) "
# done
```

---

## 四、全量回退路线说明

> ⚠️ **全量回退并非自动命令，而是人工审核 patch 后的逐块回退路线。**
> ⚠️ 禁止 git reset、禁止整文件 git checkout --、禁止批量 rm。

全量回退步骤：

1. **保存完整 diff**：`git diff > /tmp/step4_full_patch.diff`
2. **逐文件审核**：按 §三 逐文件操作
3. **验证每个文件**：每回退一个文件后运行对应的验收命令
4. **回滚后验收**：恢复全部文件后运行全部验收命令
5. **通知相关角色**：回退完成后通知玉夜/新安/旧影确认

### 回滚后验证清单

```bash
# 1. JSON 语法
python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json
python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json

# 2. D04 健康检查
python3 scripts/check_d04_health.py --dry-run

# 3. 金融铁律语法（无需验证，但确认未触碰规则）
grep -c "D04\|C-D04-0001\|L1/L2/L3" 金融铁律/金融铁律_v1.17.md
# 预期：0

# 4. 审计模板
tail -3 00_项目地基/08_审计与验收/AUDIT_验收规则与模板_v1.0.md
# 预期：最后一行是 "*本文件整合自..."，无 D04 段落

# 5. 禁止范围核验
grep -rn "unified_data_source\|UnifiedDataSource" \
  代码文件/tools/daily_orchestrator.py \
  代码文件/每日荐股/scripts/daily_workflow.py
# 预期：空

# 6. l2_cache.db 未创建
test ! -e 代码文件/数据/l2_cache/l2_cache.db && echo "✅"
```

---

## 五、预提交检查

在提交 STEP4 修改前，确认以下预提交检查通过：

| # | 检查项 | 命令 | 预期 |
|:-:|:-------|:-----|:-----|
| 1 | 代码文件未修改 | `git status --short -- 代码文件/` | 仅 data_full.json 等 pre-existing dirty |
| 2 | l2_cache.db 未创建 | `test ! -e 代码文件/数据/l2_cache/l2_cache.db` | 0 |
| 3 | 正式入口未引用 UDS | `grep -rn "UnifiedDataSource" 代码文件/tools/daily_orchestrator.py` | 空 |
| 4 | sector_phase 未清理 | `git diff -- 代码文件/数据/data_scored.json | grep "sector_phase\|SectorPhase"` | 空（未涉及）|
| 5 | 注册表 JSON 有效 | `python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json` | exit=0 |
| 6 | win_legacy JSON 有效 | `python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json` | exit=0 |

---

*流程编号：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE | 阶段门：G3*
*formal pipeline actor/HMAC 明示例外*
