# 动词合规化 Phase 2 — 灰度部署记录

**日期**: 2026-05-27  
**执行者**: 红枫  
**流水线**: pipeline_20260527_verb_compliance_phase2  

---

## 部署策略

本次变更采用**原地替换+包装器兜底**策略，无需灰度切换。所有变更在代码层面完成：

- **新函数名** (Measure-*, Export-*, Import-*): 直接使用在调用方
- **包装器** (Calc-*, Save-*, Load-*): 保留在定义文件中，确保向后兼容

## 部署清单

| 步骤 | 操作 | 状态 |
|:----:|:-----|:----:|
| 1 | 修改 `core.ps1` — Export/Import实现 + Save/Load包装器 | 完成 |
| 2 | 修改 `technical.ps1` — Measure-*实现 + Calc-*包装器 | 完成 |
| 3 | 修改 `legacy.psm1` — 全部9个函数重命名+包装器+Export-ModuleMember | 完成 |
| 4 | 修改 8个调用方模块 (replace_all) | 完成 |
| 5 | 修改 `run_daily_eval.ps1` | 完成 |
| 6 | 修改 `run_keystock_analysis.ps1` | 完成 |
| 7 | 修改 `pigeon_collector.ps1` — 移除 -DisableNameChecking | 完成 |
| 8 | 验证报告生成 (Stage ④) | 完成 |

## 部署方式

**直接部署** — 无灰度窗口。理由：
- 包装器确保旧调用路径仍然有效
- 所有变更为纯函数名替换，无逻辑变更
- 包装器输出与原名函数完全等价

## 验证方式

- [x] 模块加载无警告
- [x] 包装器功能等价
- [x] 调用链路完整
- [x] 红线审查通过

---

pipeline_stage: complete
deployed_by: 红枫
deployed_at: 2026-05-27
