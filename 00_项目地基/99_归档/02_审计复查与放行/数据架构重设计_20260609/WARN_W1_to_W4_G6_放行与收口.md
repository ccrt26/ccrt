# W1-W4 WARN 收口包 G6 最终放行与收口方案

> **流程编号**：F-DATA + F-FIX + F-REPORT + F-GATE + F-RUNBOOK  
> **当前阶段**：G6 放行  
> **放行对象**：W1-W4 WARN 一步收口包  
> **收口日期**：2026-06-09  

---

## 一、前置确认

1. ✅ G0 路由已完成；
2. ✅ G1/G2 合并确认已完成；
3. ✅ 用户已确认进入 G3；
4. ✅ 红结已完成 G3 一包执行；
5. ✅ G4 自检已完成；
6. ✅ G5 旧影独立复查结论为：建议通过；
7. ✅ 当前进入 G6，仅做最终放行，不再实施任何修改。

## 二、W1 放行结论

**W1 sector_phase 不一致已修复并可放行。**

确认依据：
1. 600114 东睦股份 20260604 sidecar JSON 合法；
2. sidecar `.sector_phase.phase` 已统一为 `"主升调整"`；
3. 600114 东睦股份 20260604 MD 相位相关文本已统一为 `"主升调整"`；
4. MD 中无与本次 sector_phase 修复相关的 `"潜伏期"` 残留；
5. data_scored.json 未修改；
6. 未修改代码；
7. 未扩展到生成链、engine、全量扫描。

**W1 结论：同意放行。**

## 三、W2 放行结论

**W2 l2_cache.db 最小建库已完成并可放行。**

确认依据：
1. l2_cache.db 已创建；
2. 仅为空 schema；
3. 数据行数为 0；
4. 未调用 Tushare/API；
5. 未补历史大数据；
6. 未切生产；
7. D04 health check 为 6 PASS / 1 WARN / 0 BLOCK；
8. WARN 仅为 backup 目录空，符合空 schema 阶段预期；
9. PROD_SWITCH=PASS，生产入口未引用 D04/UnifiedDataSource。

**W2 结论：同意放行。**
备注：该放行只代表 L2 SQLite 空 schema 已落地，不代表 L2 历史数据已实装，不代表 L2 已进入生产运行态。

## 四、W3 放行结论

**W3 gen_pdf 系列旧入口治理已完成并可放行。**

确认依据：
1. build_tools.py 存在且 help 正常；
2. convert_md_to_pdf.py 存在；
3. gen_keystock_pdf.py 存在；
4. gen_pdf.ps1 已从 under_review 更新为 forbidden_when_python_available；
5. gen_eval_pdf.ps1 已从 under_review 更新为 forbidden_when_python_available；
6. gen_keystock_pdf.ps1 已从 under_review 更新为 forbidden_when_python_available；
7. 三个 .ps1 文件均未删除；
8. 本次仅做治理状态收口，不删除旧文件。

**W3 结论：同意放行。**

## 五、W4 放行结论

**W4 formal pipeline actor/HMAC 例外已明示，可作为已知工具链例外放行。**

确认依据：
1. formal pipeline actor/HMAC 未通过；
2. 本收口包不等同于 formal pipeline PASS；
3. 未伪造 sign_off；
4. 未让执行模型冒充项目角色；
5. 后续继续按 CCRT 接力包流程 + 用户授权明示例外执行；
6. formal pipeline actor/HMAC 修复属于工具链问题，不在本收口包内继续处理。

**W4 结论：同意作为"已知例外"放行。**
备注：该放行不是 formal pipeline PASS。

## 六、禁止范围复核

确认本收口包未执行以下行为：

1. ✅ 未修改 data_scored.json；
2. ✅ 未修改 cached_data_source.py；
3. ✅ 未修改 daily_workflow.py；
4. ✅ 未修改日报/深度分析正式入口；
5. ✅ 未切换生产入口；
6. ✅ 未调用外部 API；
7. ✅ 未补历史大数据；
8. ✅ 未删除 ps1；
9. ✅ 未处理 Git/GitHub；
10. ✅ 未 commit / push / PR；
11. ✅ 未扩展生成链、engine、全量扫描；
12. ✅ 未伪造 formal pipeline actor/HMAC；
13. ✅ 未由阿黑代签任何角色结论。

## 七、pre-existing 状态说明

以下状态为本收口包执行前已存在，不计入 W1-W4 新增修改：

1. daily_orchestrator.py — pre-existing dirty
2. check_daily_data_completeness.py — pre-existing dirty
3. unified_data_source.py — pre-existing untracked
4. scripts/build_l2_cache.py — pre-existing untracked
5. l2_cache/ 目录骨架 — 既有未跟踪状态；本次仅在该目录内创建/写入 l2_cache.db 空 schema

## 八、腰子 G6 放行意见

**【腰子 G6 放行】同意放行 W1-W4 WARN 一步收口包。**

**放行边界：**
1. W1 正式收口；
2. W2 仅空 schema 收口，不代表 L2 历史数据运行态完成；
3. W3 旧 PDF 入口治理状态收口，不删除 ps1；
4. W4 formal pipeline actor/HMAC 继续作为明示工具链例外；
5. 本次收口后不得自动继续处理其他问题；
6. 后续任何新问题需另起 CCRT 标准流程。

## 九、用户最终确认

**【用户确认】接受 W1-W4 WARN 收口包 G6 放行。W1-W4 WARN 收口包正式收口。本轮暂停，不自动进入任何新任务。**
