# 第1阶段：Baseline 权威体系接入 — 验收记录

> 验收日期：2026-06-02
> 验收人：阿黑
> 阶段：第1阶段（正式重构第1阶段）

---

## 一、修改/新增文件清单

### 新增（4个）

| # | 文件 | 说明 |
|:-:|:-----|:------|
| 1 | `00_项目地基/01_数据契约/baseline_authority_contract.md` | Baseline 权威契约（10项规则） |
| 2 | `00_项目地基/02_权威注册表/baseline_authority_policy.json` | Baseline 权威策略（机器可读） |
| 3 | `scripts/resolve_current_baseline.py` | 当前有效基线解析器 |
| 4 | `00_项目地基/08_审计与验收/第1阶段_Baseline权威体系接入验收记录.md` | 本验收记录 |

### 修改（4个）

| # | 文件 | 修改内容 |
|:-:|:-----|:---------|
| 5 | `00_项目地基/00_总览/地基重构阶段总账.md` | 更新 P0-C/P0-D/P0-FIX/第1阶段状态 + 下一步顺序 |
| 6 | `重点股票/分析逻辑/日报v3.6_schema.json` | baseline_id 示例改为 `600114_W2026W22`，补充 registry 来源说明 |
| 7 | `重点股票/分析逻辑/日报v3.6_字段字典.md` | baseline_id 数据源改为 `baseline_registry.json`，示例更新 |
| 8 | `重点股票/分析逻辑/重点股票跟踪分析逻辑白皮书_v3.6.md` | baseline §1.2 后补充 5 条 registry 权威规则 |

---

## 二、第1阶段目标

1. ✅ 固化 baseline 权威合同 → `baseline_authority_contract.md`
2. ✅ 明确 baseline_id 唯一来源 → `baseline_registry.json`
3. ✅ 提供可查询当前有效 baseline 的 resolver → `resolve_current_baseline.py`
4. ✅ 修正旧 schema / 字段字典中容易误导的 baseline_id 示例
5. ✅ 更新阶段总账状态

---

## 三、Baseline 权威规则摘要

| 规则 | 内容 |
|:-----|:------|
| **权威源** | `00_项目地基/02_权威注册表/baseline_registry.json` |
| **ID 格式** | `{6位代码}_W{年份}W{周数}`（如 `600114_W2026W22`） |
| **有效期** | `baseline_date <= trade_date <= valid_until` |
| **0 条** | ⛔ BLOCK |
| **1 条** | ✅ PASS |
| **多条** | ⛔ BLOCK |
| **日报生成前必须执行** | `resolve_current_baseline.py` + `check_baseline_authority.py` |
| **禁止来源** | 深度分析正文标题/附录旧 ID/历史日报/人工输入/模板示例 |

---

## 四、Resolver 脚本说明

| 功能 | 命令 |
|:-----|:------|
| 单票查询 | `python3 scripts/resolve_current_baseline.py --code 600114 --name 东睦股份 --date 20260602` |
| JSON 输出 | `... --json` |
| 全池查询 | `... --all --date 20260602` |

输出字段：stock_code, stock_name, trade_date, result, baseline_id, baseline_file, baseline_date, valid_until, status, key_fields(key_support_price/key_pressure_price/stop_loss_price), core_thesis, overall_risk_level

---

## 五、旧口径替换说明

| 文档 | 旧示例 | 新示例 |
|:-----|:-------|:-------|
| 日报v3.6_schema.json | `600114_deep_20260529_v1.4` | `600114_W2026W22` |
| 日报v3.6_字段字典.md | `600114_deep_20260529_v1.4` | `600114_W2026W22` |
| 白皮书 v3.6.md | 无旧示例 | 新增 5 条 registry 规则 |

---

## 六、阶段总账更新说明

| 更新项 | 旧状态 | 新状态 |
|:-------|:------:|:------:|
| P0-C | 待执行 | ✅ 已通过 |
| P0-D | 待执行 | ✅ 已通过 |
| P0-FIX | 不存在 | ✅ 已通过 |
| 第1阶段 | 待执行 | ✅ 本阶段执行中 |
| B-01 问题状态 | 第1阶段待修复 | ✅ P0-FIX 已修复 |
| 下一步 | P0-C | 第2阶段 |
| 更新历史索引 | 缺 P0-C/P0-D/P0-FIX/第1阶段 | 已补充 |

---

## 七、验收命令结果

| 检查项 | 结果 |
|:-------|:----:|
| `json.tool baseline_authority_policy.json` | ✅ **PASS** |
| `json.tool 日报v3.6_schema.json` | ✅ **PASS** |
| `py_compile resolve_current_baseline.py` | ✅ **PASS** |
| `resolver --code 600114 --date 20260602` | ✅ **PASS** → baseline_id=`600114_W2026W22` |
| `resolver --code 600114 --json → json.tool` | ✅ **PASS** |
| `resolver --all --date 20260602` | ✅ **PASS 10 / BLOCK 0** |
| `check_baseline_authority.py --all --date 20260602` | ✅ **PASS 10 / BLOCK 0**（回归） |
| rg 旧示例检查 | ✅ 旧格式不作为可用示例出现 |
| git status — 变更范围 | ✅ 4 新增 + 4 修改。`重点股票/分析逻辑/interpretation_schema.json` 为 `??` untracked 文件，属于本会话前已存在的独立文件（统一解读 schema），非第1阶段产生或修改 |

---

### 第1阶段补修

> 补修日期：2026-06-02
> 补修原因：审查发现 3 处遗留问题

#### 修复点

| # | 问题 | 修复 | 文件 |
|:-:|:-----|:-----|:-----|
| 1 | `baseline_registry.schema.json` 第54行将 `600114_deep_20260529_v1.4` 列为"格式示例" | 改为只允许 `600114_W2026W22`，标注旧格式为禁用 | `baseline_registry.schema.json` |
| 2 | 阶段总账中第1阶段状态仍为"本阶段执行中" | 改为"已通过" | `地基重构阶段总账.md` |
| 3 | 验收记录未说明 `interpretation_schema.json` 来源 | 补充说明：该文件为既有 untracked 文件，非第1阶段产生 | 本文档 |

#### rg 旧示例检查修正

补修前：`baseline_registry.schema.json` 中将旧格式列为"格式示例"。

补修后：rg 检查唯一出现的旧格式引用在 `baseline_registry.schema.json` 和 `baseline_authority_contract.md` 中——均为**禁用说明或历史备注**，不构成可用的格式示例。

#### interpretation_schema.json 说明

`重点股票/分析逻辑/interpretation_schema.json` 显示在 git status 的 `??`（untracked）状态中。该文件属于统一解读体系（与 `统一解读/interpretation_schema.json` 相关联），在本会话开始前即已存在，**不是第1阶段新增或修改的文件**。第1阶段未触碰该文件。

> **第1.5阶段说明**：后续阶段自第1.5阶段起，统一按《项目唤醒卡》《变更生命周期与阶段门》《流程路由表》《角色唤醒协议》《阶段执行标准》《阶段验收报告模板》执行。

---

## 八、未解决问题

以下问题不在第1阶段处理范围：

| 编号 | 问题 | 严重度 | 计划修复 |
|:-----|:------|:------:|:--------|
| B-02 | 深度分析系统附录 baseline_id 命名多版本 | P1 | 待第1阶段后续或第5阶段 |
| B-03 | 关键价位口径混用（阈值宽松未暴露） | P1 | 待第1阶段后续 |
| D-02/D-03 | 其他股票止损 MD/sidecar 差异 | P1 | 第4阶段 |
| F-01 | 融资 T+6 延迟 | P1 | 第3阶段 |
| N-02 | data_scored 覆盖不足 | P1 | 第2阶段 |

---

## 九、结论

### 是否建议通过第1阶段：✅ 建议通过。

**依据：**
1. baseline 权威契约已固化 → ✅
2. resolver 脚本已可用（10/10 PASS）→ ✅
3. 旧 schema/字段字典/白皮书已修正 → ✅
4. P0-A 回归验证通过（--all 10/0 PASS）→ ✅
5. 阶段总账已同步更新 → ✅
6. 未修改允许范围之外的文件 → ✅

### 是否修改允许范围外文件

**否。** 仅修改了允许范围内的 4 个新增文件 + 4 个修改文件。
