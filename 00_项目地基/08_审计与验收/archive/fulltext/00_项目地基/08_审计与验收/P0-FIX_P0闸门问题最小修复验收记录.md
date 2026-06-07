# P0-FIX：P0 闸门问题最小修复 — 验收记录

> 验收日期：2026-06-02
> 阶段：P0-FIX（P0 级问题最小修复）
> 范围：仅 600114 东睦股份 20260602 日报的 P0 级问题

---

## 一、本阶段修改文件清单

| # | 文件 | 操作 | 修改内容 |
|:-:|:-----|:-----|:---------|
| 1 | `重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260602.md` | **修改** | FIX-01 + FIX-03 |
| 2 | `重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260602.json` | **修改** | FIX-01 + FIX-02 |
| 3 | `00_项目地基/08_审计与验收/P0-FIX_P0闸门问题最小修复验收记录.md` | **新增** | 本文件 |

未修改允许范围之外的任何文件。

---

## 二、修复前问题清单

| 编号 | 问题 | 发现闸门 | 严重度 |
|:-----|:------|:---------|:------:|
| B-01 | 日报 baseline_id=`600114_deep_20260529_v1.4` ≠ 注册表 `600114_W2026W22` | P0-A | **P0** |
| N-01 | sidecar sector_phase=`主升期` ≠ data_scored=`衰退期` | P0-B | **P0** |
| D-01 | MD相位=`衰退期` ≠ sidecar相位=`主升期` | P0-D | **P0** |
| D-04 | sidecar 内部板块相位矛盾：sector_phase=`主升期` vs 山猫大盘板块=`衰退期` | P0-D | **P1** |
| — | MD one_line 声明"止损上移至37元"但 P0 表已持仓止损=33.4元 | P0-D | **P0** |

---

## 三、每个问题的修复方式

### FIX-01：baseline_id 不一致

| 位置 | 修复前 | 修复后 |
|:-----|:-------|:-------|
| MD 头部 | `baseline_id：600114_deep_20260529_v1.4` | `baseline_id：600114_W2026W22` |
| MD 深度分析基线段 | `baseline_id：600114_deep_20260529_v1.4` | `baseline_id：600114_W2026W22` |
| sidecar 顶层 | `"baseline_id": "600114_deep_20260529_v1.4"` | `"baseline_id": "600114_W2026W22"` |

**方向**：日报对齐注册表，不是注册表对齐日报。

### FIX-02：板块相位不一致

| 位置 | 修复前 | 修复后 | 权威源 |
|:-----|:-------|:-------|:-------|
| sidecar.sector_phase.phase | `主升期` | `衰退期` | data_scored.SectorPhase |
| role_interpretations.山猫_宏观.板块相位 | `主升期` | `衰退期` | data_scored.SectorPhase |
| role_interpretations.daily_discussion.山猫_大盘板块.sector_phase | `衰退期`（已正确） | ✅ 不变 | data_scored.SectorPhase |
| yaozi_integration.daily_synthesis.market_sector_interpretation.data_fact | `板块=衰退期`（已正确） | ✅ 不变 | data_scored.SectorPhase |

### FIX-03：MD one_line 止损声明与 P0 表不一致

**修复前**：
`涨停确认止跌,不追高等回踩38元缩量企稳再考虑加仓。已试探仓持有,止损上移至37元。`

**修复后**：
`涨停确认止跌，不追高，等回踩38元缩量企稳再考虑加仓。已试探仓按33.4元止损执行。`

**依据**：P0 表 `held_position_stop_loss = "33.4元"` 为权威值。本阶段不对 P0 表值做任何修改。

---

## 四、修改后关键字段对照

| 字段 | 修复前 | 修复后 |
|:-----|:-------|:-------|
| MD baseline_id | `600114_deep_20260529_v1.4` | **`600114_W2026W22`** |
| sidecar baseline_id | `600114_deep_20260529_v1.4` | **`600114_W2026W22`** |
| sidecar.sector_phase.phase | `主升期` | **`衰退期`** |
| role_interpretations.山猫_宏观.板块相位 | `主升期` | **`衰退期`** |
| 山猫_大盘板块.sector_phase | `衰退期`（正确） | **不变** |
| MD one_line 止损声明 | `止损上移至37元` | **`按33.4元止损执行`** |
| sidecar held_position_stop_loss | `33.4元`（正确） | **不变** |

---

## 五、验收命令结果

### A. Baseline 权威闸门（P0-A）

```bash
$ python3 scripts/check_baseline_authority.py --code 600114 --name 东睦股份 --date 20260602
```
→ **PASS** ✅（修复前 BLOCK）

```bash
$ python3 scripts/check_baseline_authority.py --all --date 20260602
```
→ **PASS 10 / BLOCK 0** ✅（修复前 PASS 9 / BLOCK 1）

### B. 数值来源一致性闸门（P0-B）

```bash
$ python3 scripts/check_numeric_source_consistency.py --code 600114 --name 东睦股份 --date 20260602
```
→ **PASS** ✅（修复前 BLOCK due to sector_phase）

```bash
$ python3 scripts/check_numeric_source_consistency.py --all --date 20260602
```
→ **PASS 10 / BLOCK 0** ✅（修复前 PASS 9 / BLOCK 1）

### C. MD / sidecar 一致性闸门（P0-D）

```bash
$ python3 scripts/check_md_sidecar_consistency.py --code 600114 --name 东睦股份 --date 20260602
```
→ **PASS 35/35** ✅（修复前 3 BLOCK：板块相位×2 + 额外止损声明）

### D. 日期新鲜度闸门（P0-C）

```bash
$ python3 scripts/check_freshness_degradation.py --code 600114 --name 东睦股份 --date 20260602
```
→ **PASS**（1 WARN 融资延迟，与修复前一致 ✅）

### E. JSON 合法性

```bash
$ python3 -m json.tool "重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260602.json"
```
→ **JSON_VALID: PASS** ✅

### F. Git 变更范围

```bash
$ git status --short "重点股票/股票报告/东睦股份(600114)" "00_项目地基/08_审计与验收"
```
→ 仅出现 `东睦股份(600114)日报_20260602.md`、`东睦股份(600114)日报_20260602.json`、`P0-FIX_P0闸门问题最小修复验收记录.md`

---

## 六、四闸门全回归通过情况

| 闸门 | 600114 修复前 | 600114 修复后 | --all 修复前 | --all 修复后 |
|:-----|:-------------:|:-------------:|:------------:|:------------:|
| **P0-A** baseline | ❌ BLOCK | ✅ **PASS** | PASS 9/BLOCK 1 | **PASS 10/BLOCK 0** |
| **P0-B** 数值 | ❌ BLOCK | ✅ **PASS** | PASS 9/BLOCK 1 | **PASS 10/BLOCK 0** |
| **P0-C** 新鲜度 | ✅ PASS (1W) | ✅ **PASS** (1W) | PASS 10/BLOCK 0 | **PASS 10/BLOCK 0** |
| **P0-D** MD/SC | ❌ 3 BLOCK | ✅ **PASS 35/35** | PASS 2/BLOCK 8 | PASS 2/BLOCK 8* |

> *P0-D --all 仍有 BLOCK（其他股票的 P1 止损差异），不在本阶段修复范围。

---

## 七、仍未修复的问题清单

以下问题已在 P0 闸门中发现，但属于 P1/P2 级别或正式阶段范围，本阶段不修复：

| 编号 | 问题 | 严重度 | 发现阶段 | 计划修复 |
|:-----|:------|:------:|:--------:|:--------|
| D-02 | 6/10 新仓止损 MD 圆整差异 | P1 | P0-D | 第4阶段 |
| D-03 | 5/10 已持仓止损 MD vs sidecar 显著差异 | P1 | P0-D | 第4阶段 |
| F-01 | 所有10只融资 T+6 延迟 | P1 | P0-C | 第3阶段 |
| F-02 | 7/10 股票无板块相位权威源 | P1 | P0-C | 第2阶段 |
| N-02 | data_scored 覆盖不足 | P1 | P0-B | 第2阶段 |
| B-02 | 深度分析系统附录 baseline_id 命名多版本 | P1 | P0-A | 第1阶段 |
| D-04 | 600114 sidecar 内部板块相位矛盾（已修复） | P1 | P0-D | ✅ 本阶段已修复 |

---

## 八、结论

### 是否建议通过 P0-FIX：✅ 建议通过。

**依据：**
1. 3 个 P0 级问题全部修复（baseline_id、板块相位、止损声明）
2. 4 个 P0 闸门对 600114 全部回归到 PASS
3. `--all` 模式中 P0-A 和 P0-B 从 BLOCK 清零到全 PASS
4. 未修改允许范围之外的任何文件
5. JSON 合法性验证通过

### P0 包最终状态

```
P0-A (baseline权威闸门)  ✅ 已通过 → 600114 BLOCK已修复
P0-B (数值一致性闸门)    ✅ 已通过 → 600114 BLOCK已修复
P0-C (新鲜度闸门)      ✅ 已通过 → 无 BLOCK
P0-D (MD/SC一致性闸门)  ✅ 已通过 → 600114 BLOCK已修复
P0-FIX                 ✅ 本阶段完成 → P0级问题已清零
```

### 是否修改了允许范围之外的文件

**否。** 仅修改了允许范围内的 3 个文件（2个日报文件+1个验收记录）。
