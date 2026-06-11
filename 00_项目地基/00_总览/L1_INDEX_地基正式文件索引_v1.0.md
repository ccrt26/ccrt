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
| D04 | 数据中台与历史分析服务 | 已注册 `C-D04-0001` |
| D05 | 证据抽取 | 已注册最小能力 `C-D05-0001` |
| D06 | 信号与特征计算 | 已注册最小能力 `C-D06-0001` |
| D07 | 统一解读 | 已注册 `C-D07-0001`；依赖 D01/D03/D05/D06；规则引用 `R-FIN-0001`,`R-ROL-0002` |
| D08 | 风控/交易解释辅助 | 暂未注册最小能力，按后续任务补齐 |
| D09 | 场景编排 | 当前以 `L1_CAP_能力场景与规则接入_v1.0.md` 管理，不作为单一业务场景 |
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
| 过程归档 | 已被最终收口文件覆盖的过程方案、审计放行单、旧设计稿移入 `99_归档/` |
| 二次归档 | 2026-06-10 已将知识进化 G4/G5/G6、运行化 G1G2/G2/G3、D04 收口报告移入 `99_归档/` |
| 冷归档全文 | 历史阶段报告、旧验收记录、被整合的旧协议全文放入 `08_审计与验收/archive/fulltext/` |
| 可删除热区旧文件 | 已被热文件承接且全文已进冷归档的旧 md，从根目录删除 |
| 不得删除 | JSON 结构化资产、数据契约、调度契约、后评估流程、迁移计划索引 |
| 不得常规读取 | 冷归档全文只按 `L2_INDEX_审计验收归档索引_v1.0.md` 点名追溯；`99_归档/` 仅用于审计追溯 |

## 3. 目录结构

| 子目录 | 用途 |
|:-------|:------|
| `00_总览/` | 地基索引（本文件 L1_INDEX）、启动入口（L0_INDEX_START_HERE）、完成态说明（L1_STATE） |
| `01_数据契约/` | 7 份 L2_CONTRACT 契约 |
| `02_权威注册表/` | JSON 注册表（capability/rule/source/baseline 等） |
| `03_报告对象/` | 报告类型 schema、字段映射 |
| `04_一致性闸门/` | 闸门定义、映射、policy JSON |
| `05_流程与角色/` | L1_FLOW / L1_ROLE / L1_TASK / L1_CAP |
| `06_后评估闭环/` | L2_RUNBOOK 后评估流程定义 |
| `06_调度与运行/` | L2_RUNBOOK/L2_CONTRACT 运行、cutover、调度 |
| `08_审计与验收/` | L2_AUDIT 文件、L2_INDEX 索引 |
| `09_迁移计划/` | L2_INDEX 目录治理索引 |
| `99_归档/` | 热区瘦身归档（过程接力包/审计复查与放行/旧设计稿），不参与日常路由 |

> **99_归档 说明**：本轮 Markdown 热区瘦身（2026-06-09，F-RUNBOOK + F-FIX + F-GATE）将已由最终收口文件覆盖的过程方案、审计放行单、旧设计稿移入 `99_归档/`。归档追溯入口：`99_归档/README_归档索引.md` 和 `99_归档/DELETE_MANIFEST_20260609.md`。日常启动不得读取 `99_归档`，该目录仅用于审计追溯和争议复查。

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
| 基线权威契约 | `01_数据契约/L2_CONTRACT_baseline_authority_v1.0.md` |
| 数值权威契约 | `01_数据契约/L2_CONTRACT_numeric_authority_v1.0.md` |
| 日期新鲜度契约 | `01_数据契约/L2_CONTRACT_freshness_authority_v1.0.md` |
| MD/sidecar 权威契约 | `01_数据契约/L2_CONTRACT_md_sidecar_authority_v1.0.md` |
| 报告权威口径契约 | `01_数据契约/L2_CONTRACT_report_authority_lineage_v1.0.md` |
| canonical cutover 契约 | `01_数据契约/L2_CONTRACT_canonical_cutover_v1.0.md` |
| canonical 报告契约 | `01_数据契约/L2_CONTRACT_canonical_report_v1.0.md` |
| 调度权威契约 | `06_调度与运行/L2_CONTRACT_schedule_authority_v1.0.md` |

## 6. 一致性闸门清单

| 闸门 | 路径 |
|:-----|:------|
| Baseline 权威 | `04_一致性闸门/stage_acceptance_policy.json` + `scripts/check_baseline_authority.py` |
| 数值来源一致性 | `04_一致性闸门/numeric_source_consistency.schema.json` + `numeric_field_mapping.json` |
| 日期新鲜度 | `04_一致性闸门/freshness_rules.json` + `freshness_degradation.schema.json` |
| MD/sidecar 一致性 | `04_一致性闸门/md_sidecar_consistency.schema.json` + `md_sidecar_field_mapping.json` |
| canonical 总闸门 | `04_一致性闸门/canonical_pipeline_gate.schema.json` |

## 7. Markdown 读取分级与命名规范

### 7.1 读取分级

| 级别 | 定义 | 读取规则 |
|:----:|:-----|:---------|
| L0 | 启动必读 | 任何角色启动只读 `L0_INDEX_START_HERE_地基启动索引_v1.0.md` |
| L1 | 任务路由常用 | 按任务类型最小读取，不得全部默认读取 |
| L2 | 权威契约/运行手册/审计模板 | 仅任务需要时读取，不作为启动必读 |
| L3 | 归档追溯 | 默认不读，只在审计追溯/争议复查/历史还原时点名读取 |

### 7.2 分级文件清单

**L0：启动必读**
| 文件 | 路径 |
|:-----|:-----|
| L0_INDEX_START_HERE_地基启动索引_v1.0.md | `00_总览/L0_INDEX_START_HERE_地基启动索引_v1.0.md` |

**L1：任务路由常用**
| 文件 | 路径 |
|:-----|:-----|
| L1_INDEX_地基正式文件索引_v1.0.md（本文件） | `00_总览/L1_INDEX_地基正式文件索引_v1.0.md` |
| L1_STATE_地基完成态与后续开门规则_v1.0.md | `00_总览/L1_STATE_地基完成态与后续开门规则_v1.0.md` |
| L1_FLOW_流程路由与阶段门_v1.0.md | `05_流程与角色/L1_FLOW_流程路由与阶段门_v1.0.md` |
| L1_ROLE_角色唤醒与输出规范_v1.0.md | `05_流程与角色/L1_ROLE_角色唤醒与输出规范_v1.0.md` |
| L1_TASK_阶段派单与执行模板_v1.0.md | `05_流程与角色/L1_TASK_阶段派单与执行模板_v1.0.md` |
| L1_CAP_能力场景与规则接入_v1.0.md | `05_流程与角色/L1_CAP_能力场景与规则接入_v1.0.md` |

**L2：权威契约/运行手册/审计模板**
| 文件或目录 | 范围 | 读取条件 |
|:-----------|:-----|:----------|
| `01_数据契约/*.md` | 7 份 L2_CONTRACT 契约 | 数据链路/变更设计时读取 |
| `02_数据架构重设计/五步优化接力包/` | D04 L2_CONTRACT/L2_RUNBOOK/L2_AUDIT 与历史索引 | D04 运维时读取；L2_REPORT/L2_RELEASE 已归档，只审计追溯读取 |
| `06_调度与运行/*` | L2_RUNBOOK/L2_CONTRACT | 调度运维时读取 |
| `06_后评估闭环/*` | L2_RUNBOOK 后评估流程定义 | 后评估任务时读取 |
| `08_审计与验收/` | L2_AUDIT 文件、L2_INDEX 索引 | 审计任务时读取；G4/G5/G6 过程件已归档 |
| `09_迁移计划/` | L2_INDEX/L2_RUNBOOK 文件 | 迁移任务时读取；G1G2/G2/G3 过程方案已归档 |

**L3：归档追溯**
| 目录 | 读取规则 |
|:-----|:----------|
| `99_归档/` | 默认不读，只在审计追溯时点名读取 |
| `08_审计与验收/archive/fulltext/` | 默认不读，只在历史回溯时通过 INDEX 点名追溯 |

### 7.3 命名规范

后续新增 Markdown 文件应采用统一格式：

```
读取级别_类型_主题_v版本.md
```

**类型枚举：**
`INDEX` / `STATE` / `FLOW` / `ROLE` / `TASK` / `CAP` / `CONTRACT` / `RUNBOOK` / `AUDIT` / `REPORT` / `RELEASE` / `ARCHIVE` / `MANIFEST`

**示例（已落地）：**
| 旧名 | 新名 |
|:-----|:------|
| START_HERE_地基启动索引.md | `L0_INDEX_START_HERE_地基启动索引_v1.0.md` |
| FLOW_流程路由与阶段门_v1.0.md | `L1_FLOW_流程路由与阶段门_v1.0.md` |
| numeric_authority_contract.md | `L2_CONTRACT_numeric_authority_v1.0.md` |

---

*本文件不包含阶段状态信息；阶段状态和完成态见 `L1_STATE_地基完成态与后续开门规则_v1.0.md`。*
