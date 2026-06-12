# ROLE：砺石最小字段程序化接入 — G0-G6 记录 v0.1

> **流程编号：** F-GATE
> **关联：** F-ROLE / F-KNOW
> **原因：** 为砺石方法校准输出新增最小结构化字段与校验规则
> **执行方式：** 字段/schema/validator 最小接入
> **formal pipeline：** 不声明 PASS
> **前置条件：** 第一步角色契约落地 + 第二步人工试运行完成（Codex 复查建议第三步）
> **版本：** v0.1
> **试运行时间：** 2026-06-12

---

## G0 — 路由记录

| 字段 | 值 |
|:-----|:-----|
| **流程编号** | F-GATE |
| **关联流程** | F-ROLE / F-KNOW |
| **原因** | 为砺石方法校准输出新增最小结构化字段与校验规则 |
| **执行方式** | 字段/schema/validator 最小接入 |
| **formal pipeline** | 不声明 PASS |
| **路由时间** | 2026-06-12 |

---

## G1 — 字段口径

### 最小字段集

```json
"method_review": {
  "role": "砺石",
  "role_code": "LISHI",
  "result": "PASS|WARN|BLOCK",
  "main_challenge": "",
  "check_item": "",
  "confidence_adjustment": "NONE|HIGH_TO_MEDIUM|MEDIUM_TO_LOW",
  "adjustment_reason": "",
  "action_adjustment": "NONE|BUY_TO_WATCH|SELL_TO_WATCH",
  "rejected_reason": ""
}
```

### 先不接入（延迟至第四步或月度复盘）

- anti_evidence_quality
- review_time_actual
- 复杂指标统计
- 自动抽样
- U-11

---

## G2 — 技术方案

| # | 文件 | 操作 | 内容 |
|:--|:-----|:-----|:------|
| 1 | `统一解读/interpretation_schema.json` | 修改 | role 枚举新增 "砺石"；properties 新增 `method_review` 可选子对象（9 字段：role/role_code/result/main_challenge/check_item/confidence_adjustment/adjustment_reason/action_adjustment/rejected_reason）；硬规则注释新增 R9-R13 |
| 2 | `统一解读/interpretation_rules.json` | 修改 | role_package_contracts 新增砺石条目；新增 `lishi_method_review_rules` 含 5 条检查（LMR-01 至 LMR-05） |
| 3 | `统一解读/validate_interpretation.py` | 修改 | 新增 `run_method_review()` 函数（LMR-01 至 LMR-05 校验）；集成到 main() 流程（Step 3b）；输出中加入 method_review_checks |
| 4 | `统一解读/角色解释包/腰子_整合单模板.md` | 确认 | 第一步已含 method_review_id/lishi_summary/adopted_challenges/rejected_challenges_reason，本轮仅确认不再重复扩展 |

### 最小校验规则

| 规则 ID | 条件 | 结果 | 说明 |
|:--------|:-----|:-----|:------|
| LMR-01 | method_review 存在时 role_code ≠ LISHI | BLOCK | 角色代码硬校验 |
| LMR-02 | result 不在 PASS/WARN/BLOCK | WARN | 值域校验 |
| LMR-03 | result=BLOCK 且 main_challenge 为空 | WARN | BLOCK 缺质疑点 |
| LMR-04 | confidence_adjustment≠NONE 且 adjustment_reason 为空 | WARN | 置信度调整缺原因 |
| LMR-05 | action_adjustment≠NONE 且 main_challenge 为空 | WARN | 动作方向调整缺质疑 |

### 未修改范围证明

- ❌ 不改日报/深度分析生成器
- ❌ 不改每日荐股
- ❌ 不改模拟交易
- ❌ 不改 role_matrix.json
- ❌ 不改 ROLE 文档
- ❌ 不新增 U-11
- ❌ 不改历史日报/深度正文
- ❌ 不改生产调度
- ❌ 不批量改 sidecar

---

## G3 — 执行记录

| 步骤 | 状态 |
|:-----|:-----|
| interpretation_schema.json — role 枚举新增"砺石" | ✅ |
| interpretation_schema.json — method_review 可选字段（9 子字段） | ✅ |
| interpretation_schema.json — 硬规则注释 R9-R13 | ✅ |
| interpretation_rules.json — role_package_contracts 新增砺石 | ✅ |
| interpretation_rules.json — lishi_method_review_rules 5条检查 | ✅ |
| validate_interpretation.py — run_method_review() 函数 | ✅ |
| validate_interpretation.py — main() 集成 Step 3b | ✅ |
| validate_interpretation.py — 输出 method_review_checks | ✅ |
| 腰子_整合单模板.md — 确认已有 4 字段 | ✅ |
| 7 项单元测试全部 PASS | ✅ |

---

## G4 — 自检结果

| 检查项 | 结果 |
|:-------|:-----|
| schema JSON 合法性 | ✅ `python3 -m json.tool` 通过 |
| rules JSON 合法性 | ✅ `python3 -m json.tool` 通过 |
| validate.py 语法 | ✅ `python3 -m py_compile` 通过 |
| method_review/LISHI 字段覆盖 4 文件 | ✅ 53 处命中 |
| 白空间 | ✅ 无错误 |
| validate.py 样例测试 | ✅ `样例1_日报_000001.json` PASS，无 method_review 时空数组 |
| 7 项 validator 单元测试 | ✅ 全部 PASS |
| 文件范围 — 统一解读 | ✅ 仅 4 个允许文件修改 |
| 文件范围 — 重点股票/ | ❌ 无本轮新修改 |
| 文件范围 — 05_流程与角色 | ❌ 无本轮新修改 |

---

## G5 — 复查结论（Codex 执行）

> **Codex 执行复查，不等同旧影正式签字。**

| # | 复查项 | 结果 | 依据 |
|:--|:-------|:-----|:------|
| 1 | 是否只改允许文件 | ✅ PASS | G4 确认仅 4 个允许文件（3修改+1确认） |
| 2 | method_review 是否为可选字段，不破坏旧解释对象 | ✅ PASS | schema 中 method_review 非 required；样例测试无 method_review 时返回空数组，不影响 PASS |
| 3 | 是否未新增 U-11 | ✅ PASS | U-11 不存在于任何修改文件中 |
| 4 | 是否未接生产生成器 | ✅ PASS | 无日报/深度分析/荐股/模拟交易生成器被修改 |
| 5 | validate_interpretation.py 是否语法通过 | ✅ PASS | `python3 -m py_compile` + 7 项测试全部 PASS |
| 6 | JSON 文件是否合法 | ✅ PASS | `python3 -m json.tool` 两个 JSON 均通过 |
| 7 | 是否没有修改历史日报/深度正文 | ✅ PASS | G4 git status 确认重点股票/无改动 |
| 8 | 是否没有把砺石变成必唤醒角色 | ✅ PASS | ROLE 文档未修改；role_matrix.json 未修改；schema 中 role 枚举含"砺石"但仅用于身份标识 |

### 总体结论

| 项目 | 判定 |
|:-----|:-----|
| **总体结论** | ✅ **PASS** |
| **复查人** | Codex 执行复查（不等同于旧影正式签字） |
| **遗留问题** | 无 |

---

## G6 — 归档

### 本轮完成

| 维度 | 状态 |
|:-----|:-----|
| method_review 最小字段进入 interpretation_schema.json | ✅ 已接入 |
| interpretation_rules.json 砺石字段规则 | ✅ 5 条 LMR 规则已接入 |
| validate_interpretation.py 最小校验 | ✅ run_method_review() 函数 + main() 集成 |
| 腰子模板字段确认 | ✅ method_review_id/lishi_summary/adopted_challenges/rejected_challenges_reason 已存在 |
| 7 项单元测试全部 PASS | ✅ |

### 本轮未完成

| 项目 | 原因 |
|:-----|:-----|
| 自动审查 | 字段已接入，审查仍需人工触发 |
| 生产接入 | 按约定不入生产 |
| U-11 | 按约定不新增 |
| 每日荐股/模拟交易接入 | 按约定不接入 |

### 固定声明

> Formal pipeline 未通过；RUN 仍停在当前阶段。
> 本阶段基于用户一次性授权与轻量字段接入流程例外继续，不等同于 formal pipeline PASS。
> 不得伪造 actor/HMAC sign-off，不得代签角色结论，不得自动推进后续阶段。

### 下一步建议

1. **小样例验证 method_review 字段** — 构造一个含 method_review 的测试 JSON 并通过 validate_interpretation.py 验证 LMR-01 至 LMR-05 全部正确触发
2. **日报/深度分析人工写入试用** — 在人工触发分析中实际写入 method_review 字段，观察运行稳定性
3. **第四步考虑** — anti_evidence_quality、自动抽样、复杂指标统计的程序化接入

### 最终产出物

| # | 产出物 | 状态 |
|:--|:-------|:-----|
| 1 | method_review 最小字段进入 interpretation_schema.json | ✅ |
| 2 | interpretation_rules.json 有砺石字段规则（LMR-01 至 LMR-05） | ✅ |
| 3 | validate_interpretation.py 能校验最小规则 | ✅（7 项测试通过） |
| 4 | 腰子模板字段确认 | ✅ |
| 5 | G0-G6 记录文件 | ✅ |
| 6 | 自检命令结果 | ✅ |
| 7 | Codex 复查结论：PASS | ✅ |
