# P4：最小规则拆条与 rule_id 回填验收记录 v1.0

> **阶段：** P4 执行 | **日期：** 2026-06-06
> **执行模型：** 非角色代签，仅承担写入与命令执行

---

## 1. 修改清单

| 文件 | 操作 | 说明 |
|:-----|:-----|:------|
| `02_权威注册表/rule_asset_registry.json` | 新增 R-ROL-0002 | 反方角色规则条目 |
| `02_权威注册表/capability_registry.json` | 修改 C-D07-0001 | `rules_applied` 回填 ["R-FIN-0001", "R-ROL-0002"]，移除 `_note_rules_pending` |
| `05_流程与角色/P4_最小规则拆条与rule_id回填验收记录_v1.0.md` | 新增 | 本文件 |

## 2. 规则变更详情

### 2.1 新增 R-ROL-0002（反方角色规则）

- **rule_id:** R-ROL-0002
- **type:** role
- **owner:** 阿黑
- **source:** P3-CDE §4 表3
- **含义:** 反方只做 CounterOpinion 反证挑战（挑战证据充分性、结论跳跃、风险遗漏、反证条件），不采集数据、不签金融结论
- **depends_on:** R-ROL-0001（角色边界索引）

### 2.2 C-D07-0001 rules_applied 回填

- **新增规则引用:** `["R-FIN-0001", "R-ROL-0002"]`
- **R-FIN-0001:** 金融铁律约束统一解读方向、口径、公式使用（统一解读接入方案 §4 明文规定）
- **R-ROL-0002:** 反方 CounterOpinion 是统一解读能力必需输入项（C-D07-0001 输入定义）
- 已移除 `_note_rules_pending` 标注

### 2.3 未变更项

- D01/D03/D05/D06 的 `rules_applied` 保持空数组（无明确可命中规则，不强行回填）
- rule_asset_registry schema 不变
- capability_registry schema 不变
- 金融铁律正文不变
- 代码脚本、正式报告、baseline、sidecar、E3/canonical 均不变

## 3. 验收命令执行结果

### 3.1 `jq . 00_项目地基/02_权威注册表/rule_asset_registry.json`

→ 校验通过。包含 6 条规则（FIN/RED/COD/ROL/CST + 新增 R-ROL-0002），JSON 结构完整。

### 3.2 `jq . 00_项目地基/02_权威注册表/capability_registry.json`

→ 校验通过。包含 5 条能力条目，C-D07-0001 `rules_applied` 已回填。

### 3.3 `jq '.capabilities[] | select(.capability_id=="C-D07-0001") | .rules_applied'`

→ 输出 `["R-FIN-0001", "R-ROL-0002"]`（回填正确）

### 3.4 `grep -n "R-ROL-0002\|反方\|CounterOpinion" rule_asset_registry.json`

→ 确认 R-ROL-0002 条目存在，描述中包含"反方"和"CounterOpinion"关键词。

### 3.5 验收记录文件存在性

→ 本文件已创建于 `05_流程与角色/P4_最小规则拆条与rule_id回填验收记录_v1.0.md`

### 3.6 git status

→ 确认仅修改 3 个允许文件，无越界修改。

## 4. 结论

| 判定 | 说明 |
|:-----|:------|
| ✅ PASS | P4 最小规则拆条与 rule_id 回填完成 |
| ✅ 不阻断 P5 | 无阻塞性问题 |

## 5. 风险表

| 风险 | 等级 | 说明 | 处理 |
|:-----|:-----|:------|:-----|
| R-ROL-0002 source_line 仅引用 §4 表3 | LOW | 反方角色实际职责分散在多文件（P3-CDE §4、统一解读接入方案 §3） | 后续 P5/P6 可补全多 source_line 或增加 cross_ref |
| C-D07-0001 rules_applied 仅 2 条 | LOW | 当前最小集满足验证，后续规则拆条深入后可追加 | P5 规则资产深度治理时审视 |

---

*本记录由执行模型写入，不代签任何角色。*
