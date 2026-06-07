# INDEX：地基正式文件索引 v1.0

> **定位：** 地基正式文件总索引，任务需要时读取。不是启动必读。
> **覆盖：** 四层架构说明、目录结构、注册表索引、数据契约索引、闸门索引
> **维护人：** 阿黑

---

## 1. 地基四层架构（收敛版）

```
治理地基（规则约束 + 权限边界 + 阶段门）
    ↓ 规则约束
生产地基（12 类原子能力域：
  D01-D04 数据与治理
  D05-D08 分析与解释，其中 D07 = 统一解读原子能力 C-D07-0001
  D09-D12 编排输出）
    ↓ 能力供给（标准接口，不得绕过）
场景编排（重点股票分析〔深度分析/日报/临时分析〕/每日荐股/保护机制/模拟交易）
    ↓ 产出标准化产物
产物与闭环（CanonicalReport | EvalHook | AuditRecord → 反馈回路 → 治理地基）
```

**核心约束：** 统一解读是 D07 原子能力，不是业务场景；场景不得绕过标准能力接口；产物必须有标准 schema；治理地基通过规则资产/权限/阶段门/审计约束生产地基。

## 1.1 12 类原子能力域

| 域 | 定位 | 当前注册/治理状态 |
|:---|:-----|:------------------|
| D01 | 数据采集与快照输入 | 已注册最小能力 `C-D01-0001` |
| D02 | 数据源/外部信息接入 | 暂未注册最小能力，按后续任务补齐 |
| D03 | 数据治理与质量检查 | 已注册最小能力 `C-D03-0001` |
| D04 | 缓存/权威源沉淀 | 暂未注册最小能力，按后续任务补齐 |
| D05 | 证据抽取 | 已注册最小能力 `C-D05-0001` |
| D06 | 信号与特征计算 | 已注册最小能力 `C-D06-0001` |
| D07 | 统一解读 | 已注册 `C-D07-0001`；依赖 D01/D03/D05/D06；规则引用 `R-FIN-0001`,`R-ROL-0002` |
| D08 | 风控/交易解释辅助 | 暂未注册最小能力，按后续任务补齐 |
| D09 | 场景编排 | 当前以 `CAP_能力场景与规则接入_v1.0.md` 管理，不作为单一业务场景 |
| D10 | 报告/产物输出 | 由报告对象 schema 与 canonical 契约约束 |
| D11 | 后评估钩子 | 由 `06_后评估闭环/` 与 EvalHook 约束 |
| D12 | 知识反馈/流水线闭环 | 后续第9~第10阶段继续治理 |

**保留规则：** D01-D12 是能力域；C-Dxx-0001 是已注册能力条目；业务场景只能调用能力，不得把场景本身伪装成能力。

## 2. 四类资产

| 类型 | 定义 | 存放位置 |
|:-----|:-----|:---------|
| 原子能力 | 可复用能力定义 | `02_权威注册表/capability_registry.json` |
| 规则资产 | rule_id 化的规则约束 | `02_权威注册表/rule_asset_registry.json` |
| 执行载体 | 把能力和规则跑起来 | pipeline_engine / cron / 闸门脚本 |
| 产物对象 | 能力执行后的标准化结果 | 标准产物目录 |

**红线：** 规则资产≠能力 | 原子能力≠脚本 | 执行载体≠规则源 | 产物对象≠规则源

## 2.1 热文件/冷归档取舍

| 类型 | 处理 |
|:-----|:-----|
| 热文件 | 只保留启动、索引、完成态、流程、角色、派单、能力场景、审计规则、总验收 |
| 冷归档全文 | 历史阶段报告、旧验收记录、被整合的旧协议全文放入 `08_审计与验收/archive/fulltext/` |
| 可删除热区旧文件 | 已被热文件承接且全文已进冷归档的旧 md，从根目录删除 |
| 不得删除 | JSON 结构化资产、数据契约、调度契约、后评估流程、迁移计划索引 |
| 不得常规读取 | 冷归档全文只按 `INDEX_审计验收归档索引_v1.0.md` 点名追溯 |

## 3. 目录结构

| 子目录 | 用途 |
|:-------|:------|
| `00_总览/` | 地基索引（本文件）、启动入口（START_HERE）、完成态说明（STATE） |
| `01_数据契约/` | Schema 注册表、接口契约定义 |
| `02_权威注册表/` | JSON 注册表（注册表、注册表、能力、规则等） |
| `03_报告对象/` | 报告类型 schema、字段映射 |
| `04_一致性闸门/` | 闸门定义、映射、policy JSON |
| `05_流程与角色/` | FLOW/ROLE/TASK/CAP 四文件 |
| `06_后评估闭环/` | 后评估流程定义 |
| `06_调度与运行/` | 运行注册、runbook、调度契约 |
| `08_审计与验收/` | AUDIT 文件、INDEX 索引 |
| `09_迁移计划/` | 目录治理索引 |

## 4. 结构化资产清单（JSON 不删除）

以下 JSON 是结构化权威资产，不按 md 规则删除：

| 资产 | 路径 | 条目数 |
|:-----|:-----|:------|
| baseline_registry | `02_权威注册表/baseline_registry.json` | 68 条基线 |
| capability_registry | `02_权威注册表/capability_registry.json` | 5 条能力 |
| rule_asset_registry | `02_权威注册表/rule_asset_registry.json` | 6 条规则 |
| source_registry | `02_权威注册表/source_registry.json` | 骨架 |
| numeric_field_registry | `02_权威注册表/numeric_field_registry.json` | 12 字段 |
| freshness_field_registry | `02_权威注册表/freshness_field_registry.json` | — |
| md_sidecar_field_registry | `02_权威注册表/md_sidecar_field_registry.json` | — |
| baseline_authority_policy | `02_权威注册表/baseline_authority_policy.json` | — |
| report_authority_source_registry | `02_权威注册表/report_authority_source_registry.json` | — |
| runtime_entry_registry | `06_调度与运行/runtime_entry_registry.json` | — |
| win_legacy_migration_register | `06_调度与运行/win_legacy_migration_register.json` | — |

## 5. 数据契约清单

| 契约 | 路径 |
|:-----|:------|
| baseline 权威契约 | `01_数据契约/baseline_authority_contract.md` |
| 数值权威契约 | `01_数据契约/numeric_authority_contract.md` |
| 日期新鲜度契约 | `01_数据契约/freshness_authority_contract.md` |
| MD/sidecar 权威契约 | `01_数据契约/md_sidecar_authority_contract.md` |
| 报告权威口径契约 | `01_数据契约/report_authority_lineage_contract.md` |
| canonical cutover 契约 | `01_数据契约/canonical_cutover_contract.md` |
| canonical 报告契约 | `01_数据契约/canonical_report_contract.md` |
| 调度权威契约 | `06_调度与运行/schedule_authority_contract.md` |

## 6. 一致性闸门清单

| 闸门 | 路径 |
|:-----|:------|
| Baseline 权威 | `04_一致性闸门/stage_acceptance_policy.json` + `scripts/check_baseline_authority.py` |
| 数值来源一致性 | `04_一致性闸门/numeric_source_consistency.schema.json` + `numeric_field_mapping.json` |
| 日期新鲜度 | `04_一致性闸门/freshness_rules.json` + `freshness_degradation.schema.json` |
| MD/sidecar 一致性 | `04_一致性闸门/md_sidecar_consistency.schema.json` + `md_sidecar_field_mapping.json` |
| canonical 总闸门 | `04_一致性闸门/canonical_pipeline_gate.schema.json` |

---

*本文件不包含阶段状态信息；阶段状态和完成态见 `STATE_地基完成态与后续开门规则_v1.0.md`。*
