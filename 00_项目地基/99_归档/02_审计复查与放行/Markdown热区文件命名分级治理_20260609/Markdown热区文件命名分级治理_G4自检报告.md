# Markdown 热区文件命名分级治理 — G4 自检报告

流程编号：F-RUNBOOK + F-FIX + F-GATE
阶段门：G3 → G4 → 用户确认 → G5 → G6
报告日期：2026-06-09
检查人：红结

---

## 1. L0/L1/L2 前缀文件数量

**结果：✅ PASS — 40 个**

| 级别 | 数量 | 说明 |
|:-----|:----:|:------|
| L0_ | 1 | 启动入口：`L0_INDEX_START_HERE_地基启动索引_v1.0.md` |
| L1_ | 6 | INDEX + STATE + FLOW + ROLE + TASK + CAP |
| L2_ | 33 | 7 数据契约 + 3 运行/后评估 + 3 审计主文件 + 7 迁移计划 + 13 五步优化接力包收口文件 |
| **合计** | **40** | 全部同目录 rename，同目录内不再有无前缀热区正式文件 |

## 2. 非前缀热区 .md

**结果：✅ PASS — 2 个，均为允许**

| 文件 | 允许理由 |
|:-----|:---------|
| `00_总览/START_HERE_地基启动索引.md` | 唯一保留的旧名 redirect 文件。内容已替换为"已迁移，见 L0_INDEX_START_HERE_地基启动索引_v1.0.md" |
| `00_总览/Markdown热区文件命名分级治理_G2准入单.md` | G2 阶段控制文件，不纳入 rename。G6 收口后由用户决定是否归档到 99_归档 |

## 3. 热区总量

**结果：✅ PASS — 42（40  rename 范围 + 2 允许非前缀）**

| 分解 | 数量 |
|:-----|:----:|
| L0_/L1_/L2_ 前缀（rename 范畴） | 40 |
| START_HERE redirect | 1 |
| G2 准入单（控制文件） | 1 |
| **热区总量** | **42** |

> ⚠️ G2 准入单 §四 记载热区 .md 总量为 41，系 G2 设计阶段少算 START_HERE redirect 保留文件的计数口径偏差，为 WARN 级别。**当前 G3 实施严格按 rename 范围执行，无漏改、无多改，不返工。**

## 4. 99_归档 .md 总数

**结果：✅ PASS — 21**

| 分解 | 数量 |
|:-----|:----:|
| 原归档文件（不改名） | 20 |
| G3 新增 RENAME_MANIFEST_20260609.md | 1 |
| **99_归档 合计** | **21** |

- 原 20 个文件**无任何 L_ 前缀**，保持原有文件名不变
- 新增的 RENAME_MANIFEST 为唯一新增文件，文件名无前缀

## 5. RENAME_MANIFEST_20260609.md

**结果：✅ PASS — 存在且完整**

文件路径：`99_归档/RENAME_MANIFEST_20260609.md`

内容覆盖：
- 40 条改名映射（A~G 七组，含原路径/新路径/级别/类型）
- 文件级别总览表（L0=1, L1=6, L2=33）
- 兼容策略说明（含 START_HERE redirect 说明）
- 受影响索引文件清单（7 个索引文件 + 99_归档 README）

## 6. archive/fulltext 未改名

**结果：✅ PASS — 50 个 .md 全部保留**

- 文件数量：50（与 G3 前一致）
- 文件名规则：无 L_ 前缀，无任何变更
- 目录归类：L3 归档追溯，默认不读

## 7. START_HERE redirect

**结果：✅ PASS**

- 旧 `START_HERE_地基启动索引.md` 存在（`00_总览/`）
- 内容为 redirect："当前启动入口已改为：`L0_INDEX_START_HERE_地基启动索引_v1.0.md`"
- 指向的 `L0_INDEX_START_HERE_地基启动索引_v1.0.md` 存在且内容完整（含任务路由表 + 角色读取约束 + 禁止清单）
- 本轮任何角色启动、旧会话、旧 prompt 引用 START_HERE 时均可通过 redirect 到达新 L0 入口

## 8. JSON/脚本/数据/生产入口

**结果：✅ PASS — 本轮未修改**

| 范畴 | 检查结果 |
|:-----|:---------|
| `02_权威注册表/*.json` | 10 个 JSON 文件均在。git status 显示的 dirty 为 **pre-existing**，非本轮 rename 造成 |
| `scripts/` | 未修改 |
| `代码文件/` | 未修改 |
| 日报/深度分析/荐股/保护机制/模拟交易 | 不在 rename 范围，未触及 |

> **说明：** git status 中 02_权威注册表、04_一致性闸门等 JSON 文件显示 "M" 状态，系本会话 session 启动前已存在的 dirty（上一轮热区瘦身遗留 + 统一解读变更等），不纳入本轮 G4 结论。

## 9. Git/GitHub

**结果：✅ PASS — 未处理**

- git add：❌ 未执行
- git commit：❌ 未执行（`git log --oneline -1` 显示为上一轮提交，非本轮）
- git push：❌ 未执行
- GitHub：❌ 未处理

## 10. Formal pipeline

**结果：⚠️ 明示例外 — 不得声称 PASS**

- actor/HMAC sign-off：❌ 不可用
- pipeline_engine.py：❌ 非本会话流程入口
- 本次基于 G2 准入单 + 用户逐次确认推进，不等同于 formal pipeline PASS
- 旧影 G5 复查与腰子 G6 放行继续按流程执行

---

## G4 综合结论

| # | 检查项 | 结果 |
|:-:|:-------|:----:|
| 1 | L0/L1/L2 前缀文件 = 40 | ✅ PASS |
| 2 | 非前缀热区 .md = 2（允许） | ✅ PASS |
| 3 | 热区总量 = 42（G2 单 41 为 WARN） | ✅ PASS |
| 4 | 99_归档 .md = 21 | ✅ PASS |
| 5 | RENAME_MANIFEST 存在 | ✅ PASS |
| 6 | archive/fulltext 未改名 | ✅ PASS |
| 7 | START_HERE redirect 指向正确 | ✅ PASS |
| 8 | JSON/脚本/数据/生产入口未改 | ✅ PASS（pre-existing dirty 已排除） |
| 9 | Git/GitHub 未处理 | ✅ PASS |
| 10 | Formal pipeline 明示例外 | ⚠️ 例外 |
| | **整体结论** | **✅ G4 PASS** |

**按流程暂停，等待用户确认进入 G5 旧影独立复查。**
