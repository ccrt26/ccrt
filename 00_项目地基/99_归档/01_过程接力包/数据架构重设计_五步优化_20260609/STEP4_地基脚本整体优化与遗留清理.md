# STEP4：地基脚本整体优化与遗留清理

> 本步骤只在 STEP0-STEP3 稳定后执行。目标是清理旧入口、重复缓存、遗留脚本和文档残留，避免系统重新分叉。

---

## 新会话启动命令

```text
阿黑，按照标准流程执行：STEP4 地基脚本整体优化与遗留清理。

前置要求：STEP3 已 PASS，UnifiedDataSource 已 shadow 验证且未发现阻断问题。本步骤只做证据化清理和最小重构；禁止删除无法证明无用的脚本，禁止破坏回滚路径。
```

---

## 本步骤目标

完成数据地基收口：

1. 旧入口状态固化：保留、适配、废弃、归档。
2. 重复缓存路径收口。
3. Windows 遗留资产登记或隔离。
4. 旧文档口径同步。
5. 测试和审计脚本补齐。
6. 生成最终运行手册和回滚手册。

---

## 前置检查

必须确认：

1. `STEP3_UnifiedDataSource影子接入报告.md` 存在并 PASS。
2. `STEP3_旧入口适配矩阵.md` 已列出所有旧入口。
3. `STEP3_GoldenDiff或ShadowDiff报告.md` 无 BLOCK。
4. 用户明确允许进入清理阶段。

缺失则 BLOCK。

---

## 必须读取

1. 本文件
2. STEP0-STEP3 全部交付物
3. `.gitignore`
4. `00_项目地基/06_调度与运行/runtime_entry_registry.json`
5. `00_项目地基/06_调度与运行/win_legacy_migration_register.json`
6. `代码文件/每日荐股/scripts/`
7. `代码文件/tools/`
8. `scripts/`
9. `_win32_legacy/`
10. `金融铁律/金融铁律_v1.17.md`
11. `00_项目地基/08_审计与验收/AUDIT_验收规则与模板_v1.0.md`

---

## 允许修改范围

1. `.gitignore`
2. `00_项目地基/06_调度与运行/runtime_entry_registry.json`
3. `00_项目地基/06_调度与运行/win_legacy_migration_register.json`
4. `00_项目地基/08_审计与验收/`
5. `代码文件/每日荐股/scripts/` 中已被 STEP3 证明可收口的文件
6. `代码文件/tools/` 中已被 STEP3 证明可收口的文件
7. `scripts/` 中已被 STEP3 证明可收口的文件
8. 新增运行手册、回滚手册、清理报告
9. `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_*.md`

删除或移动文件必须先列清单并等待用户确认。

---

## 禁止修改范围

1. 禁止无证据删除脚本。
2. 禁止删除回滚路径。
3. 禁止修改正式报告产物。
4. 禁止清理用户未确认的历史数据。
5. 禁止执行 destructive git 命令。

---

## 必须完成任务

1. 生成 `旧入口最终处置矩阵`。
2. 更新 runtime entry registry。
3. 更新 win legacy migration register。
4. 清理或标注重复缓存路径。
5. 更新金融铁律中旧数据源说明，避免和 D04 冲突。
6. 更新审计模板，让 D04 日检/周检/月检进入常规审计。
7. 补齐最终回归测试。
8. 生成 D04 运行手册。
9. 生成 D04 回滚手册。
10. 生成最终验收报告。

---

## 验收命令

至少执行：

```bash
python3 -m json.tool 00_项目地基/06_调度与运行/runtime_entry_registry.json
python3 -m json.tool 00_项目地基/06_调度与运行/win_legacy_migration_register.json
python3 -m py_compile 代码文件/数据/unified_data_source.py
python3 scripts/check_d04_health.py --dry-run
python3 scripts/check_numeric_source_consistency.py --all --date <最近交易日> --json
python3 scripts/check_freshness_degradation.py --all --date <最近交易日> --json
pytest tests/test_d04_*.py -q
git status --short
```

如果测试环境缺失，必须说明缺失项和替代验证。

---

## 交付物

1. `STEP4_地基脚本收口报告.md`
2. `旧入口最终处置矩阵.md`
3. `D04_运行手册.md`
4. `D04_回滚手册.md`
5. `D04_常规审计接入报告.md`
6. `STEP4_验收命令结果.md`
7. `五步优化最终总结.md`

---

## 通过条件

1. 旧入口状态全部明确。
2. 不再存在相互冲突的权威源说明。
3. D04 进入常规审计。
4. 回滚路径保留。
5. 测试/闸门无 BLOCK。
6. 旧影复查 PASS。
7. 用户确认五步优化完成。

