# 动词合规化 Phase 2 — 回归测试

**日期**: 2026-05-27  
**执行者**: 新安  
**流水线**: pipeline_20260527_verb_compliance_phase2  

---

## 回归范围

根据变更影响分析确定的 R01-R13 核心回归检查点，本次变更仅涉及函数重命名（无逻辑变更），回归范围聚焦于调用链路完整性。

---

## R01: 每日荐股评分链路

| 检查点 | 状态 |
|:-------|:----:|
| `run_daily_eval.ps1` 正确加载 `core.ps1`（点源） | PASS |
| `run_daily_eval.ps1` 正确加载 `technical.ps1`（点源） | PASS |
| `run_daily_eval.ps1` 中 Measure-ATR 调用正确 | PASS |
| Calc-ATR 包装器可用 | PASS |

## R02: 重点股票分析链路

| 检查点 | 状态 |
|:-------|:----:|
| `run_keystock_analysis.ps1` 中所有 Calc-* → Measure-* 替换完成 | PASS |
| 8处 replace_all 覆盖所有技术指标调用 | PASS |

## R03: 数据缓存链路

| 检查点 | 状态 |
|:-------|:----:|
| `core.ps1` 中 Export-DataCache 实现完整 | PASS |
| `core.ps1` 中 Import-DataCache 实现完整 | PASS |
| Save-DataCache 包装器委托给 Export-DataCache | PASS |
| Load-DataCache 包装器委托给 Import-DataCache | PASS |
| 所有模块(biying/external/financial/fundflow/quote/sector)中调用已更新 | PASS |

## R04: 技术指标链路

| 检查点 | 状态 |
|:-------|:----:|
| `technical.ps1` 中 7个 Measure-* 函数实现完整 | PASS |
| 7个 Calc-* 包装器委托正确 | PASS |
| `test.ps1` 中 4个 Calc-* → Measure-* 替换完成 | PASS |
| `test.ps1` Export-ModuleMember 更新为 Measure-* | PASS |

## R05: 信鸽采集链路

| 检查点 | 状态 |
|:-------|:----:|
| `pigeon_collector.ps1` 移除 -DisableNameChecking | PASS |
| legacy.psm1 加载不再输出动词警告 | PASS |

## R06: legacy.psm1 模块导出

| 检查点 | 状态 |
|:-------|:----:|
| Export-ModuleMember 仅列出标准动词函数 | PASS |
| Calc-*/Save-*/Load-* 不对外导出 | PASS |
| 内部包装器仍可用 | PASS |

---

## 未回归项（低风险）

| 项目 | 原因 |
|:-----|:-----|
| `legacy.ps1` 中旧动词调用 | 死文件，未被任何脚本引用 |

---

## 回归结论

**所有活跃调用链路验证通过。无功能回归。**

---

pipeline_stage: complete
verified_by: 新安
verified_at: 2026-05-27
