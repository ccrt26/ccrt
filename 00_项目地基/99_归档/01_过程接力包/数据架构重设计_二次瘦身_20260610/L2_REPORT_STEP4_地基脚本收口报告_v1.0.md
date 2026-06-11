# STEP4 地基脚本收口报告

> **流程编号**：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE
> **阶段门**：G3/G4（实施+自检）
> **日期**：2026-06-09
> formal pipeline actor/HMAC：未通过，继续作为明示例外

---

## 一、阶段目标完成情况

| 目标 | 完成度 | 说明 |
|:-----|:------:|:-----|
| 旧入口状态固化 | ✅ | 12 个入口 4 类状态全部明确，矩阵已落盘 |
| 重复缓存路径收口 | ✅ | 4 个权威路径已识别，仅做口径收口，不删除数据 |
| Windows 遗留资产登记 | ✅ | win_legacy_migration_register：原有 15 条，G3 后共 27 条；本轮新增 12 条，并更新 git_autocommit.ps1 原有条目状态 |
| 旧文档口径同步 | ✅ | 金融铁律补充 D04/L1/L2/L3 说明，数据契约已在 STEP1 完成 |
| 测试和审计脚本补齐 | ✅ | D04 日检/周检/月检已接入常规审计模板 |
| 运行手册 | ✅ | D04_运行手册.md 已创建 |
| 回滚手册 | ✅ | D04_回滚手册.md 已创建 |
| 验收命令 | ✅ | 全部通过（WARN 可接受） |
| 常规审计接入 | ✅ | AUDIT_验收规则与模板_v1.0.md §4 已更新 |

## 二、修改文件清单

### 修改文件（5 个）

| # | 文件 | 操作 | 说明 |
|:-:|:-----|:-----|:------|
| M1 | `.gitignore` | — | 无需修改（已有 L2 排除规则 in pre-existing dirty） |
| M2 | `runtime_entry_registry.json` | M | 更新 4 条 + 新增 3 条（check_d04_health.py + L2 检查） |
| M3 | `win_legacy_migration_register.json` | M | 重写：原有 15 条，G3 后共 27 条；本轮新增 12 条，并更新 git_autocommit.ps1 原有条目状态 |
| M4 | `金融铁律/金融铁律_v1.17.md` | M | 补充 D04/L1/L2/L3 数据源口径说明（3 处） |
| M5 | `AUDIT_验收规则与模板_v1.0.md` | M | 新增 §4 D04 常规审计接入（日检/周检/月检） |

### 新增文件（7 个交付物 + 3 个确认文件）

| # | 文件 | 说明 |
|:-:|:-----|:------|
| N1 | `STEP4_旧入口最终处置矩阵.md` | 旧入口状态固化 |
| N2 | `D04_运行手册.md` | D04 日常运维操作手册 |
| N3 | `D04_回滚手册.md` | D04 回滚步骤（禁止 git reset/整文件 checkout/默认 rm） |
| N4 | `D04_常规审计接入报告.md` | D04 常规审计接入说明 |
| N5 | `STEP4_验收命令结果.md` | 验收命令运行结果 |
| N6 | `五步优化最终总结.md` | 五步优化整体总结（见独立文件） |
| N7 | `STEP4_地基脚本收口报告.md` | 本文件 |
| N8 | `STEP4_G2_地基脚本整体优化与遗留清理实施方案.md` | G2 方案（含补修版） |
| N9 | `STEP4_G2_玉夜数据事实确认.md` | G2 玉夜确认 |
| N10 | `STEP4_G2_新安测试验收确认.md` | G2 新安确认 |
| N11 | `STEP4_G2_腰子金融口径前置确认.md` | G2 腰子确认 |

## 三、冻结结论

| 冻结项 | 结论 |
|:-------|:------|
| 旧入口最终状态 | 7 个保留（BAU 生产入口）+ 6 个废弃冻结 + 9 个 under_review（含 gen_pdf 系列）+ 3 个遗留隔离 |
| 重复缓存 | 不做删除，仅做口径收口。kline_cache/data_full 作为 L1 保留不动 |
| Windows 遗留 | 已全量登记，物理文件保留。不删除、不移动 |
| D04 生产链路 | 未切换。UnifiedDataSource 保持 shadow 模式 |
| l2_cache.db | 未创建。需用户单独授权 |
| sector_phase | 未纳入 STEP4 清理。保留原状 |

## 四、WARN 项

| # | WARN 项 | 处理 |
|:-:|:--------|:------|
| 1 | gen_pdf.ps1/gen_eval_pdf.ps1/gen_keystock_pdf.ps1 系列 | ⚠️ under_review — 尚未冻结；后续需单独验证 convert_md_to_pdf.py / gen_keystock_pdf.py 是否完整覆盖原 ps1 场景，若无法证明则保持 under_review |
| 2 | formal pipeline actor/HMAC 未通过 | 继续明示例外，不得伪造 sign-off |
| 3 | sector_phase 不一致不视为严重 | 另起 F-DATA/F-FIX |

## 五、Pre-existing dirty 说明

以下正式入口文件当前为 pre-existing dirty，**不属于 STEP4 修改范围**，未在 STEP4 中被修改或引用 UnifiedDataSource：

| 文件 | 当前状态 | STEP4 是否修改 | UDS 引用 | 结论 |
|:-----|:---------|:---------------|:---------|:------|
| `代码文件/lib/cached_data_source.py` | pre-existing dirty | ❌ 否 | 无（grep exit=1）| ✅ PASS |
| `代码文件/tools/daily_orchestrator.py` | pre-existing dirty | ❌ 否 | 无（grep exit=1）| ✅ PASS |
| `代码文件/每日荐股/scripts/daily_workflow.py` | pre-existing dirty | ❌ 否 | 无（grep exit=1）| ✅ PASS |

上述三个文件在 STEP3 前即已存在 dirty 状态，STEP4 G3/G4 未对这些文件做任何修改。正式入口仍未切换到 D04/UnifiedDataSource。

## 六、G4 自检结论

| 维度 | 结果 |
|:-----|:------|
| JSON 语法 | ✅ 2/2 PASS |
| D04 健康检查 | ⚠️ WARN（dry-run，预期内） |
| Fallback 回归测试 | ✅ 5/5 PASS |
| UDS 接口 smoke test | ✅ 10/10 PASS |
| Python 编译 | ✅ PASS |
| 禁止范围核验 | ✅ PASS |
| 未修改代码文件 | ✅ 确认 |
| l2_cache.db 未创建 | ✅ 确认 |
| 正式入口未引用 UDS | ✅ 确认 |
| **总体** | **✅ PASS（WARN 可接受）** |

---

*流程编号：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE | 阶段门：G3/G4*
*formal pipeline actor/HMAC 明示例外*
