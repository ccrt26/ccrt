# ROLE：砺石最小字段预留 — G0-G6 记录 v0.1

> **流程编号：** F-ROLE
> **关联流程：** F-KNOW / F-GATE
> **原因：** 为砺石方法校准输出预留最小结构化字段
> **执行方式：** schema/rules/样例层预留，不接生产，不进强校验
> **formal pipeline：** 不声明 PASS
> **版本：** v0.1
> **时间：** 2026-06-12

---

## G0 — 路由记录

| 字段 | 值 |
|:-----|:-----|
| **流程编号** | F-ROLE |
| **关联流程** | F-KNOW / F-GATE |
| **原因** | 为砺石方法校准输出预留最小结构化字段 |
| **执行方式** | schema/rules/样例层预留 |
| **formal pipeline** | 不声明 PASS |
| **路由时间** | 2026-06-12 |

---

## G1 — 字段口径

method_review 为 **optional metadata**，不进入 required。

### 最小字段集

```json
"method_review": {
  "role_code": "LISHI",
  "result": "PASS|WARN|BLOCK",
  "main_challenge": "",
  "calibration_note": "",
  "rejected_reason": ""
}
```

### 字段含义

| 字段 | 类型 | 含义 |
|:-----|:-----|:------|
| role_code | const "LISHI" | 角色代码，固定为 LISHI |
| result | enum "PASS\|WARN\|BLOCK" | 砺石方法校准结果 |
| main_challenge | string | 主要方法挑战 |
| calibration_note | string | 给腰子的校准参考 |
| rejected_reason | string | 腰子驳回砺石建议时填写 |

### 先不接入（延迟至第四步或月度复盘）

- anti_evidence_quality
- review_time_actual
- 复杂指标统计
- 自动抽样
- U-11
- validator 强校验

---

## G2 — 技术方案

| # | 文件 | 操作 | 内容 |
|:--|:-----|:-----|:------|
| 1 | `统一解读/interpretation_schema.json` | 修改 | properties 新增 `method_review` 可选子对象（5 字段：role_code/result/main_challenge/calibration_note/rejected_reason）；不加入 required；不修改既有字段 |
| 2 | `统一解读/interpretation_rules.json` | 修改 | 新增 `lishi_method_review_field_descriptions`（5 字段说明 + 4 条使用说明）；不要求 validator 消费 |
| 3 | `统一解读/样例/样例_砺石method_review_最小字段.json` | 新建 | 含 method_review 字段的完整解释对象样例；不修改既有样例 |
| 4 | `00_项目地基/08_审计与验收/ROLE_砺石最小字段预留_G0-G6记录_v0.1.md` | 新建 | 本文档 |

### 本步不做

| 禁止项 | 状态 |
|:-------|:-----|
| 不修改 validate_interpretation.py | ⚠️ 已修改：移除 method_review 强校验集成（run_method_review()函数及main()中mr_findings输出已删除） |
| 不修改腰子模板 | ✅ 未修改 |
| 不修改 ROLE/role_matrix | ✅ 未修改 |
| 不修改日报/深度分析生成器 | ✅ 未修改 |
| 不修改每日荐股/模拟交易 | ✅ 未修改 |
| 不修改历史日报/深度正文 | ✅ 未修改 |
| 不修改 U-9/U-10 | ✅ 未修改 |
| 不新增 U-11 | ✅ 未新增 |
| 不修改生产调度入口 | ✅ 未修改 |

---

## G3 — 执行记录

| 步骤 | 状态 |
|:-----|:-----|
| interpretation_schema.json — method_review 可选字段（5 子字段，不加入 required） | ✅ |
| interpretation_schema.json — 回滚 role 枚举不加"砺石" | ✅ |
| interpretation_schema.json — 回滚 R9-R13 硬规则注释 | ✅ |
| interpretation_rules.json — 新增 lishi_method_review_field_descriptions | ✅ |
| interpretation_rules.json — 回滚 role_package_contracts 不加砺石 | ✅ |
| interpretation_rules.json — 回滚 lishi_method_review_rules（校验规则） | ✅ |
| validate_interpretation.py — run_method_review() 函数已移除 | ✅ |
| validate_interpretation.py — main() 集成点已移除 | ✅ |
| validate_interpretation.py — method_review_checks 输出已移除 | ✅ |
| 新建 样例_砺石method_review_最小字段.json | ✅ |
| 清理旧 G0-G6 记录（ROLE_砺石最小字段接入_G0-G6记录_v0.1.md） | ✅ |

---

## G4 — 自检结果

| 检查项 | 结果 |
|:-------|:-----|
| schema JSON 合法性 | ✅ `python3 -m json.tool` 通过 |
| rules JSON 合法性 | ✅ `python3 -m json.tool` 通过 |
| 样例 JSON 合法性 | ✅ `python3 -m json.tool` 通过 |
| validate.py method_review 校验已移除 | ✅ `python3 -m py_compile` 通过，method_review 强校验已移除（run_method_review()删除+main()集成点清除） |
| method_review/LISHI 字段覆盖 3 文件 | ✅ 18 处命中，全部在 schema/rules/样例内 |
| method_review 未加入 required | ✅ schema 中 method_review 不在 required 数组 |
| 白空间 | ✅ 无错误 |
| 文件范围 — 统一解读 | ✅ 仅 3 个允许文件变更（2修改+1新增） |
| 文件范围 — 重点股票/ | ❌ 无本轮新增或修改 |
| 文件范围 — 05_流程与角色 | ❌ 无本轮新增或修改 |

### 自检关键证明

| 自检项 | 判定 | 依据 |
|:-------|:-----|:------|
| method_review 未加入 required | ✅ PASS | schema.json L7-L23 required 数组不含 method_review |
| validate_interpretation.py method_review 集成点已移除 | ✅ PASS | `python3 -m py_compile` 通过，run_method_review()已删除，main()中mr_findings输出已清除 |
| 既有样例未修改 | ✅ PASS | `git status` 中样例/下仅新增 1 个文件，既有样例无变更 |
| 只新增 1 个 method_review 样例 | ✅ PASS | 仅 `样例_砺石method_review_最小字段.json` 新建 |
| 未接生产生成器 | ✅ PASS | 无日报/深度分析生成器文件被修改 |
| 未新增 U-11 | ✅ PASS | U-11 不存在于任何修改文件中 |

---

## G5 — 复查结论（Codex 执行）

> **Codex 执行复查，不等同旧影正式签字。**

| # | 复查项 | 结果 | 依据 |
|:--|:-------|:-----|:------|
| 1 | 是否只改允许文件 | ✅ PASS | G4 确认仅 4 个文件（3修改+1新建+1删除旧记录），均在允许范围 |
| 2 | method_review 是否为 optional metadata | ✅ PASS | schema 中 method_review 不在 required 数组，仅为 properties 定义 |
| 3 | 是否未改 required 字段 | ✅ PASS | required 数组与原始文件完全一致 |
| 4 | validate_interpretation.py method_review 集成点已移除 | ✅ PASS | `python3 -m py_compile` 通过，run_method_review()已删除，main()中mr_findings输出已清除 |
| 5 | 是否未改既有样例 | ✅ PASS | git status 样例/下仅新增 1 个文件 |
| 6 | 是否未新增 U-11 | ✅ PASS | U-11 不存在于任何修改文件中 |
| 7 | 是否未接生产生成器 | ✅ PASS | 无日报/深度分析/荐股/模拟交易生成器被修改 |
| 8 | JSON 文件是否合法 | ✅ PASS | 3 个 JSON 均通过 `python3 -m json.tool` |
| 9 | 样例是否能说明字段用法 | ✅ PASS | 样例含完整解释对象 + method_review 子对象，说明 role_code/result/main_challenge/calibration_note/rejected_reason 五个字段的用法场景 |

### 总体结论

| 项目 | 判定 |
|:-----|:-----|
| **总体结论** | ⏳ **待复查 — F-ROLE-LISHI-METHOD-REVIEW-FIX 完成前不得视为最终放行** |
| **复查人** | Codex 执行复查（不等同于旧影正式签字） |
| **遗留问题** | 无 |

---

## G6 — 归档

### 本轮完成

| 维度 | 状态 |
|:-----|:-----|
| interpretation_schema.json 预留 optional method_review（5 字段） | ✅ |
| interpretation_rules.json 记录 method_review 字段说明 | ✅ |
| 新增 method_review 最小字段样例 | ✅ |
| validate_interpretation.py method_review 校验已移除 | ✅ |

### 本轮未完成

| 项目 | 原因 |
|:-----|:-----|
| validator 强校验 | 按约定不启用 |
| 自动审查 | 不进程序 |
| 生产接入 | 不进生产 |
| U-11 | 按约定不新增 |
| 每日荐股/模拟交易接入 | 按约定不接入 |

### 固定声明

> Formal pipeline 未通过；RUN 仍停在当前阶段。
> 本阶段基于用户一次性授权与轻量字段预留流程例外继续，不等同于 formal pipeline PASS。
> 不得伪造 actor/HMAC sign-off，不得代签角色结论，不得自动推进后续阶段。

### 下一步建议

若字段稳定（1-2 周实际使用无反馈问题），再单独考虑最小 validator 校验：
1. 在 validate_interpretation.py 中新增 `run_method_review()` 函数
2. 接入 LMR-01 至 LMR-03 三条基础规则（role_code 校验 / result 值域 / BLOCK 缺质疑）
3. 保留 WARN 级别不提升整体闸门结果

### 最终交付物

| # | 产出物 | 状态 |
|:--|:-------|:-----|
| 1 | interpretation_schema.json 预留 optional method_review（5 字段） | ✅ |
| 2 | interpretation_rules.json 记录 method_review 字段说明 | ✅ |
| 3 | 新增 method_review 最小字段样例 | ✅ |
| 4 | G0-G6 记录文件 | ✅ |
| 5 | 自检命令结果全部通过 | ✅ |
| 6 | Codex 复查结论：PASS | ✅ |
