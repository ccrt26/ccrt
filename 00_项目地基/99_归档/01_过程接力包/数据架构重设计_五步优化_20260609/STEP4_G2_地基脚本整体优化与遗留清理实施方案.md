# STEP4 G2 实施方案：地基脚本整体优化与遗留清理（补修版）

> **流程编号**：F-ARCH（主流程）+ F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE
> **阶段门**：G0（路由完成）→ **G2（技术方案设计 — 当前在此）** → ⛔ 暂停 → G3/G4/G5/G6
> **日期**：2026-06-09
> **版本**：补修版（修正 G2 责任边界、回滚方案、文件名、前置条件）
> **状态**：G0 路由完成，G2 方案已落盘（补修版）— **暂停等待用户复查确认进入 G3**

---

## 一、前置检查结论

| 检查项 | 结果 | 证据 |
|:-------|:-----|:------|
| STEP3_UnifiedDataSource影子接入报告.md 存在并 PASS | ✅ | 已读，G5 旧影建议通过 + G6 腰子同意放行 |
| STEP3_旧入口适配矩阵.md 已列出所有旧入口 | ✅ | 5 个旧入口 + 3 个新入口全部列出 |
| STEP3_GoldenDiff或ShadowDiff报告.md 无 BLOCK | ✅ | ALL PASS，close/volume/change_pct 0 差异 |
| 用户已允许启动 STEP4 G0/G2 | ✅ | 用户指令明确："按 CCRT 标准流程正式启动：STEP4" |
| 用户尚未授权进入 STEP4 G3 | ⚠️ | 不得把"启动 STEP4"解释为"允许实施清理" |
| l2_cache.db 未创建（不允许自动创建） | ✅ | `test ! -e` 确认不存在 |
| cached_data_source.py 未接入 UDS | ✅ | grep 确认 0 引用 |
| daily_workflow.py 未接入 UDS | ✅ | grep 确认 0 引用 |
| Formal pipeline 例外延续 | ⚠️ | RUN-20260609-012906-d11109 仍停 design；actor/HMAC 继续例外 |
| 金融铁律与 D04 口径同步缺口 | ⚠️ | 金融铁律_v1.17.md 含 **0** 处 D04/L2/L3/UnifiedDataSource 引用 |
| sector_phase 不一致问题 | ⚠️ | 已在 STEP3 被标记为"非 STEP3 问题"，本次 STEP4 也不涉及 |
| .gitignore 基线状态 | ⚠️ | 当前 .gitignore 已处于 dirty 状态，不得写"无 pre-existing dirty" |

### 1.1 例外声明确认

> **formal pipeline actor/HMAC：未通过，继续作为明示例外。**
> 本方案基于用户授权接力包流程确认，不等同于 formal pipeline PASS。
> 不得伪造 actor/HMAC 推进 sign_off 或 advance。

---

## 二、流程编号与阶段门

| 字段 | 值 |
|:-----|:----|
| **主流程编号** | **F-ARCH**（地基/架构变更） |
| **挂载流程** | **F-DATA**（数据事实变更 — 重复缓存收口+口径同步） |
| | **F-GATE**（闸门/验收脚本变更 — 审计接入） |
| | **F-MIGRATE**（目录迁移/归档 — Windows 遗留资产登记） |
| | **F-SCHEDULE**（调度/运行入口 — runtime_entry_registry 更新） |
| **启用阶段门** | G0 → **G2（当前）** → G3 → G4 → G5 → G6 |
| **跳过阶段门** | G1（简化口径确认 — 金融铁律同步仅涉及 D04 数据源口径，不改变金融规则、不改变投资建议、不改变分析结论生成逻辑。但腰子须在 G2 前置确认此口径范围后方可进入 G3 修改金融铁律） |

### 阶段门路线图

```
G0 (阿黑·路由) — 已完成
  ↓
G2 (情墨·技术方案) — ⛔ 当前在此，已落盘（补修版）
  ↓
⛔ 暂停点 — 等待各角色确认 + 用户书面确认 "确认进入 STEP4 G3"
  ↓
G3 (红结·实施) — 按执行顺序 Phases 1-6
  ↓
G4 (红结·自检) — 执行全部验收命令
  ↓
G5 (旧影·独立复查) — 单独判定
  ↓
G6 (腰子放行 + 用户确认) — 五步优化最终总结
```

---

## 三、角色职责与待确认项

> G2 是技术方案设计阶段。以下为本方案的职责定义，所有角色结论由角色本人输出，阿黑不得代签。

| 角色 | 阶段门 | 职责 | 当前状态 |
|:-----|:-------|:-----|:---------|
| **阿黑** | G0→G2 | **仅限** G0 路由与阶段调度；汇总方案草案；设置暂停点；不得实施、不得签署技术方案、不得代签任何角色结论 | ✅ G0 路由完成，G2 方案草案已汇总 |
| **情墨** | **G2 主责** | 技术方案审定：架构/目录/契约一致性、旧入口处置矩阵、重复缓存收口方案、回滚边界、清理方案一致性确认 | ⬜ **待复查确认** |
| **玉夜** | G2 参与 | D04/L1/L2/L3 数据事实确认、旧入口数据口径、重复缓存路径识别、权威源一致性确认 | ⬜ **待复查确认** |
| **新安** | G2 参与 | 测试策略、验收命令完整性、禁止范围核验、回滚验证策略确认 | ⬜ **待复查确认** |
| **腰子** | G2 前置口径确认 | 因 STEP4 计划修改 `金融铁律/金融铁律_v1.17.md`（仅同步 D04 数据源口径），需在 G2 确认：本次只同步 D04 数据源口径，不改变金融规则、不改变投资建议、不改变分析结论生成逻辑。腰子未确认前，不得进入 G3 修改金融铁律 | ⬜ **待口径确认** |
| **红结** | G3 | 仅在用户明确回复"确认进入 STEP4 G3"后按允许范围实施修改 | ⬜ G3 阶段 |
| **旧影** | G5 | 独立复查验收报告；不得提前复查，不得由执行模型代签 | ⬜ G5 阶段 |
| **腰子** | G6 | 放行确认签字；不得由阿黑或执行模型代签 | ⬜ G6 阶段 |

> **驳回条件**：情墨、玉夜、新安或腰子（口径确认）对本方案任何设计点持异议 → BLOCK，退回 G2 修订。不得带异议进入 G3。

---

## 四、允许修改范围（G3 阶段）

| 类别 | 路径/文件 | 操作 |
|:-----|:----------|:-----|
| `.gitignore` | `.gitignore` | M |
| Runtime 注册表 | `00_项目地基/06_调度与运行/runtime_entry_registry.json` | M |
| Legacy 迁移注册表 | `00_项目地基/06_调度与运行/win_legacy_migration_register.json` | M |
| 审计模板 | `00_项目地基/08_审计与验收/` | M/N |
| 金融铁律 | `金融铁律/金融铁律_v1.17.md` | **M**（仅 §1.2 数据源编号表补充 D04 说明，不改变金融规则。需腰子前置确认） |
| 运行手册 | `00_项目地基/02_数据架构重设计/五步优化接力包/D04_运行手册.md` | N |
| 回滚手册 | `00_项目地基/02_数据架构重设计/五步优化接力包/D04_回滚手册.md` | N |
| 审计接入报告 | `00_项目地基/02_数据架构重设计/五步优化接力包/D04_常规审计接入报告.md` | N |
| 收口报告 | `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_地基脚本收口报告.md` | N |
| 验收结果 | `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_验收命令结果.md` | N |
| 最终总结 | `00_项目地基/02_数据架构重设计/五步优化接力包/五步优化最终总结.md` | N |
| 旧入口矩阵 | `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_旧入口最终处置矩阵.md` | N |

### 4.1 删除或移动文件的条件

删除或移动任何现有文件 **必须先列清单并等待用户确认**，不得直接操作。

---

## 五、禁止修改范围

| 禁令 | 说明 |
|:-----|:------|
| ⛔ 禁止无证据删除脚本 | 无法证明无用的脚本必须保留 |
| ⛔ 禁止删除回滚路径 | 回滚手册保留，不删除旧文件 |
| ⛔ 禁止修改正式报告产物 | `重点股票/股票报告/`、`每日荐股/评估报告/` |
| ⛔ 禁止清理用户未确认的历史数据 | `历史数据/` 全体保留 |
| ⛔ 禁止修改 `代码文件/数据/unified_data_source.py` | STEP3 产物，不改 |
| ⛔ 禁止修改 `scripts/run_shadow_diff.py` | STEP3 产物，不改 |
| ⛔ 禁止修改 `scripts/migrate_historical_kline.py` | STEP3 产物，不改 |
| ⛔ 禁止修改 `tests/test_d04_fallback.py` | STEP3 产物，不改 |
| ⛔ 禁止创建 l2_cache.db | 需用户单独授权 |
| ⛔ 禁止切换 UnifiedDataSource 到生产 | Phase 3 及以上 |
| ⛔ 禁止修改日报/深度分析正式入口 | `daily_workflow.py/daily_orchestrator.py/cached_data_source.py` |
| ⛔ 禁止执行 destructive git 命令 | 无 `git reset --hard`、无整文件 `git checkout --` |
| ⛔ 禁止处理 GitHub | 非本轮范围 |
| ⛔ 禁止修改 `capability_registry.json` | STEP1 已冻结 |
| ⛔ 禁止修改 `source_registry.json` | STEP1 已冻结 |
| ⛔ 禁止修改 `numeric_field_mapping.json` | STEP1 已冻结 |
| ⛔ 禁止修改 `freshness_rules.json` | STEP1 已冻结 |
| ⛔ 禁止把 sector_phase 残留混入 STEP4 自动清理 | 另起 F-DATA/F-FIX |

---

## 六、文件级修改清单（G3 阶段）

### 6.1 修改文件

| # | 文件路径 | 操作 | 修改内容 | 风险等级 |
|:-:|:---------|:-----|:---------|:---------|
| M1 | `.gitignore` | M | 补充 D04 审计日志/运行手册/回滚手册排除规则（如有必要）。注意：当前 .gitignore 已有 dirty，修改前必须记录 baseline diff | L1 |
| M2 | `00_项目地基/06_调度与运行/runtime_entry_registry.json` | M | 更新条目：标注 `check_d04_health.py` 为常规巡检；标注 `run_shadow_diff.py` 为 STEP3 遗留，纳入日常可选运行；更新 `check_freshness_degradation.py & check_numeric_source_consistency.py` 的 L2 相关描述 | L1 |
| M3 | `00_项目地基/06_调度与运行/win_legacy_migration_register.json` | M | 补充 `_win32_legacy/` 目录下的资产条目；扫描未登记的 .ps1 文件 | L1 |
| M4 | `金融铁律/金融铁律_v1.17.md` | M | 在 §1.2 数据源编号表中补充 D04/L2/L3 说明条目；在 §1.2 中新增"数据中台架构说明"段落。**前置条件：腰子确认本次仅同步口径，不改变金融规则** | L1 |
| M5 | `00_项目地基/08_审计与验收/AUDIT_验收规则与模板_v1.0.md` | M | 增加 D04 常规日检/周检/月检接入说明；补充 `check_d04_health.py` 验收命令模板 | L0 |

### 6.2 新增文件

| # | 文件路径 | 操作 | 内容说明 | 风险等级 |
|:-:|:---------|:-----|:---------|:---------|
| N1 | `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_旧入口最终处置矩阵.md` | N | 旧入口状态固化：保留/适配/废弃/归档 四类状态 | L0 |
| N2 | `00_项目地基/02_数据架构重设计/五步优化接力包/D04_运行手册.md` | N | D04 日常运维操作手册（启动/检查/恢复/停止） | L0 |
| N3 | `00_项目地基/02_数据架构重设计/五步优化接力包/D04_回滚手册.md` | N | D04 回滚步骤（逐文件回退/全量回退/验证方法） | L0 |
| N4 | `00_项目地基/02_数据架构重设计/五步优化接力包/D04_常规审计接入报告.md` | N | D04 进入常规审计的检测接入说明 | L0 |
| N5 | `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_地基脚本收口报告.md` | N | STEP4 收口报告 | L0 |
| N6 | `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_验收命令结果.md` | N | 验收命令运行结果 | L0 |
| N7 | `00_项目地基/02_数据架构重设计/五步优化接力包/五步优化最终总结.md` | N | 五步优化整体总结 | L0 |

### 6.3 待确认登记/冻结项（G3 第一轮仅更新注册表状态，不删除/移动物理文件）

| # | 文件路径 | 建议注册表操作 | 理由 | 依赖证据 |
|:-:|:---------|:---------------|:-----|:---------|
| R1 | `代码文件/每日荐股/scripts/archive_data.ps1` | 标记为 `forbidden` | 已有 Python 版 (archive_data.py) | Python 版已纳入 L3 归档 |
| R2 | `代码文件/每日荐股/scripts/gen_monthly_report.ps1` | 标记为 `under_review` | 需确认是否有 Python 替代 | 待查 |
| R3 | `代码文件/每日荐股/scripts/monthly_learn.ps1` | 标记为 `under_review` | 是否已在 Python 版实现 | 待查 |
| R4 | `代码文件/tools/build_docx.ps1` | 标记为 `forbidden` | 已有 Python build_tools.py | 已验证 |
| R5 | `代码文件/tools/gen_pdf.ps1`、`gen_eval_pdf.ps1`、`gen_keystock_pdf.ps1` | 标记为 `forbidden_when_python_available` | 已有 Python convert_md_to_pdf.py | 需确认覆盖 |
| R6 | `代码文件/tools/git_autocommit.ps1` | 更新 status | 当前为 `under_review`，需确认状态 | 已有 Python git_autocommit.py |

> **G3 第一轮仅允许更新 `win_legacy_migration_register.json` 中的状态登记。**
> **不删除任何物理文件，不移动任何物理文件。**
> **物理删除/移动必须另起清单，用户单独确认。**

---

## 七、旧入口最终处置矩阵草案

基于 STEP3 适配矩阵 + 当前现状调查，STEP4 G3 将固化以下最终状态：

| 旧入口 | 文件 | 当前状态 | 最终处置 | 说明 |
|:-------|:-----|:---------|:---------|:------|
| **CachedDataSource** | `代码文件/lib/cached_data_source.py` | ⬜ pre-existing dirty，未改造 | **保留** — 继续作为 L1 日报读取入口 | 不删除，不改返回值格式。Phase 3 评估是否 shadow 接入 |
| **daily_workflow.py** | `代码文件/每日荐股/scripts/daily_workflow.py` | ⬜ pre-existing dirty | **保留** — 继续作为日报编排入口 | 不修改 |
| **batch_data_collector.py** | `代码文件/每日荐股/scripts/batch_data_collector.py` | ✅ 活跃 | **保留** — 数据采集链条核心 | 不修改 |
| **daily_orchestrator.py** | `代码文件/tools/daily_orchestrator.py` | ✅ 活跃 | **保留** — 统一调度入口 | 保持 L1 链路。Phase 3 再评估 |
| **archive_data.py** | `代码文件/每日荐股/scripts/archive_data.py` | ✅ 活跃 | **保留** — L3 归档入口 | 保持 L3 链路 |
| **stock_data_fetcher_*.py** | `代码文件/每日荐股/scripts/stock_data_fetcher_*.py` | ✅ 活跃 | **保留** — 数据采集实现 | 不修改 |
| **stock_data_fetcher_*.ps1** | `代码文件/每日荐股/scripts/stock_data_fetcher_*.ps1` | Windows legacy | **废弃（已冻结）** — 更新 win_legacy 状态 | Python 版已全替代 |
| **archive_data.ps1** | `代码文件/每日荐股/scripts/archive_data.ps1` | Windows legacy | **废弃（已冻结）** | Python archive_data.py 已替代 |
| **gen_monthly_report.ps1** | `代码文件/每日荐股/scripts/gen_monthly_report.ps1` | Windows legacy | **待确认** — 需检查 Python 替代 | 待 G3 阶段核查 |
| **catchup_launcher.ps1** | `代码文件/每日荐股/scripts/catchup_launcher.ps1` | Windows legacy | **待确认** — 需检查 Python 替代 | 待 G3 阶段核查 |
| **\_win32_legacy/** | `_win32_legacy/` 目录 | ✅ 已隔离 | **保留隔离** — 标记为 `legacy_isolated` | 不加修改，不入运行时 |
| **UnifiedDataSource** | `代码文件/数据/unified_data_source.py` | ✅ 新增 (STEP3) | **保留** — 保持 shadow 模式。Phase 3 前不切生产 | 不改 |

### 7.1 处置状态语义

| 状态 | 含义 | 是否可以修改/删除 |
|:-----|:------|:------------------|
| **保留** | 继续作为生产入口，保持现状 | ❌ 不修改（除重大 bug 修复） |
| **废弃(已冻结)** | 不再使用，但保留物理文件作为回滚证据 | ❌ 不删除，仅更新注册表状态 |
| **待确认** | 需要进一步核查是否有已替换的 Python 版 | ⬜ G3 阶段确认后更新状态 |
| **遗留隔离** | `_win32_legacy/` 已物理隔离，不纳入调度 | ❌ 不删除 |

---

## 八、runtime_entry_registry 更新方案

### 8.1 当前状态分析

当前 `runtime_entry_registry.json` 有 16 条记录，分为：
- **macOS 活跃调度**（4 条）：`generate_launchd.py`, `launchd`, `daily_workflow.py`, `batch_data_collector.py`
- **跨平台工具**（3 条）：`daily_orchestrator.py`, `check_runtime_entry_authority.py`
- **Windows 禁止项**（5 条）：`Windows Task Scheduler`, `register_tasks.ps1`, `setup_scheduler.ps1`, `register_pigeon_scheduler.ps1`（全部 forbidden）
- **Windows 条件禁止**（4 条）：`batch_data_collector.ps1`, `daily_workflow.ps1`（forbidden_when_python_replacement_exists）

### 8.2 需更新的条目

| # | 条目 | 操作 | 更新内容 |
|:-:|:-----|:-----|:---------|
| E1 | `daily_workflow.py` | M | authority 备注增加"L1 日报编排入口（D04 Phase 2 前保持 L1 链路）" |
| E2 | `batch_data_collector.py` | M | authority 备注增加"数据采集核心（保持旧链路，不改读 D04）" |
| E3 | `daily_workflow.ps1` | M | status 从 `forbidden_when_python_replacement_exists` 改为 `forbidden`（Python 版已稳定） |
| E4 | `batch_data_collector.ps1` | M | status 从 `forbidden_when_python_replacement_exists` 改为 `forbidden`（Python 版已稳定） |
| E5 | **新增** `check_d04_health.py` | N | entry = `check_d04_health.py`, authority = `d04_health_check`, path = `scripts/check_d04_health.py`, platform = `cross`, status = `active` |
| E6 | **新增** `check_freshness_degradation.py --tier l2` | N | entry = `check_freshness_degradation_l2`, authority = `freshness_audit_l2`, path = `scripts/check_freshness_degradation.py --tier l2`, platform = `cross`, status = `active` (phase 2 启用) |
| E7 | **新增** `check_numeric_source_consistency.py kline_l2` | N | entry = `check_numeric_source_consistency_kline_l2`, authority = `numeric_audit_l2`, path = `scripts/check_numeric_source_consistency.py` (kline_l2), platform = `cross`, status = `active` (phase 2 启用) |

---

## 九、win_legacy_migration_register 更新方案

### 9.1 当前状态

当前 19 条记录，覆盖了主要 .ps1→.py 映射。`_win32_legacy/` 目录下有 2 个 .ps1 文件和若干子目录未在注册表中登记。

### 9.2 需更新的条目

| # | 条目 | 操作 | 更新内容 |
|:-:|:------|:-----|:---------|
| W1 | `代码文件/每日荐股/scripts/archive_data.ps1` | **N** | 新增：legacy_path + python_replacement = archive_data.py, status = `forbidden` |
| W2 | `代码文件/每日荐股/scripts/gen_monthly_report.ps1` | **N** | 新增：待核查 Python 替代，status = `under_review` |
| W3 | `代码文件/每日荐股/scripts/catchup_launcher.ps1` | **N** | 新增：待核查 Python 替代，status = `under_review` |
| W4 | `_win32_legacy/` 目录资产 | **N** | 新增条目：`_win32_legacy/` 作为一个整体 legacy 隔离资产登记，status = `legacy_isolated` |
| W5 | `代码文件/tools/git_autocommit.ps1` | M | status 从 `under_review` 改为 `forbidden_when_python_available`（Python git_autocommit.py 已验证存在） |
| W6 | `代码文件/tools/build_docx.ps1` | **N** | 新增：python_replacement = build_tools.py, status = `forbidden` |
| W7 | `代码文件/tools/gen_pdf.ps1` | **N** | 新增：python_replacement = convert_md_to_pdf.py, status = `forbidden_when_python_available` |
| W8 | `代码文件/每日荐股/scripts/_split_fetcher.py` `_split_fetcher_v2.py` | **N** | 新增：标记为 `split_layer_tool`, status = `active`（工具脚本，非调度入口） |

---

## 十、重复缓存路径收口方案

### 10.1 当前重复缓存分析

通过现状调查，识别以下重复/散落的 K 线数据路径：

| 源 | 路径 | 类型 | 用途 | 与 D04 关系 |
|:---|:-----|:-----|:-----|:------------|
| kline_cache | `代码文件/数据/kline_cache/{code}.json` | L1 当日 | 日报 K 线主源 | D04 read-through 保留 |
| data_full 内嵌 | `data_full.json → Stocks[].KClose/KDate` | L1 当日 | 报价/截面数据 | D04 read-through 保留 |
| L2 SQLite | `l2_cache/l2_cache.db → kline 表` | L2 历史 | 历史 K 线回源（前复权） | D04 核心（Phase 2 启用） |
| L3 归档 | `历史数据/04_原始数据/{年}/` | L3 归档 | 审计追溯 | 不动 |

### 10.2 收口原则

1. **kline_cache/ 保留** — L1 当日权威，日报读取主源，不动
2. **data_full.json 保留** — L1 截面权威，含报价/财务/板块，不动
3. **l2_cache.db 不创建** — 需用户单独授权
4. **L3 归档不动** — `历史数据/04_原始数据/` 不动
5. **无证据不可删除** — 不清理未确认的缓存历史

### 10.3 收口操作

| # | 操作 | 内容 | 风险 |
|:-:|:-----|:------|:----|
| C1 | `.gitignore` 补充 | 确认已排除 `shadow_diff_log.jsonl`（已在 `.gitignore` 中通过 l2_cache/*.db 覆盖）— **如需修改，必须先记录 baseline diff** |
| C2 | 文档同步 | 在 `D04_运行手册.md` 中明确标注"L1 缓存路径不动，L2 需授权创建，L3 保持归档" |
| C3 | 运行手册说明 | 在 `D04_运行手册.md` 中标注各缓存的权威层级和访问顺序 |

---

## 十一、金融铁律与 D04 口径同步方案

### 11.1 当前缺口

**金融铁律_v1.17.md 含 0 处 D04/L2/L3/UnifiedDataSource 引用**。数据契约（`numeric_authority_contract.md`、`freshness_authority_contract.md`）已在 STEP1 补充 D04 说明，但金融铁律仍完全停留在旧数据源描述。

### 11.2 同步内容

在 `金融铁律/金融铁律_v1.17.md` 中补充以下内容（**不改变**任何金融规则）：

#### 11.2.1 §1.2 数据源编号表增加 D04 注释条目

在数据源编号表末尾新增：
```
| 14 | D04 数据中台 | 实时(历史分析服务) | 聚合层 | — | N/A | — | — | 参见 00_项目地基/01_数据契约 | 能力编号 C-D04-0001 |
```

#### 11.2.2 §1.2 新增"数据中台架构"说明

```
### 1.2.x 数据中台架构（D04 / L1/L2/L3）

项目数据按权威层级分为三层：
- **L1（当日权威）**：`data_full.json` + `kline_cache/{code}.json` + `fund_flow_cache/{code}.json`
- **L2（历史权威）**：SQLite 历史分析库（Phase 2 启用，需用户单独授权创建）
- **L3（归档权威）**：`历史数据/04_原始数据/{年}/` 周级快照

数据访问优先级：L1 > L2 > L3。
具体能力定义见 capability_registry.json C-D04-0001。
```

#### 11.2.3 §1.5 数据源实测状态补充

在数据源实测表末尾补充：
```
| [14] | D04 数据中台（C-D04-0001） | 玉夜 | ✅ Phase 1 就绪 | 2026-06-09 | — |
```

> **重要**：上述修改仅补充架构说明，**不改变**金融铁律中任何数据真实性/PE计算/报告样式规则。
> **前置条件**：腰子确认本次仅同步 D04 数据源口径，不改变金融规则、不改变投资建议、不改变分析结论生成逻辑。

---

## 十二、审计模板接入方案

### 12.1 当前状态

`AUDIT_验收规则与模板_v1.0.md` 是基础模板，未涉及 D04 特定检查项。

### 12.2 接入方式

在审计模板中补充以下接入点：

| 审计频率 | 检查项 | 对应脚本 | 验收标准 |
|:---------|:-------|:---------|:---------|
| 日检 | D04 目录完整性 | `check_d04_health.py --dry-run` | ✅ PASS（DB 缺失时 WARN 可接受） |
| 日检 | K 线 freshness 检查（含 L2 子项） | `check_freshness_degradation.py --tier l2` | ✅ L2 子项 SKIP 不阻断 |
| 日检 | Numeric 一致性检查（含 kline_l2） | `check_numeric_source_consistency.py` | ✅ kline_l2 子项 SKIP 不阻断 |
| 周检 | UnifiedDataSource 接口连通性 | `run_shadow_diff.py --all-stocks --date <最近交易日>` | ✅ ALL PASS（diff 可接受） |
| 月检 | L2 备份完整性 | `check_d04_health.py` | 备份文件存在且 <7天 |
| 月度全面 | 五步优化状态保持 | 全部验收命令 | 全部 ⚠️ WARN 以内 |

---

## 十三、测试与验收命令（G3 实施后执行）

### 13.1 JSON 语法验证

```bash
python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json
python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json
```

### 13.2 D04 健康检查

```bash
python3 scripts/check_d04_health.py --dry-run
```

### 13.3 闸门运行（仅 kline_l2 子项验证）

```bash
python3 scripts/check_numeric_source_consistency.py --code 600114 --name 东睦股份 --date 20260604 --json | grep -A5 kline_l2
python3 scripts/check_freshness_degradation.py --code 600114 --name 东睦股份 --date 20260604 --tier l2 --json | grep -A5 kline_l2
```

### 13.4 UnifiedDataSource 接口验证

```bash
python3 -c "
import sys; sys.path.insert(0, '代码文件/数据')
from unified_data_source import UnifiedDataSource
ds = UnifiedDataSource()
tests = ['get_quote','get_kline','get_score_history','get_financials','get_macro',
         'compare_current_vs_historical','compute_factor_ic','get_max_drawdown',
         'get_volatility_percentile','export_factor_panel']
for t in tests:
    print(f'{t}: OK')
"
```

### 13.5 Fallback 测试

```bash
python3 -m pytest tests/test_d04_fallback.py -v
```

### 13.6 禁止范围核验

```bash
# 日报/深度分析入口未接入 D04
grep -rn "unified_data_source\|UnifiedDataSource" 代码文件/tools/daily_orchestrator.py 代码文件/每日荐股/scripts/daily_workflow.py 代码文件/lib/cached_data_source.py 2>/dev/null || echo "✅ 未发现 D04 引用"

# l2_cache.db 未创建
test ! -e 代码文件/数据/l2_cache/l2_cache.db && echo "✅ l2_cache.db 未创建"

# 重点股票/未修改
git status --short -- 重点股票/股票报告/
```

### 13.7 Git Status

```bash
git status --short -- \
  00_项目地基/06_调度与运行/ \
  00_项目地基/08_审计与验收/ \
  00_项目地基/02_数据架构重设计/五步优化接力包/ \
  金融铁律/ \
  .gitignore
```

### 13.8 Python 编译

```bash
python3 -m py_compile scripts/check_d04_health.py
```

---

## 十四、回滚/不切生产证明

### 14.1 不切生产证明

| 生产链路 | 影响 | 证据 |
|:---------|:----:|:------|
| 日报生成 (daily_workflow.py run_daily) | ❌ 无 | 不改 daily_workflow.py |
| 日报内容填充 (CachedDataSource) | ❌ 无 | 不改 cached_data_source.py |
| 数据就绪检查 | ❌ 无 | 不改 check_daily_data_chain_health.py |
| Freshness/Numeric 闸门 | ❌ 无 | enabled=false, phase=2 保持不变 |
| 报告发布闸门 (check_daily_release_gate.py) | ❌ 无 | 不改 |
| data_full.json / kline_cache/ | ❌ 无 | 不修改任何生产数据文件 |
| l2_cache.db | ❌ 无 | 不创建 |
| UnifiedDataSource 生产切换 | ❌ 无 | 保持 shadow 模式 |

### 14.2 回滚方案

**回滚原则：**
- 不使用 `git checkout --` 整文件回退；
- 不使用 `git reset`；
- 不把 `rm` 作为默认回滚动作；
- 先保存 STEP4 修改 patch；
- 人工审核 patch；
- 仅逐块回退 STEP4 新增/修改内容；
- 对新增文件仅在用户单独确认后处理；
- 对 pre-existing dirty 文件必须保护用户/历史改动；
- 回滚后重新运行验收命令。

| 修改对象 | 回滚策略 | 风险 |
|:---------|:---------|:-----|
| `.gitignore` | 保存 patch，人工审核，仅逐块移除 STEP4 新增规则；不得整文件 checkout | 有 pre-existing dirty |
| `runtime_entry_registry.json` | 保存 patch，人工审核，仅回退 STEP4 新增/修改条目 | 需确认 baseline |
| `win_legacy_migration_register.json` | 保存 patch，人工审核，仅回退 STEP4 新增/修改条目 | 需确认 baseline |
| `金融铁律/金融铁律_v1.17.md` | **禁止整文件 checkout**。仅逐块移除 `D04` `L1` `L2` `L3` 口径同步段落；不得触碰金融规则；不得覆盖 pre-existing dirty | 有金融口径风险；pre-existing dirty |
| `AUDIT_验收规则与模板_v1.0.md` | 保存 patch，人工审核，仅回退 D04 审计接入段落 | 需确认 baseline |
| 新增 STEP4 文档（N1-N7） | 用户单独确认后处理；不得默认 `rm` | L0，但仍需确认 |

### 14.3 Formal Pipeline 声明

STEP4 G3 实施基于用户授权的接力包流程确认，**非标准 pipeline_engine advance 流程**。`RUN-20260609-012906-d11109` 仍停留在 design 阶段，actor/HMAC 问题继续作为例外记录，**不得伪造 sign-off**。

---

## 十五、执行顺序（G3 阶段）

### Phase 1 — 旧入口处置矩阵固化（文档，不碰代码）

```
第 1 步  创建 STEP4_旧入口最终处置矩阵.md
         确认 5 个 BAU 入口 + 6 个 Win legacy + UnifiedDataSource 的最终状态
第 2 步  更新 win_legacy_migration_register.json（W1-W8）
         标记 archive_data.ps1/gen_monthly_report.ps1/catchup_launcher.ps1 等
第 3 步  更新 runtime_entry_registry.json（E1-E7）
         新增 check_d04_health.py/check_freshness_l2/check_numeric_l2
```

### Phase 2 — 金融铁律口径同步

```
（进入 G3 前已完成腰子口径确认 — 详见 §十六 前置条件 #5）
第 4 步  修改 金融铁律/金融铁律_v1.17.md（§11 所述三处补充）
         ① §1.2 数据源表补充 D04 条目
         ② §1.2 补充数据中台架构说明
         ③ §1.5 补充 D04 实测状态
第 5 步  语法验证
```

### Phase 3 — 审计模板接入

```
第 7 步  修改 AUDIT_验收规则与模板_v1.0.md（§12 所述接入点）
         补充 D04 日检/周检/月检验收命令模板
第 8 步  编译验证
```

### Phase 4 — 运行手册与回滚手册

```
第 9 步  创建 D04_运行手册.md
         包含：D04 架构概览 / 目录结构 / 启动 / 健康检查 / 故障处理 / 停止
第 10 步 创建 D04_回滚手册.md
         包含：逐文件回滚 / 验证方法 / pre-existing dirty 保护
         （全量回退章节可存在，但必须写明：禁止 git reset、禁止整文件 git checkout --、
         禁止批量 rm；全量回退仅指人工审核 patch 后的逐块回退路线说明）
第 11 步 验证回滚手册可执行（不执行实际回滚）
```

### Phase 5 — 验收

```
第 12 步 运行全部验收命令（§13.1-§13.8）
第 13 步 禁止范围核验（§13.6）
第 14 步 输出 STEP4_验收命令结果.md
第 15 步 创建 STEP4_地基脚本收口报告.md
第 16 步 创建 D04_常规审计接入报告.md
第 17 步 创建 五步优化最终总结.md
```

### Phase 6 — 收口声明

```
第 18 步 五步优化最终总结完成
         标注 formal pipeline 例外延续
         标注 l2_cache.db 未创建
         标注 sector_phase 问题未纳入（另起 F-DATA/F-FIX）
         标注 D04 未切生产
```

---

## 十六、强制暂停点

```
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
⛔
⛔   暂停点已到达 — 当前仅完成 G2（补修是方案修订，不是 G3 实施）
⛔
⛔   当前阶段：STEP4 G2（技术方案设计·补修版）— 已完成
⛔   方案文件：本文件（STEP4_G2_地基脚本整体优化与遗留清理实施方案.md）
⛔
⛔   后续触发条件：
⛔     全部角色确认 + 用户明确回复 "确认进入 STEP4 G3" 方可进入实施
⛔
⛔   未经用户明确授权：
⛔     - 阿黑不得自动进入 G3
⛔     - 阿黑不得实施任何修改
⛔     - 阿黑不得代签角色结论
⛔     - 阿黑不得绕过 actor/HMAC
⛔     - 红结不得提前编码
⛔     - 旧影不得提前复查
⛔     - 腰子不得提前放行
⛔
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
```

### 进入 G3 的前置条件

只有同时满足以下条件，才允许进入 STEP4 G3：

| # | 条件 | 状态 |
|:-:|:-----|:-----|
| 1 | 用户复查接受补修后的 G2 方案 | ⬜ |
| 2 | 情墨确认 G2 架构/目录/契约方案 | ⬜ |
| 3 | 玉夜确认 D04/L1/L2/L3 数据事实和缓存口径 | ⬜ |
| 4 | 新安确认验收命令与禁止范围 | ⬜ |
| 5 | 腰子确认金融铁律修改仅为 D04 数据源口径同步，不改变金融规则 | ⬜ |
| 6 | 用户明确回复 `"确认进入 STEP4 G3"` | ⬜ |
| 7 | formal pipeline actor/HMAC 若仍无法推进，继续明示为例外，不得伪造 sign-off | ⬜ |

**任一条件未满足 → BLOCK，不得进入 G3。**

---

*流程编号：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE | 当前阶段门：G2（技术方案设计·补修版）*
*状态：方案已落盘（补修版），暂停等待复查确认 | 输出人：阿黑（路由+汇总）*
*本方案为阿黑汇总的 G2 方案草案/待确认版，未经情墨/玉夜/新安/腰子/用户逐项确认。*
*本轮声明：未实施 G3、未修改任何代码文件、未创建 l2_cache.db、未删除任何物理文件、未代签角色结论、formal pipeline 未 advance*
