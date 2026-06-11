# STEP3 G6 腰子放行单 — UnifiedDataSource 与旧入口影子接入

> **流程编号**：F-ARCH + F-DATA + F-GATE
> **阶段门**：G6（放行归档）
> **日期**：2026-06-09
> formal pipeline actor/HMAC：未通过，继续作为明示例外
> 本放行不等同于 formal pipeline PASS

---

## 一、G5 前置确认

| 确认项 | 结论 |
|:-------|:------|
| G5 旧影独立复查 | ✅ **建议通过（WARN 可接受，非 STEP3 原因）** |
| 报告文件 | `STEP3_G5_旧影独立复查报告.md` |
| 复查日期 | 2026-06-09 |

## 二、G6 确认事实

### 2.1 代码层验证

| 维度 | 结果 |
|:-----|:------|
| 编译检查 | ✅ 6/6 PASS（PYTHONPYCACHEPREFIX 规避 macOS pycache 权限） |
| UnifiedDataSource 10 接口格式 | ✅ 10/10 统一 dict 格式 |
| get_kline degraded 口径 | ✅ L1 不足 + L2 不存在 → degraded/WARN |
| A 类降级口径（degraded） | ✅ get_macro/macro 等正确返回 |
| B 类降级口径（not_available_in_step3） | ✅ compute_factor_ic/compare 等正确返回 |
| fallback 测试 | ✅ 5/5 PASS（含严格断言 + B 类覆盖） |
| shadow diff | ✅ ALL PASS（close/volume/change_pct 0 差异） |
| K 线收敛 dry-run | ✅ 4200 行，不写 DB |
| l2_cache.db 未创建 | ✅ |
| 不切生产 | ✅ |

### 2.2 L2/UDS 闸门子项

| 闸门 | 日期 | kline_l2 子项 | 结果 |
|:-----|:-----|:--------------|:------|
| freshness --tier l2 | 20260604 | kline_l2.freshness | ✅ PASS/SKIP |
| numeric | 20260604 | kline_l2.numeric | ✅ PASS/SKIP |
| numeric | 20260609 | kline_l2.numeric | ✅ PASS/SKIP |
| freshness --tier l2 | 20260609 | kline_l2.freshness | ⚠️ 未执行（sidecar 缺失提前 BLOCK） |

### 2.3 WARN 项（均非 STEP3 原因）

| # | WARN 项 | 归属 | 处理方式 |
|:-:|:--------|:-----|:---------|
| 1 | sector_phase.phase 不一致导致 numeric 闸门整体 BLOCK（sidecar="潜伏期", data_scored="主升调整"） | 非 STEP3 | 后续 F-DATA/F-FIX 单独处理 |
| 2 | 20260609 日报 sidecar/MD 不存在导致 freshness/numeric 原日期 BLOCK | 非 STEP3 | 后续日报链路修复时处理 |
| 3 | l2_cache.db 未创建，L2 依赖接口全部 degraded/not_available_in_step3 | 设计内状态 | 创建需用户单独授权 |
| 4 | formal pipeline actor/HMAC 未通过，RUN-20260609-012906-d11109 仍停 design | 流程工具链例外 | 继续明示，不得伪造 |

### 2.4 不切生产证明

| 隔离项 | 状态 |
|:-------|:------|
| 日报/深度分析正式入口 | ✅ 未修改 |
| cached_data_source.py | ✅ 未接入 UDS |
| daily_workflow.py | ✅ 未接入 UDS |
| daily_orchestrator.py | ✅ 未引用 UDS |
| l2_cache.db | ✅ 未创建 |
| tushare/API 调用 | ✅ 未调用 |
| data_full.json / kline_cache / fund_flow_cache | ✅ 未修改 |
| D04 能力扩充 | ✅ C-D04-0001 未新增 consumed_by |

### 2.5 Formal Pipeline 例外

| 项 | 状态 |
|:---|:------|
| RUN-20260609-012906-d11109 当前阶段 | `design`（停留） |
| actor/HMAC | 未通过 |
| 本次流程基础 | 用户授权接力包流程 |
| 是否等同 formal pipeline PASS | ❌ 否 |
| 是否伪造 sign-off | ❌ 否 |

---

## 三、腰子放行意见区

> 腰子已在 G6 阶段输出放行结论，以下为正式落盘记录。

| 字段 | 内容 |
|:-----|:------|
| **放行角色** | **腰子**（金融业务负责人） |
| **放行范围** | STEP3 UnifiedDataSource 影子接入；独立 shadow diff；fallback 测试；闸门 kline_l2 Phase 2 前不阻断验证；不切生产证明 |
| **意见** | **✅ 同意放行** |
| **日期** | **2026-06-09** |

### 附加条件

1. **不得自动进入 STEP4** — 需用户新指令或新建会话启动。
2. **l2_cache.db 创建需用户单独授权**，且必须先 `--dry-run` 验证。
3. **sector_phase.phase 不一致**需后续以 `F-DATA/F-FIX` 流程单独处理（非 STEP3 问题）。
4. **20260609 日报 sidecar/MD 缺失**需后续日报链路或数据修复阶段处理（非 STEP3 问题）。
5. **formal pipeline actor/HMAC** 需继续作为流程工具链例外记录，不得伪造 sign-off。
6. **UnifiedDataSource 不得切生产**，guarded cutover 需另起阶段并用户确认。
7. **D04 不得扩展为分析/回测/交易/投资建议系统**，保持 NOT-01~NOT-10 边界。

---

## 四、用户确认区

```
【】接受 STEP3 G6 放行
【】不接受，需修正（请说明）

用户签字：
日期：
```

---

## 五、暂停声明

```
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
⛔
⛔   STEP3 G6 腰子放行单已落盘。
⛔   腰子意见：同意放行（附条件）。
⛔
⛔   用户确认前 STEP3 不正式收口。
⛔   当前不得自动进入 STEP4。
⛔   sector_phase 清理需另起 F-DATA/F-FIX。
⛔   20260609 日报 sidecar/MD 缺失需另起修复。
⛔   formal pipeline actor/HMAC 继续明示例外。
⛔
⛔   等待用户决定：
⛔     1. 是否接受 STEP3 G6 放行；
⛔     2. 是否另起 F-DATA/F-FIX 清理 WARN 项；
⛔     3. 是否新会话启动 STEP4。
⛔
⛔   阿黑不得自动进入 STEP4。
⛔   阿黑不得代签腰子结论。
⛔   执行模型不得代签腰子结论。
⛔
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
```

---

*流程编号：F-ARCH + F-DATA + F-GATE | 阶段门：G6*
*formal pipeline actor/HMAC：未通过，继续作为明示例外 | 本次不等同于 formal pipeline PASS*
*腰子：同意放行（附条件）| 日期：2026-06-09*
