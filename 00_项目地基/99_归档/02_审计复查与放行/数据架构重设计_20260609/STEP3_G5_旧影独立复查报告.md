# STEP3 G5 旧影独立复查报告 — UnifiedDataSource 与旧入口影子接入

> **复查角色**：旧影
> **复查阶段**：G5
> **流程编号**：F-ARCH + F-DATA + F-GATE
> **复查日期**：2026-06-09
> formal pipeline actor/HMAC：未通过，继续作为明示例外
> 本次不等同于 formal pipeline PASS
> 本报告不得代替 G6 腰子放行

---

## 一、复查范围

旧影独立复查了以下交付物、代码和配置：

### 1.1 方案与交付报告

| # | 文件 | 版本 |
|:-:|:-----|:-----|
| 1 | `STEP3_G2_UnifiedDataSource影子接入实施方案.md` | 补修版 |
| 2 | `STEP3_UnifiedDataSource影子接入报告.md` | G3/G4 |
| 3 | `STEP3_修改文件清单.md` | G3/G4 |
| 4 | `STEP3_验收命令结果.md` | G3/G4（证据补修） |
| 5 | `STEP3_闸门同步验证报告.md` | G3/G4（证据补修） |
| 6 | `STEP3_GoldenDiff或ShadowDiff报告.md` | G3/G4 |
| 7 | `STEP3_旧入口适配矩阵.md` | G3/G4 |
| 8 | `STEP3_不切生产证明.md` | G3/G4 |

### 1.2 代码文件

| # | 文件 | 操作 |
|:-:|:-----|:-----|
| 9 | `代码文件/数据/unified_data_source.py` | 新增，G5 不修改 |
| 10 | `tests/test_d04_fallback.py` | 新增/补修，G5 不修改 |
| 11 | `scripts/run_shadow_diff.py` | 新增，G5 不修改 |
| 12 | `scripts/migrate_historical_kline.py` | 新增，G5 不修改 |

### 1.3 审计线检查

| # | 检查项 |
|:-:|:-------|
| 13 | dirty baseline（`cached_data_source.py` / `daily_workflow.py` pre-existing dirty） |
| 14 | formal pipeline actor/HMAC 例外记录 |
| 15 | numeric 闸门 BLOCK 是否为 STEP3 原因 |
| 16 | 禁止范围核验（日报入口未接入 UDS、l2_cache.db 未创建、GitHub 未处理） |

---

## 二、复查方法

旧影使用以下方法独立验证每项内容：

| 检查项 | 方法 |
|:-------|:------|
| 交付物完整性 | 确认 7 份 + G2 方案文件全部存在 |
| kline_l2 闸门逻辑 | 直接读取 `scripts/check_numeric_source_consistency.py` line 750-762 和 `scripts/check_freshness_degradation.py` line 220-230 源代码 |
| numeric BLOCK 溯源 | 读取 `data_scored.json` 中 600114 的 SectorPhase（`"主升调整"`），比对报告描述 |
| dirty baseline | grep 验证 `cached_data_source.py` 和 `daily_workflow.py` 中无 UDS 引用（均为 0） |
| formal pipeline 状态 | 读取 `.claude/pipeline_active.json` |
| l2_cache.db | `test ! -e` 物理文件确认 |
| 交付物存在性 | 逐一 `test -f` 确认全部 7 份报告 |

---

## 三、逐项复查结论

### 3.1 交付物完整性 — ✅ PASS

全部 7 份 STEP3 交付报告存在，内容完整，签注了流程编号、阶段门、formal pipeline 例外说明。

### 3.2 kline_l2 闸门逻辑代码审计 — ✅ PASS

旧影独立读取了闸门脚本源代码，确认：

**`scripts/check_numeric_source_consistency.py`（line 752-758）：**
```python
enabled = kl2.get("enabled", False)
phase = kl2.get("phase", 0)

if not enabled or phase < 2:
    return make_check(field, ..., "PASS",
        "kline_l2: SKIP (enabled={enabled}, phase={phase}) — Phase 2 前跳过 L2 数值检查")
```

**`scripts/check_freshness_degradation.py`（line 222-229）：**
```python
enabled = kl2.get("enabled", False)
phase = kl2.get("phase", 0)

if not enabled or phase < 2:
    return make_check(..., "PASS",
        "kline_l2 enabled={enabled} phase={phase} — Phase 2 前跳过 L2 新鲜度检查")
```

**判定**：`enabled=False, phase=2` 时两个闸门均正确返回 `PASS/SKIP`，不检查 L2 数据、不触发 L2 读取、不 BLOCK 当日报告。该逻辑与 G2 方案一致，且在 STEP2 已完成适配，STEP3 未修改闸门代码。

### 3.3 Numeric 闸门整体 BLOCK 溯源 — ✅ 确认非 STEP3 原因

旧影逐层审计了每次 BLOCK 的根因：

| 运行日期 | 整体结果 | BLOCK 根因 | 是否 STEP3 导致 |
|:---------|:---------|:-----------|:----------------|
| 20260609 | ❌ BLOCK | `东睦股份(600114)日报_20260609.json`/`.md` **不存在**（当日未生成日报） | ❌ 否 |
| 20260604 | ❌ BLOCK | `sector_phase.phase` 不一致：sidecar 写 `"潜伏期"`，data_scored 真实值 `"主升调整"` | ❌ 否 |

**kline_l2.numeric 子项在所有运行中均为 ✅ PASS/SKIP。**

**data_scored.json 系统值确认**：600114 在 Recommendations 和 AllStocks 两个桶中 `SectorPhase` 均为 `"主升调整"`。sidecar 中的 `"潜伏期"` 是日报 sidecar 数据字段写入值，与 UnifiedDataSource / L2 适配完全无关。

**numeric 闸门非 kline_l2 子项的 BLOCK 与 STEP3 无因果关系。**

### 3.4 Freshness 闸门 L2 子项 — ✅ PASS

| 运行日期 | 整体结果 | kline_l2.freshness 子项 |
|:---------|:---------|:------------------------|
| 20260604 | ✅ PASS（exit=0） | ✅ **PASS/SKIP** — Phase 2 前跳过 L2 新鲜度检查 |
| 20260609 | ❌ BLOCK（sidecar 缺失提前退出） | **未执行** — 因日报 sidecar 不存在提前 BLOCK |

**判定**：freshness 闸门在有效日报日期下整体 PASS，kline_l2 子项在可执行时正确返回 SKIP。

### 3.5 Dirty Baseline 核实 — ✅ PASS

| 文件 | 旧影验证 | 结论 |
|:-----|:---------|:------|
| `代码文件/lib/cached_data_source.py` | grep "UnifiedDataSource"=0, "unified_data_source"=0 | ✅ 无新增引用 |
| `代码文件/每日荐股/scripts/daily_workflow.py` | grep "UnifiedDataSource"=0, "unified_data_source"=0 | ✅ 无新增引用 |
| pre-existing dirty | 报告中如实记录了 commit 和行数 | ✅ 未被覆盖 |

### 3.6 Formal Pipeline 例外说明 — ✅ PASS

| 检查项 | 结果 |
|:-------|:------|
| `RUN-20260609-012906-d11109` 仍停留在 design | ✅ 确认 |
| actor/HMAC 无法通过 sign_off/--advance | ✅ 确认 |
| 所有 7 份交付报告是否标注了例外 | ✅ 全部标注 |
| 本次是否不等同于 formal pipeline PASS | ✅ 明确 |
| 是否接受接力包例外 | ✅ 接受 — 基于用户授权的流程确认 |

### 3.7 不切生产证明 — ✅ PASS

| 隔离项 | 旧影验证 |
|:-------|:---------|
| l2_cache.db 未创建 | ✅ `test ! -e` 确认不存在 |
| UDS 不调 API | ✅ 代码审计仅读本地缓存 |
| shadow 日志不写入正式报告 | ✅ 路径 `l2_cache/shadow_diff_log.jsonl`，由 `.gitignore` 排除 |
| 正式日报入口未引用 UDS | ✅ 全部 grep 确认 |

### 3.8 Shadow diff 有效性 — ✅ PASS

shadow diff 日志文件 `代码文件/数据/l2_cache/shadow_diff_log.jsonl` 存在且已含有效记录。`scripts/run_shadow_diff.py --code 600114` 输出 close/volume/change_pct 完全一致（0 差异）。确认独立 shadow 脚本可作为第一轮主验证入口正常运行。

### 3.9 10 接口格式— ✅ PASS

| 接口 | data_source | status | 结果 |
|:-----|:------------|:-------|:-----|
| `get_quote` | `l1_live` | PASS | ✅ |
| `get_kline`（60天） | `l1_live` | PASS | ✅ |
| `get_score_history` | `degraded` | SKIP | ✅ |
| `get_financials` | `degraded` | SKIP | ✅ |
| `get_macro` | `degraded` | SKIP | ✅ |
| `compare_current_vs_historical` | `not_available_in_step3` | SKIP | ✅ |
| `compute_factor_ic` | `not_available_in_step3` | SKIP | ✅ |
| `get_max_drawdown` | `not_available_in_step3` | SKIP | ✅ |
| `get_volatility_percentile` | `not_available_in_step3` | SKIP | ✅ |
| `export_factor_panel` | `not_available_in_step3` | SKIP | ✅ |

两类降级口径正确：A 类 `degraded/SKIP`，B 类 `not_available_in_step3/SKIP`。`compare_current_vs_historical` 未现场计算 mean/std/percentile。`compute_factor_ic` 未现场计算 IC。

### 3.10 编译与环境 — ✅ PASS

编译 6/6 PASS（`PYTHONPYCACHEPREFIX` 规避 macOS pycache 权限）。fallback 测试 5/5 PASS。K 线收敛 dry-run 4200 行不写 DB。

---

## 四、WARN 项

| # | WARN 项 | 归属 | 建议 |
|:-:|:--------|:-----|:------|
| 1 | `sector_phase.phase` 不一致导致 numeric 闸门整体 BLOCK（sidecar="潜伏期"，data_scored="主升调整"） | **非 STEP3 问题** | 由玉夜后续以 F-DATA/F-FIX 单独排查 |
| 2 | 20260609 日报 sidecar/MD 不存在导致 freshness/numeric 原日期整体验收 BLOCK | **非 STEP3 问题** | 后续在有日报文件的日期或日报链路恢复后重跑 |
| 3 | l2_cache.db 未创建，L2 依赖接口全部 degraded/not_available_in_step3 | STEP3 设计内允许状态 | 创建 DB 需用户单独授权，先 dry-run 后实写 |
| 4 | formal pipeline actor/HMAC 未通过，`RUN-20260609-012906-d11109` 仍停 design | 流程工具链例外 | G6 前继续明示，不得伪造 sign-off |

---

## 五、结论

| 复查维度 | 结论 |
|:---------|:-----|
| 交付物完整性（7 份） | ✅ PASS |
| kline_l2 闸门逻辑代码审计 | ✅ PASS |
| numeric 闸门整体 BLOCK 非 STEP3 原因 | ✅ 确认 |
| freshness 闸门 L2 子项（有效日期） | ✅ PASS/SKIP |
| dirty baseline 核实 | ✅ PASS |
| formal pipeline 例外说明 | ✅ PASS |
| 不切生产证明 | ✅ PASS |
| Shadow diff 有效性 | ✅ PASS |
| 10 接口格式与两类降级口径 | ✅ PASS |
| 编译与 fallback 测试 | ✅ PASS |
| 整体（含 WARN） | ✅ 建议通过（WARN 可接受，非 STEP3 原因） |

### 总体结论

**建议通过（WARN 可接受，非 STEP3 原因）。**

**理由**：

1. **代码层通过** — 编译检查通过；10 个 UnifiedDataSource 接口返回格式正确；get_kline degraded/WARN 口径正确；两类（A/B）降级口径正确；fallback 测试 5/5 PASS；shadow diff ALL PASS；l2_cache.db 未创建；未切生产；未修改日报/深度分析正式入口。

2. **L2/UDS 闸门子项通过** — numeric 的 `kline_l2.numeric` 子项在 20260604/20260609 均 PASS/SKIP；freshness 的 `kline_l2.freshness` 子项在有效日期 20260604 PASS/SKIP；20260609 freshness 因 sidecar 缺失提前 BLOCK，kline_l2.freshness 未执行。上述行为符合 Phase 2 前不阻断设计。

3. **整体 BLOCK 原因不是 STEP3** — 20260609 闸门整体 BLOCK 原因是当日日报 sidecar/MD 不存在；20260604 numeric 整体 BLOCK 原因是 `sector_phase.phase` 中 sidecar 为"潜伏期"而 data_scored 为"主升调整"。以上均非 STEP3 UnifiedDataSource / L2 / UDS 适配导致。

4. **dirty baseline 未被覆盖** — `cached_data_source.py` / `daily_workflow.py` 等 pre-existing dirty 未被覆盖、未回滚、未新增 UDS 引用。

5. **formal pipeline 例外已明示** — actor/HMAC 未通过，本次基于用户授权接力包流程例外，不等同于 formal pipeline PASS，不得伪造 sign-off。

---

## 六、暂停点

```
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
⛔
⛔   STEP3 G5 独立复查报告已落盘。
⛔
⛔   总体结论：建议通过（WARN 可接受，非 STEP3 原因）。
⛔
⛔   当前不得自动进入 G6。
⛔   等待用户复查并明确确认是否进入 G6 腰子放行阶段。
⛔
⛔   阿黑不得代签腰子结论。
⛔   执行模型不得代签腰子结论。
⛔   运行时入口不得直接读 UDS。
⛔
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
```

---

*复查角色：旧影 | 复查阶段：G5 | 流程编号：F-ARCH + F-DATA + F-GATE | 日期：2026-06-09*
*formal pipeline actor/HMAC：未通过，继续作为明示例外 | 本次不等同于 formal pipeline PASS*
*本报告不得代替 G6 腰子放行*
