# RENAME MANIFEST — Markdown 热区文件命名分级治理

> 日期：2026-06-09
> 流程：F-RUNBOOK + F-FIX + F-GATE
> 阶段：G3
> 范围：仅热区正式 Markdown 文件同目录 rename
> 禁止：不改 99_归档，不改 archive/fulltext，不改 JSON/脚本/数据

## 原理说明

本轮改名是上一轮"Markdown 读取分级与命名治理"的落地执行——将已定义的
L0/L1/L2/L3 读取级别直接写入文件名，使角色一眼可识别文件启动优先级。
所有重命名为同目录 `mv`，不跨目录移动。

## 改名清单（40 项）

### A. 00_总览/ — L0:1 + L1:2

| 原路径 | 新路径 | 级别 | 类型 |
|:-------|:-------|:----:|:----:|
| `00_总览/START_HERE_地基启动索引.md` | `00_总览/L0_INDEX_START_HERE_地基启动索引_v1.0.md` | L0 | INDEX |
| `00_总览/INDEX_地基正式文件索引_v1.0.md` | `00_总览/L1_INDEX_地基正式文件索引_v1.0.md` | L1 | INDEX |
| `00_总览/STATE_地基完成态与后续开门规则_v1.0.md` | `00_总览/L1_STATE_地基完成态与后续开门规则_v1.0.md` | L1 | STATE |

### B. 05_流程与角色/ — L1:4

| 原路径 | 新路径 | 级别 | 类型 |
|:-------|:-------|:----:|:----:|
| `05_流程与角色/FLOW_流程路由与阶段门_v1.0.md` | `05_流程与角色/L1_FLOW_流程路由与阶段门_v1.0.md` | L1 | FLOW |
| `05_流程与角色/ROLE_角色唤醒与输出规范_v1.0.md` | `05_流程与角色/L1_ROLE_角色唤醒与输出规范_v1.0.md` | L1 | ROLE |
| `05_流程与角色/TASK_阶段派单与执行模板_v1.0.md` | `05_流程与角色/L1_TASK_阶段派单与执行模板_v1.0.md` | L1 | TASK |
| `05_流程与角色/CAP_能力场景与规则接入_v1.0.md` | `05_流程与角色/L1_CAP_能力场景与规则接入_v1.0.md` | L1 | CAP |

### C. 01_数据契约/ — L2 CONTRACT:7

| 原路径 | 新路径 | 级别 | 类型 |
|:-------|:-------|:----:|:----:|
| `01_数据契约/baseline_authority_contract.md` | `01_数据契约/L2_CONTRACT_baseline_authority_v1.0.md` | L2 | CONTRACT |
| `01_数据契约/canonical_cutover_contract.md` | `01_数据契约/L2_CONTRACT_canonical_cutover_v1.0.md` | L2 | CONTRACT |
| `01_数据契约/canonical_report_contract.md` | `01_数据契约/L2_CONTRACT_canonical_report_v1.0.md` | L2 | CONTRACT |
| `01_数据契约/freshness_authority_contract.md` | `01_数据契约/L2_CONTRACT_freshness_authority_v1.0.md` | L2 | CONTRACT |
| `01_数据契约/md_sidecar_authority_contract.md` | `01_数据契约/L2_CONTRACT_md_sidecar_authority_v1.0.md` | L2 | CONTRACT |
| `01_数据契约/numeric_authority_contract.md` | `01_数据契约/L2_CONTRACT_numeric_authority_v1.0.md` | L2 | CONTRACT |
| `01_数据契约/report_authority_lineage_contract.md` | `01_数据契约/L2_CONTRACT_report_authority_lineage_v1.0.md` | L2 | CONTRACT |

### D. 06_后评估闭环/ + 06_调度与运行/ — L2:3

| 原路径 | 新路径 | 级别 | 类型 |
|:-------|:-------|:----:|:----:|
| `06_后评估闭环/后评估流程定义_v1.0.md` | `06_后评估闭环/L2_RUNBOOK_后评估流程定义_v1.0.md` | L2 | RUNBOOK |
| `06_调度与运行/canonical_cutover_runbook.md` | `06_调度与运行/L2_RUNBOOK_canonical_cutover_v1.0.md` | L2 | RUNBOOK |
| `06_调度与运行/schedule_authority_contract.md` | `06_调度与运行/L2_CONTRACT_schedule_authority_v1.0.md` | L2 | CONTRACT |

### E. 08_审计与验收/ 主文件 — L2:3

| 原路径 | 新路径 | 级别 | 类型 |
|:-------|:-------|:----:|:----:|
| `08_审计与验收/AUDIT_地基融合总验收_v1.0.md` | `08_审计与验收/L2_AUDIT_地基融合总验收_v1.0.md` | L2 | AUDIT |
| `08_审计与验收/AUDIT_验收规则与模板_v1.0.md` | `08_审计与验收/L2_AUDIT_验收规则与模板_v1.0.md` | L2 | AUDIT |
| `08_审计与验收/INDEX_审计验收归档索引_v1.0.md` | `08_审计与验收/L2_INDEX_审计验收归档索引_v1.0.md` | L2 | INDEX |

### F. 09_迁移计划/ — L2:7

| 原路径 | 新路径 | 级别 | 类型 |
|:-------|:-------|:----:|:----:|
| `09_迁移计划/目录治理索引.md` | `09_迁移计划/L2_INDEX_目录治理索引_v1.0.md` | L2 | INDEX |
| `09_迁移计划/README_运行化阶段接力索引_v1.0.md` | `09_迁移计划/L2_INDEX_运行化阶段接力索引_v1.0.md` | L2 | INDEX |
| `09_迁移计划/PLAN_地基1.0后运行化总方案_v1.0.md` | `09_迁移计划/L2_RUNBOOK_地基1.0后运行化总方案_v1.0.md` | L2 | RUNBOOK |
| `09_迁移计划/STEP-A_文档与接力包整理_G2方案.md` | `09_迁移计划/L2_REPORT_STEP-A_文档与接力包整理_G2方案_v1.0.md` | L2 | REPORT |
| `09_迁移计划/STEP-B_L2数据实装_G2方案.md` | `09_迁移计划/L2_REPORT_STEP-B_L2数据实装_G2方案_v1.0.md` | L2 | REPORT |
| `09_迁移计划/STEP-C_运行入口Shadow验证_G2方案.md` | `09_迁移计划/L2_REPORT_STEP-C_运行入口Shadow验证_G2方案_v1.0.md` | L2 | REPORT |
| `09_迁移计划/STEP-D_生产入口切换评估_G2方案.md` | `09_迁移计划/L2_REPORT_STEP-D_生产入口切换评估_G2方案_v1.0.md` | L2 | REPORT |

### G. 02_数据架构重设计/五步优化接力包/ 保留文件 — L2:13

| 原路径 | 新路径 | 级别 | 类型 |
|:-------|:-------|:----:|:----:|
| `README_五步优化接力索引.md` | `L2_INDEX_五步优化接力索引_v1.0.md` | L2 | INDEX |
| `D04_权威源决策表.md` | `L2_CONTRACT_D04_权威源决策表_v1.0.md` | L2 | CONTRACT |
| `D04_能力边界冻结表.md` | `L2_CONTRACT_D04_能力边界冻结表_v1.0.md` | L2 | CONTRACT |
| `D04_运行手册.md` | `L2_RUNBOOK_D04_运行手册_v1.0.md` | L2 | RUNBOOK |
| `D04_回滚手册.md` | `L2_RUNBOOK_D04_回滚手册_v1.0.md` | L2 | RUNBOOK |
| `D04_常规审计接入报告.md` | `L2_AUDIT_D04_常规审计接入报告_v1.0.md` | L2 | AUDIT |
| `D04_注册与闸门同步补丁方案.md` | `L2_REPORT_D04_注册与闸门同步补丁方案_v1.0.md` | L2 | REPORT |
| `STEP2_D04数据层建设报告.md` | `L2_REPORT_STEP2_D04数据层建设报告_v1.0.md` | L2 | REPORT |
| `STEP3_G6_收口归档.md` | `L2_RELEASE_STEP3_G6_收口归档_v1.0.md` | L2 | RELEASE |
| `STEP4_地基脚本收口报告.md` | `L2_REPORT_STEP4_地基脚本收口报告_v1.0.md` | L2 | REPORT |
| `STEP4_旧入口最终处置矩阵.md` | `L2_REPORT_STEP4_旧入口最终处置矩阵_v1.0.md` | L2 | REPORT |
| `WARN_W1_to_W4_收口记录.md` | `L2_RELEASE_WARN_W1_to_W4_收口记录_v1.0.md` | L2 | RELEASE |
| `五步优化最终总结.md` | `L2_REPORT_五步优化最终总结_v1.0.md` | L2 | REPORT |

## 文件级别总览

| 前缀 | 含义 | 数量 |
|:-----|:-----|:----:|
| L0_ | 启动必读 | 1 |
| L1_ | 任务路由常用 | 6 |
| L2_ | 权威契约/运行手册/审计模板 | 33 |
| L3_ | 归档追溯（目录级，不改名） | 2 个目录 |

## 兼容策略

1. ✅ **仅 `START_HERE_地基启动索引.md` 保留旧名 redirect**（内容替换为："已迁移，见 L0_INDEX_START_HERE_地基启动索引_v1.0.md"）
2. ❌ 其他旧文件名不保留
3. ✅ 所有热区索引引用已更新为新文件名（7 个索引文件）
4. ✅ 99_归档 和 archive/fulltext 内历史正文允许保留旧名引用，不作为断链

## 受影响索引文件（均已更新）

| 索引文件 | 新路径 |
|:---------|:-------|
| L0_INDEX_START_HERE | `00_总览/L0_INDEX_START_HERE_地基启动索引_v1.0.md` |
| L1_INDEX_地基正式文件索引 | `00_总览/L1_INDEX_地基正式文件索引_v1.0.md` |
| L2_INDEX_五步优化接力索引 | `02_数据架构重设计/五步优化接力包/L2_INDEX_五步优化接力索引_v1.0.md` |
| L2_INDEX_审计验收归档索引 | `08_审计与验收/L2_INDEX_审计验收归档索引_v1.0.md` |
| L2_INDEX_运行化阶段接力索引 | `09_迁移计划/L2_INDEX_运行化阶段接力索引_v1.0.md` |
| L2_INDEX_目录治理索引 | `09_迁移计划/L2_INDEX_目录治理索引_v1.0.md` |
| 99_归档 README | `99_归档/README_归档索引.md` |
