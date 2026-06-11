# 文献状态机 v1.0

> **本文档定义外部文献卡片的状态定义、允许流转、禁止流转规则。**
> 配套文档：[POLICY_外部文献入库流程_v1.0.md](POLICY_外部文献入库流程_v1.0.md) | [POLICY_角色主责路由_v1.0.md](POLICY_角色主责路由_v1.0.md)

---

## 一、状态定义

| 状态 | 含义 | 字段要求 |
|:-----|:-----|:---------|
| `RAW_RECEIVED` | 原文已登记 | 必须有 source_id、title、source、publish_date、version、url_or_path |
| `ROUTED` | 阿黑已完成路由，指定了 primary_role | 必须指定 primary_role；必须有 material_type |
| `CARD_DRAFTED` | 文献卡片已由主责角色产出 | 必须有 card_id、reading_scope、核心结论、适用范围、适用条件、不适用条件、evidence_level、review_date |
| `FINANCE_ALIGNED` | 腰子已统一金融口径 | `finance_aligned = true`；`finance_owner = 腰子` |
| `REFERENCE_ONLY` | 可作为参考知识，不可执行 | 参考阶段，无额外字段要求 |
| `VALIDATION_PENDING` | 项目验证阶段 | 必须有 VAL 验证文件；`validated = true` |
| `PARAM_CANDIDATE` | 参数候选——验证表明参数有效 | 必须通过验证 |
| `COUNTEREXAMPLE_CANDIDATE` | 反例候选——文献形成反例 | 必须通过验证 |
| `CORE_CANDIDATE` | 核心知识候选——可升级为核心知识 | 必须通过验证 |
| `ACTIVE` | 已生效，可进入角色启动上下文 | 必须有 `confirmed_roles`、适用条件、不适用条件、`valid_until`、`review_date` |
| `DEPRECATED` | 已废弃，不再使用 | 必须有废弃原因 |

## 二、允许流转（白名单）

```
RAW_RECEIVED ──────────────► ROUTED
ROUTED ────────────────────► CARD_DRAFTED
CARD_DRAFTED ──────────────► FINANCE_ALIGNED
FINANCE_ALIGNED ───────────► REFERENCE_ONLY
REFERENCE_ONLY ────────────► VALIDATION_PENDING
VALIDATION_PENDING ────────► PARAM_CANDIDATE
VALIDATION_PENDING ────────► COUNTEREXAMPLE_CANDIDATE
VALIDATION_PENDING ────────► CORE_CANDIDATE
PARAM_CANDIDATE ───────────► ACTIVE
COUNTEREXAMPLE_CANDIDATE ──► ACTIVE
CORE_CANDIDATE ────────────► ACTIVE
ACTIVE ────────────────────► DEPRECATED
```

## 三、禁止流转（黑名单）

| 非法流转 | 原因 |
|:---------|:-----|
| `RAW_RECEIVED` → `ACTIVE` | 越级：未经卡片、口径、验证、确认 |
| `CARD_DRAFTED` → `ACTIVE` | 越级：未经腰子口径、参考知识、验证 |
| `REFERENCE_ONLY` → `ACTIVE` | 越级：未经验证、确认 |
| `CARD_DRAFTED` → `CORE_CANDIDATE` | 越级：未经腰子口径、参考知识、验证 |
| 未经验证 → `PARAM_CANDIDATE` | 禁止：候选层必须经过 VALIDATION_PENDING |
| 未经验证 → `COUNTEREXAMPLE_CANDIDATE` | 禁止：候选层必须经过 VALIDATION_PENDING |
| 未经验证 → `CORE_CANDIDATE` | 禁止：候选层必须经过 VALIDATION_PENDING |
| 未经确认 → `ACTIVE` | 禁止：`confirmed_roles` 必须非空 |
| 无 `review_date` → `ACTIVE` | 禁止：必须设定复审日期 |
| 无 `valid_until` → `ACTIVE` | 禁止：必须设定有效期 |
| 无适用条件 → `ACTIVE` | 禁止：必须写明适用条件 |
| 无不适用条件 → `ACTIVE` | 禁止：必须写明不适用条件 |
| `finance_aligned != true` → 候选层或 ACTIVE | 禁止：未经腰子统一口径 |

## 四、状态机校验规则（由程序 enforcement）

### 4.1 流转前检查（`transition` 命令）

执行 `transition card_id --to TARGET_STATE` 时，程序必须检查：

1. 当前状态 → TARGET_STATE 是否在允许流转白名单中
2. 如在禁止流转黑名单中 → 拒绝并输出原因
3. 如不在白名单也不在黑名单 → 拒绝，输出"未定义流转"
4. 以下附加检查取决于目标状态：

### 4.2 进入候选层（PARAM_CANDIDATE / COUNTEREXAMPLE_CANDIDATE / CORE_CANDIDATE）前检查

- [ ] `finance_aligned == true`
- [ ] `validated == true`
- [ ] 当前状态为 VALIDATION_PENDING
- [ ] 存在对应的 VAL 验证文件

### 4.3 进入 ACTIVE 前检查

- [ ] `finance_aligned == true`
- [ ] `validated == true`
- [ ] `confirmed_roles` 非空
- [ ] 存在适用条件（正文包含"适用范围"或"适用条件"节）
- [ ] 存在不适用条件（正文包含"不适用条件"节）
- [ ] `valid_until` 存在且未过期
- [ ] `review_date` 存在
- [ ] lint 检查无 ERROR 级别违规

### 4.4 进入 DEPRECATED 前检查

- [ ] 当前状态为 ACTIVE
- [ ] 正文包含废弃原因说明

## 五、过期规则

1. `valid_until` 早于当前日期 → 过期，应进入复审流程
2. 过期内容不得出现在 `active_index.json` 中
3. 过期内容应触发 `due` 命令输出到 `pending_review.json`
4. 过期内容可根据复审结果：重新生效（renew valid_until）或进入 DEPRECATED

## 六、索引加载规则

| 索引文件 | 收录内容 |
|:---------|:---------|
| `sources_index.json` | 所有 raw 目录中的原文 |
| `cards_index.json` | 所有 cards 目录中的文献卡片 |
| `active_index.json` | **仅** ACTIVE 且未过期内容 |
| `pending_review.json` | 待验证、待确认、待复审内容 |
| `expired_index.json` | 过期或即将过期内容 |
| `violations.json` | lint 检查发现的违规项 |

> ⚠️ `active_index.json` **不得**加载 raw、cards、candidates、deprecated 内容。

---

## 七、版本信息

| 项目 | 内容 |
|:-----|:-----|
| 当前版本 | v1.0 |
| 最后更新 | 2026-06-10 |
| 更新人 | 阿黑/情墨 |
| 变更摘要 | 初始版本：文献状态机定义 |
