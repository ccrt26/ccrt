# G6 完成定义与闭环规则 v1.0

> 版本：v1.0 | 生效日期：2026-06-14
> 所有 G0-G6 流程必须引用本规则。
> 本规则统一解读：G6 PASS = 任务目标已完成。

---

## 一、G6 PASS 的定义

**G6 PASS = 任务目标已完成。**

当系统或流程通过 G6 阶段时，意味着：

1. **该任务的技术目标已达成**（代码实现、证据生成、签章链完整）。
2. **该任务的功能目标已达成**（可独立运行、已验证、可被下游消费）。
3. **该任务的终态产物已确定**——产出必须覆盖该任务目标所需的全部完成证据。可能包括 `archive_record`、`production_switch_record`、`runtime_verification`、`release evidence`、`production verification` 等；具体需要哪些由任务目标和 `release_policy` 决定。未产齐目标所需证据，不得输出 G6 PASS。

G6 PASS 之后不再存在任何需要用户继续判断或决策的"尾巴"。归档、启用、发布、生产验证的差异不应留给用户判断。用户不需要判断归档、启用、发布、生产验证的差异——这些差异由角色和自动化系统在 G6 阶段内消化完毕。

---

## 二、G6 三个阶段与边界

### 2.1 G6 candidate（自检候选）

- **含义**：执行模型自我验证结果，不等同正式角色签章。
- **formal**：false
- **产出文件**：`*_G4_self_check_candidate.json` 或 `*_G6_*_candidate*.json`
- **边界**：不得 claim `archive_completed`、`tag_completed`、`merge_completed`、`push_completed`。
- **用户可见性**：可作为复查输入，不得作为行动依据。

### 2.2 G6 readiness（就绪验证）

- **含义**：G6 formal_signoff 完成 + `archive_after_g6` 确认 ARCHIVE_READY_DRY_RUN 通过。
- **formal**：true（已含 formal_signoff）
- **产出文件**：`*_G6_archive_readiness_record.json`
- **边界**：`archive_not_executed=true`，表示真实归档尚未执行。这是 G6 PASS 的前置条件，不是 G6 PASS 本身。

### 2.3 G6 PASS（正式完成）

- **含义**：任务目标已完成。G6 formal_signoff 已通过 + 任务目标所需的全部终态证据已产齐。
- **未完成目标终态，不得输出 G6 PASS**。如果目标所需证据（archive_record、production_switch_record、runtime_verification 等）未全部生成，或者生成了但包含待用户确认的遗留事项，则不得 claim G6 PASS。
- **formal**：true
- **产出文件**：视任务目标需要，包括但不限于 `*_G6_archive_record.json`（result=CLOSED, archive_completed=true）、`*_production_switch_record.json`（result=ACTIVE）、`*_production_switch_runtime_verification.json`（result=PASS）等。
- **边界**：目标所需证据全部产齐。不得在 G6 PASS 后遗留"还需用户确认归档/发布/生产验证"的表述。

### 2.4 边界对照表

| 阶段 | formal | archive_completed | production_switched | 用户需要决策 |
|:-----|:-------|:------------------|:--------------------|:-------------|
| G6 candidate | false | false | false | 是（需角色复查） |
| G6 readiness | true | false (archive_not_executed) | false | 否（仅需复查） |
| **G6 PASS** | **true** | **目标所需证据已产齐** | **明确声明** | **否** |

---

## 三、用户汇报口径

### 3.1 允许的三种终态

用户只看到三种状态，由 `scripts/ccrt_user_report_normalizer.py` 统一归一化：

```
1. COMPLETE
   CCRT 全流程已完成，已归档，已提交 GitHub。

2. AUTO_REPAIRING
   发现问题，系统已打回对应环节自动修复，无需用户处理。

3. BLOCK
   BLOCK：<具体不可自动处理原因>
```

### 3.2 禁止的汇报

以下表达一律禁止出现在面向用户的终态报告中（可保留在内部证据 JSON 中）：

- ❌ "本输出只是 G4 自检候选"
- ❌ "不是 G5 PASS，不是 G6 PASS"
- ❌ "等待独立复查" / "等待复查"
- ❌ "等待 G6"
- ❌ "等待归档"
- ❌ "未 tag，未 merge，未 push"
- ❌ "请用户确认下一阶段"
- ❌ `candidate_only`、`not_g5_pass`、`not_g6_pass`、`waiting_review`、`archive_not_executed`、`forbidden_claims`、`forbidden_actions`、`no_role_signoff_claimed`
- ❌ 任何在 COMPLETE 之后仍将"归档/发布/启用/生产切换"表述为用户决策的句子

内部证据 JSON 允许保留上述字段用于审计和追溯，但 `ccrt_user_report_normalizer.py` 会在输出前拦截含这些字段的用户报告。

### 3.3 任务终态自包含原则

每个 G6 终结的任务必须满足：**一个读者（非本项目成员）读完该任务的 G6 产出文件后，能明确知道该任务是否已完成、完成到什么状态、下一步应该做什么。** 不需要向任何人追问才能理解。

---

## 四、角色输出约束

### 4.1 阿黑（调度路由）

- G6 阶段只能路由到旧影（独立复查）→ 腰子（G6 formal_signoff）→ 归档/生产切换。
- G6 PASS 后不得以任何理由将"归档/发布/启用"拆成需要用户额外判断的步骤。
- G6 阶段出现缺 HMAC、缺 actual_actor、越权签章时，应自动打回对应环节，不升级用户。

### 4.2 旧影（独立审计）

- G5/G6 复查结论只写 PASS / WARN / BLOCK。
- 不得在结论后附加"但需要用户确认归档/发布"。
- G6 formal_signoff 缺签章条件时，输出 WAITING_FORMAL_SIGNOFF，不升级用户。

### 4.3 腰子（业务负责人）

- G6 formal_signoff 缺 actual_actor=腰子 时，不得生成 formal_signoff。
- G6 formal_signoff 通过后，允许自动归档或生成 production_switch_record。

### 4.4 执行角色/红结

- 不得 claim G5/G6 PASS。
- 不得代替旧影/腰子签章。
- 不得写 `archive_completed=true` 或 `g6_pass_claimed=true`。

---

## 五、自动化闭环要求

### 5.1 三段自动推进

```
G4 candidate PASS
  → stage_gate_auto_advance.py 判断 ADVANCE_READY
    → G5 formal_signoff（旧影 actor-bound HMAC）
      → stage_gate_auto_advance.py 判断 ADVANCE_READY
        → G6 formal_signoff（腰子 actor-bound HMAC）
          → archive_after_g6.py 判断 ARCHIVE_READY_DRY_RUN
            → stage_gate_release_orchestrator.py 归档/生产切换
              → G6 PASS（目标所需全部终态证据）
```

### 5.2 每一段必须满足的条件

| 段 | 输入 | 通过条件 | 拒绝条件（自动打回） |
|:---|:-----|:---------|:-------------------|
| G4→G5 | candidate PASS | ADVANCE_READY | missing_evidence, BLOCK, candidate_claims_formal |
| G5→G6 | formal_signoff + actual_actor=旧影 + HMAC | ADVANCE_READY | missing_hmac, missing_actual_actor, role_substitution, actual_actor_mismatch |
| G6→archive | formal_signoff + actual_actor=腰子 + HMAC | ARCHIVE_READY_DRY_RUN | 同上 + 无用户确认的生产动作 |
| 归档 | G6 signoff + ARCHIVE_READY_DRY_RUN | archive_record (CLOSED) | 任何 G6 证据问题 → BLOCK，不归档 |

### 5.3 违反闭环的自动检测

- `archive_after_g6.py` 判断结果非 `ARCHIVE_READY_DRY_RUN` → `stage_gate_release_orchestrator.py` 不得输出 CLOSED archive_record。
- `stage_gate_release_orchestrator.py` 的 `make_archive_record()` 已复用 `archive_after_g6.evaluate()` 作为唯一归档判定源——这是强制安全闸门。

---

## 六、术语统一

| 旧表达（禁止） | 正确表达 |
|:--------------|:---------|
| "已归档但未完成" | "已生成 archive_record，result=CLOSED，任务已完成" |
| "G6 通过了但归档没做" | "G6 未完成——G6 formal_signoff 后未产出 archive_record" |
| "等待用户确认是否归档" | "G6 PASS —— archive_record 已生成"（或 "G6 未 PASS —— 归档条件尚不满足"） |
| "已切换生产，但用户需要确认" | "production_switch_record 已生成，生产已切换"（或 "未切换"） |
| "让用户看看要不要发布" | "已发布"（或 "未发布——发布条件尚不满足"） |

---

## 七、G0-G6 流程引用要求

1. 所有新建 G0-G6 流程必须在本文件中登记（或引用本文件版本号）。
2. 任何 G6 阶段的产出，必须声明是否符合本规则的 G6 PASS 定义。
3. 违反本规则的 G6 结论，旧影应标记为 BLOCK 并退回。
4. 本规则 v1.0 适用于以下已归档流程：
   - F-GATE-STAGE-AUTO-ADVANCE-20260614
   - F-GATE-STAGE-RELEASE-ORCHESTRATOR-20260614

---

## 八、附则

- 本规则不替代 `stage_gate_registry.json` 中的三段推进规则。
- 本规则中的"用户"指任务提出者或业务负责人，非角色体系中的某个具体角色。
- 本规则中的"归档"专指 08_审计与验收 下的 audit archive_record，不涉及生产数据归档。
