# Markdown 热区文件命名分级治理 — G6 放行收口

流程编号：F-RUNBOOK + F-FIX + F-GATE
阶段门：G6
放行日期：2026-06-09

---

## 一、G5 前置

旧影 G5 独立复查结论：**PASS**

复查报告路径：
`00_总览/Markdown热区文件命名分级治理_G5旧影独立复查报告.md`

复查基于 `99_归档/RENAME_MANIFEST_20260609.md` 的 40 条 rename 映射（manifest 驱动）：

| 检查项 | 结果 |
|:-------|:----:|
| M1: Manifest 40 条新路径全部存在 | ✅ PASS |
| M2: Manifest 39 条旧路径（除 START_HERE redirect）均不存在 | ✅ PASS |
| M3: START_HERE redirect 有效 | ✅ PASS |
| M4: 过程控制文件允许保留 | ✅ PASS |
| M5: 旁支 STEP-C 文件不纳入 rename | ✅ PASS |
| M6: 99_归档 与 RENAME_MANIFEST | ✅ PASS |
| M7: archive/fulltext 未改名 | ✅ PASS |
| M8: JSON/脚本/数据/生产入口非本轮造成 | ✅ PASS |
| M9: Git/GitHub 未处理 | ✅ PASS |
| M10: Formal pipeline 明示例外 | ⚠️ 例外 |

---

## 二、腰子 G6 意见

| 检查项 | 结论 |
|:-------|:-----|
| 本轮仅为 Markdown 文件命名治理 | ✅ 确认。40 个热区 .md 文件名加 L0/L1/L2 前缀，内容语义不改 |
| 不改变金融口径 | ✅ 确认。金融铁律、数值来源、新鲜度规则未触及 |
| 不改变数据架构 | ✅ 确认。D04 定义在 JSON/capability_registry.json，不受文件名变更影响 |
| 不改变生产入口 | ✅ 确认。日报/深度分析/每日荐股/保护机制/模拟交易未触及 |
| 不改变项目完成态 | ✅ 确认。L1_STATE_地基完成态与后续开门规则_v1.0.md 内容未改 |
| **同意放行** | ✅ **放行通过** |

---

## 三、Formal pipeline

actor/HMAC sign-off：❌ 不可用
formal pipeline：**明示例外**
本次不等同于 formal pipeline PASS。

---

## 四、过程文件处理

G2/G4/G5/G6 四份过程文件暂保留在 `00_总览/`：

| 文件 | 当前状态 | 后续处理 |
|:-----|:---------|:---------|
| `Markdown热区文件命名分级治理_G2准入单.md` | 热区保留 | 后续如需瘦身，另起一轮归档流程处理 |
| `Markdown热区文件命名分级治理_G4自检报告.md` | 热区保留 | 同上 |
| `Markdown热区文件命名分级治理_G5旧影独立复查报告.md` | 热区保留 | 同上 |
| `Markdown热区文件命名分级治理_G6放行收口.md`（本文件） | 热区保留 | 同上 |

> 以上过程文件不在本轮 G6 自动移动或删除。后续如需归档到 `99_归档/`，需另起请求并由用户确认。

---

## 五、Git/GitHub

| 操作 | 状态 |
|:-----|:----:|
| git add | ❌ 未执行 |
| git commit | ❌ 未执行 |
| git push | ❌ 未执行 |
| GitHub | ❌ 未处理 |

> 留待后续统一 commit，不在本轮 G6 处理。

---

## 六、禁止

- ⛔ 不返工 rename
- ⛔ 不修改 JSON
- ⛔ 不修改脚本
- ⛔ 不修改数据
- ⛔ 不修改生产入口
- ⛔ 不删除过程文件
- ⛔ 不处理 Git/GitHub

---

## 七、收口结论

> **Markdown 热区文件命名分级治理正式收口。**
>
> 经 G0 路由 → G2 方案设计+补修 → G3 rename 实施 → G4 自检 → G5 旧影复查 → G6 腰子放行，40 个热区正式 .md 完成文件名分级治理（L0=1, L1=6, L2=33），START_HERE redirect 保留，RENAME_MANIFEST 和 7 个索引引用已更新。99_归档、archive/fulltext、JSON、脚本、数据、生产入口均按要求保持未动。

---

*责任角色：阿黑（路由汇总）→ 腰子（G6 放行）*
