# Markdown 热区文件命名分级治理 — G5 旧影独立复查报告

复查编号：G5-20260609-MD-RENAME
复查人：旧影（独立审计官）
复查日期：2026-06-09
流程：F-RUNBOOK + F-FIX + F-GATE
验收标准：以 `99_归档/RENAME_MANIFEST_20260609.md` 为唯一 rename 验收清单

---

## M1：Manifest 40 条新路径全部存在

**结果：✅ PASS — 40/40 存在**

| 分组 | 范围 | 应存在 | 实测 |
|:-----|:-----|:------:|:----:|
| A | 00_总览/ (L0×1 + L1×2) | 3 | ✅ 3 |
| B | 05_流程与角色/ (L1×4) | 4 | ✅ 4 |
| C | 01_数据契约/ (L2 CONTRACT×7) | 7 | ✅ 7 |
| D | 06_后评估闭环 + 06_调度与运行/ (L2×3) | 3 | ✅ 3 |
| E | 08_审计与验收 主文件/ (L2×3) | 3 | ✅ 3 |
| F | 09_迁移计划/ (L2×7) | 7 | ✅ 7 |
| G | 02_五步优化接力包 保留文件/ (L2×13) | 13 | ✅ 13 |
| — | **合计** | **40** | **✅ 40** |

## M2：Manifest 40 条旧路径（除 START_HERE redirect）均不存在

**结果：✅ PASS — 39/39 已删除，0 残留**

| 分组 | 旧路径数 | 应不存在 | 实测 |
|:-----|:--------:|:--------:|:----:|
| A | 2（INDEX + STATE，不含 START_HERE） | 2 | ✅ 2 |
| B | 4 | 4 | ✅ 4 |
| C | 7 | 7 | ✅ 7 |
| D | 3 | 3 | ✅ 3 |
| E | 3 | 3 | ✅ 3 |
| F | 7 | 7 | ✅ 7 |
| G | 13 | 13 | ✅ 13 |
| — | **合计** | **39** | **✅ 39** |

## M3：START_HERE redirect 允许保留

**结果：✅ PASS**

文件：`00_总览/START_HERE_地基启动索引.md`
内容：
```
# 已迁移
当前启动入口已改为：
**`L0_INDEX_START_HERE_地基启动索引_v1.0.md`**
请读取新文件。
```

新入口 `00_总览/L0_INDEX_START_HERE_地基启动索引_v1.0.md` 存在且内容完整。

## M4：过程控制文件允许保留

**结果：✅ PASS — 2 个过程文件，G6 后决定是否归档**

| 文件 | 类型 | 处理方式 |
|:-----|:-----|:---------|
| `Markdown热区文件命名分级治理_G2准入单.md` | G2 过程控制文件 | 热区保留，G6 后由用户决定 |
| `Markdown热区文件命名分级治理_G4自检报告.md` | G4 过程控制文件 | 热区保留，G6 后由用户决定 |

## M5：旁支 STEP-C 文件不纳入本轮 rename

**结果：✅ PASS — 不视为实施错误**

文件 `L2_REPORT_STEP-C与分析逻辑重构解耦方案_G2_v1.0.md` 不在本轮 manifest 中，归类为旁支 STEP-C G2 前置文件。其 L2 命名格式正确，**不返工**。

## M6：99_归档 与 RENAME_MANIFEST

**结果：✅ PASS**

| 检查项 | 结果 |
|:-------|:----:|
| `99_归档/RENAME_MANIFEST_20260609.md` 存在 | ✅ 存在，40 条映射完整 |
| 99_归档 .md 总数 = 21 | ✅ 21（原 20 + RENAME_MANIFEST） |
| 99_归档 文件含 L_ 前缀 | ✅ 0 个（未改名） |

## M7：archive/fulltext 不纳入 rename

**结果：✅ PASS**

| 检查项 | 结果 |
|:-------|:----:|
| archive/fulltext .md 总数 = 50 | ✅ 50 |
| archive/fulltext 文件含 L_ 前缀 | ✅ 0 个（未改名） |

## M8：JSON/脚本/数据/生产入口

**结果：✅ PASS — 非本轮造成**

| 范畴 | 结果 |
|:-----|:----:|
| `02_权威注册表/*.json` | 10 个 JSON 文件均在。git dirty 为 pre-existing，非本轮 rename 造成 |
| `scripts/` | 变更 pre-existing，非本轮 |
| `代码文件/` | 未修改 |
| 生产入口（日报/深度分析/荐股/保护） | 未触及 |

## M9：Git/GitHub

**结果：✅ PASS — 未处理**

- git add/commit/push：❌ 未执行
- GitHub：❌ 未处理

## M10：Formal pipeline

**结果：⚠️ 明示例外 — 不得声称 PASS**

actor/HMAC sign-off 不可用，本次基于 G2 准入单 + 用户逐次确认推进。不等同于 formal pipeline PASS。

---

## G5 综合审计结论

| # | 检查项 | 结果 |
|:-:|:-------|:----:|
| M1 | Manifest 40 条新路径全部存在 | ✅ PASS |
| M2 | Manifest 39 条旧路径（除 redirect 外）均不存在 | ✅ PASS |
| M3 | START_HERE redirect 有效 | ✅ PASS |
| M4 | 过程控制文件允许保留 | ✅ PASS |
| M5 | 旁支 STEP-C 文件不纳入 rename | ✅ PASS |
| M6 | 99_归档 与 RENAME_MANIFEST | ✅ PASS |
| M7 | archive/fulltext 未改名 | ✅ PASS |
| M8 | JSON/脚本/数据/生产入口非本轮造成 | ✅ PASS |
| M9 | Git/GitHub 未处理 | ✅ PASS |
| M10 | Formal pipeline 明示例外 | ⚠️ 例外 |
| | **整体结论** | **✅ G5 PASS** |

**按流程暂停，等待用户确认进入 G6 腰子放行。**
