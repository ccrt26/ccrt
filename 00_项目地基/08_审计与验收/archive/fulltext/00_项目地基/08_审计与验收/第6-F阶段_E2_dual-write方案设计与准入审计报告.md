# 第6-F阶段 — E2 dual-write 方案设计与准入审计报告

> 流程ID: RUN-20260604-065423-700d1d
> 报告日期: 2026-06-04
> 阶段性质: 方案设计与准入审计 — 不改代码、不执行E2、不进入E3
> 维护人: 情墨+玉夜+腰子+阿黑+旧影

---

## 一、阶段定位

1. **第6-F只做方案设计与准入审计**。不改代码，不执行 E2，不进入 E3。
2. 本报告产出的是 **E2 dual-write 接入方案草案**和**第6-F准入审计结果**。
3. 下一阶段必须是 **第6-G / E2 dual-write 执行**（经本方案签批后），由标准流程重新启动。
4. ⛔ 禁止在本阶段修改任何脚本、业务配置、报告文件。
5. ⛔ 禁止直接进入 E2 执行或 E3 guarded-cutover。

---

## 二、E2 dual-write 目标定义

| 维度 | 定义 |
|:-----|:------|
| **旧链路地位** | 旧链路仍是正式输出权威。`daily_orchestrator.py` 的正式日报/sidecar 输出不受影响。 |
| **canonical 输出** | canonical 同步旁路输出到安全目录 `/private/tmp/canonical_dual_write_{date}/`，**不覆盖正式日报/sidecar**。 |
| **比较策略** | E2 只比较（render diff + golden diff），不发布 canonical 结果到正式目录。 |
| **阻断规则** | E2 失败不得影响旧链路正式输出，但 **必须阻断进入 E3**。E2 BLOCK 状态下 E3 禁止启动。 |
| **写入限制** | 正式报告目录禁止出现任何 `*_rendered.*` 文件。 |
| **验证人** | 玉夜 + 新安 + 旧影。 |

### 2.1 E2 与 E1 的关键区别

| 维度 | E1 shadow-only | E2 dual-write |
|:-----|:---------------|:---------------|
| 旧链路 | 不受影响 | 不受影响（仍为正式权威） |
| canonical 是否生成 | ✅ 生成 | ✅ 生成 |
| canonical 是否写入安全目录 | ✅ 写入 | ✅ 写入 |
| 是否跑 render diff | ✅ 总闸门含 render diff | ✅ 独立加强 diff |
| 失败影响 | 仅 WARN，不阻断日报 | 不阻断日报，但**阻断进入 E3** |
| 与旧链路的绑定 | 完全独立 | 同步触发（日报完成后自动执行） |
| 验证级别 | 新安 | 玉夜 + 新安 + 旧影 |

---

## 三、当前资产审计

### 3.1 验收记录

| 资产 | 存在 | G5 结论 |
|:-----|:----:|:--------|
| 第6-A验收记录 | ✅ | ✅ PASS |
| 第6-B验收记录 | ✅ | ✅ PASS |
| 第6-C验收记录 | ✅ | ✅ PASS |
| 第6-D验收记录 | ✅ | ✅ PASS |
| 第6-E验收记录 | ✅ | ✅ PASS |

### 3.2 切换策略资产

| 资产 | 存在 | 说明 |
|:-----|:----:|:------|
| `canonical_cutover_contract.md` | ✅ | 准入条件 + E1/E2/E3 + 回滚 + 角色责任 |
| `canonical_cutover_runbook.md` | ✅ | 执行步骤 + 失败处理 + 回滚 + 禁止操作 |

### 3.3 代码资产

| 资产 | 存在 | 说明 |
|:-----|:----:|:------|
| `scripts/run_canonical_shadow.py` | ✅ | E1 执行器 |
| `scripts/check_canonical_pipeline_gate.py` | ✅ | 发布前总闸门（4个子闸门） |
| `scripts/render_report_from_canonical.py` | ✅ | 含正式目录阻断 |
| `scripts/check_canonical_render_diff.py` | ✅ | 渲染产物 diff |
| `代码文件/tools/daily_orchestrator.py` | ✅ | 已有 `--canonical-shadow` 参数 |
| `scripts/build_canonical_report.py` | ✅ | canonical 构建 |

### 3.4 安全阻断审计

| 检查项 | 结果 |
|:-------|:-----|
| render 脚本禁止写入正式目录 | ✅ `ERROR: 禁止写入正式报告目录` |
| shadow runner render-dir 阻断 | ✅ 正式目录→BLOCK exit=2 |
| orchestrator shadow 不影响正式 exit code | ✅ 仅 WARN |
| skip_data_check 语义不变 | ✅ 已验证 |
| 正式目录无 rendered 残留 | ✅ find 0 结果 |

**审计结论：** 资产完整，具备进入 E2 方案设计的基础条件。

---

## 四、E2 执行方案草案

> ⚠️ **本草案仅用于第6-F方案审计，不在此阶段执行。** 第6-G启动后方可实施。

### 4.1 允许修改范围（第6-G执行时）

| 文件 | 修改类型 | 说明 |
|:-----|:---------|:------|
| `代码文件/tools/daily_orchestrator.py` | 增加参数 | `--canonical-dual-write` 参数 |
| `scripts/` | 新增 | `run_canonical_dual_write.py` |

### 4.2 新增脚本概要

**`scripts/run_canonical_dual_write.py`（仅方案，不本阶段实现）**

命令格式：
```bash
python3 scripts/run_canonical_dual_write.py --date {date} --canonical-dir /private/tmp/canonical_reports_{date} --dual-dir /private/tmp/canonical_dual_write_{date}
```

执行顺序：
1. 构建 canonical → `build_canonical_report.py`
2. 渲染 canonical → `render_report_from_canonical.py` → 输出到 dual-dir
3. 跑 render diff → `check_canonical_render_diff.py` — 比较 dual-dir 与正式报告目录
4. 跑总闸门 → `check_canonical_pipeline_gate.py`

规则：
- dual-write 输出目录必须是 `/private/tmp/canonical_dual_write_{date}`
- 正式报告目录禁止写入 `*_rendered.*`
- 正式输出仍由旧链路产生
- canonical 输出只用于 diff/gate
- diff BLOCK → 阻断进入 E3（不阻断日报）

### 4.3 orchestrator 参数草案

`daily_orchestrator.py` 增加 `--canonical-dual-write`：
- 在正式日报 signal 写入后，调用 `run_canonical_dual_write.py`
- shadow-only 和 dual-write 共存时，后运行的 dual-write 覆盖 shadow 结果
- dual-write 失败只记 WARN，不改变正式 exit code
- 日志明确输出 `DUAL_WRITE_CANONICAL: PASS` 或 `DUAL_WRITE_CANONICAL: BLOCK`

---

## 五、第6-G 准入条件

第6-G（E2 dual-write 执行）启动前，**必须全部满足**：

| # | 准入项 | 检查方法 |
|:--|:-------|:---------|
| G1 | 第6-A~第6-F 均通过 | `test -f` 6份验收记录 |
| G2 | 第6-E shadow runner 对目标日期 PASS | `python3 scripts/run_canonical_shadow.py --date {target}` → exit 0 |
| G3 | `canonical_pipeline_gate` 对目标日期 PASS | `python3 scripts/check_canonical_pipeline_gate.py --date {target}` → exit 0 |
| G4 | P0-A baseline PASS | `python3 scripts/check_baseline_authority.py --all --date {target}` → exit 0 |
| G5 | P0-B numeric 对目标日期无 P0 BLOCK | `python3 scripts/check_numeric_source_consistency.py --all --date {target}` |
| G6 | P0-C freshness PASS | `python3 scripts/check_freshness_degradation.py --all --date {target}` → exit 0 |
| G7 | P0-D MD/sidecar 对目标日期 PASS 或仅登记P1 | `python3 scripts/check_md_sidecar_consistency.py --all --date {target}` |
| G8 | P5 lineage PASS | `python3 scripts/check_report_authority_lineage.py --all --date {target}` → exit 0 |
| G9 | runtime gate PASS | `python3 scripts/check_runtime_entry_authority.py --all` → exit 0 |
| G10 | 腰子确认 E2 不改变金融口径 | 腰子签章输出 |

---

## 六、E2 失败处理

| 失败场景 | 动作 |
|:---------|:------|
| E2 diff BLOCK | **不进入 E3**，检查映射规则或 canonical 数据 |
| canonical pipeline BLOCK | **不进入 E3**，按子闸门逐项排查 |
| 正式目录出现 `*_rendered.*` 残留 | **BLOCK**，立即删除，审核脚本权限 |
| `source_snapshot` 缺失 | **BLOCK** 或登记 P1，不得自动放行 |
| 用户发现数字/日期/sidecar 不一致 | **stop-the-line**，立即回滚到旧链路 |
| 旧链路正常、E2 全 FAIL | 旧链路继续，**阻断 E3 入口** |

**核心原则：** E2 失败不得影响旧链路正式输出，但必须阻断进入 E3。

---

## 七、后续第6-G 派单草案

> ⚠️ **此草案仅供后续使用，第6-F不得执行。**

**派单：第6-G / E2 dual-write 执行**

修改范围：
1. 新增 `scripts/run_canonical_dual_write.py`
2. `代码文件/tools/daily_orchestrator.py` 增加 `--canonical-dual-write` 参数
3. 新增 `00_项目地基/08_审计与验收/第6-G阶段_E2_dual-write接入验收记录.md`

禁止修改：
- 正式日报/sidecar/HTML/PDF
- 重点股票/股票报告/
- `canonical_cutover_contract.md` / `canonical_cutover_runbook.md`

执行步骤：
1. 实现 `run_canonical_dual_write.py`
2. orchestrator 增加 `--canonical-dual-write`
3. 全池 PASS 验证
4. 缺文件/多余文件/正式目录阻断反向测试
5. G5 复查 + 验收记录

---

## 八、角色输出证据

| 角色 | 状态 | 说明 |
|:-----|:-----|:------|
| **阿黑** | ✅ 已唤醒 | 意图判定为 NEW_REQUIREMENT，分发至情墨，第6-F阶段路由 |
| **情墨** | ✅ 已唤醒 | E2 架构方案设计 — 确认 dual-write 接入边界，输出本报告 |
| **玉夜** | ✅ 已唤醒 | 确认 E2 diff 准入标准合理，数据事实验证路径清晰 |
| **腰子** | ✅ 已唤醒 | 确认第6-F不改代码、不执行E2/E3；确认E2阶段不改变金融口径（正式日报仍由旧链路产生）；结论 PASS |
| **旧影** | ✅ 已唤醒 | G5 独立复查通过，全部资产审计完整，约束合规 |

**跳过角色说明：**

| 角色 | 跳过理由 |
|:-----|:---------|
| 红结 | 本阶段不写代码 |
| 新安 | 本阶段不写代码 |
| 山猫 | 不改策略/事件 |
| 信鸽 | 不改事件 |
| 流金 | 不改风控规则 |
| 青山 | 不改策略 |

---

## 九、越权检查

| 检查项 | 结论 |
|:-------|:-----|
| 本阶段仅新增1个审计报告 | ✅ |
| 未修改代码 | ✅ 0行 |
| 未修改正式报告目录 | ✅ |
| 未进入第6-G | ✅ 阀门 CLOSED |
| 未执行 E2 | ✅ |
| 未进入 E3 | ✅ |
| 角色输出证据完整 | ✅ 5角色唤醒 |
| 后续第6-G仅作为草案 | ✅ 标注"第6-F不得执行" |

---

## 十、阀门声明

> ⛔ **阀门状态: CLOSED**
>
> 第6-F仅完成 E2 dual-write 方案设计与准入审计。
> 不改代码、不执行 E2、不进入 E3。
> 下一阶段：第6-G / E2 dual-write 执行（需重新走标准流程启动）。
