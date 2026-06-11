# canonical 生产切换策略冻结契约

> 版本: 1.0 | 生效日期: 2026-06-04 | 维护人: 情墨+玉夜+腰子+阿黑
>
> 第6-D阶段产物 — 只冻结准入条件与回滚规则，不执行切换。

---

## 一、定位

1. canonical 生产切换**不是第6-D执行内容**。
2. 第6-D只冻结第6-E之前的准入条件和回滚规则。
3. 第6-E开始时必须从此契约启动，不得跳过。

---

## 二、切换前硬性准入

第6-E任何一段执行前，**必须全部满足**以下条件：

| # | 准入项 | 检查方法 | 说明 |
|:--|:-------|:---------|:-----|
| P0-A | 第6-A/B/C验收记录存在且建议通过 | `test -f` 3份验收记录+rg结论 | 任一未通过→退回 |
| P0-B | `check_canonical_pipeline_gate.py` 对目标日期 PASS | `python3 scripts/check_canonical_pipeline_gate.py --date {target} --canonical-dir {...} --render-dir {...}` | 所有子闸门 PASS |
| P0-C | baseline authority PASS | `python3 scripts/check_baseline_authority.py --all --date {target}` | 10只全部 PASS |
| P0-D | numeric source consistency: 当前允许历史 BLOCK；生产切换前必须明确适用日期；若切真实当日，P0-B不能有P0 BLOCK | `python3 scripts/check_numeric_source_consistency.py --all --date {target}` | 按策略灵活处理 |
| P0-E | freshness PASS | `python3 scripts/check_freshness_degradation.py --all --date {target}` | 全部 PASS 或仅已登记P1 |
| P0-F | MD/sidecar 对生产目标日期必须 PASS 或仅剩已登记P1 | `python3 scripts/check_md_sidecar_consistency.py --all --date {target}` | 全部 PASS |
| P0-G | P5 lineage PASS | `python3 scripts/check_report_authority_lineage.py --all --date {target}` | 10只全部 PASS |
| P0-H | runtime entry authority PASS | `python3 scripts/check_runtime_entry_authority.py --all` | 全部 PASS |
| P0-I | git status path-limited，无非允许范围变更 | `git status --short` | 只有已登记的design文件在变更范围 |

---

## 三、切换模式

只允许三段式渐进切换：

### E1 shadow-only

- canonical 只旁路生成，不影响正式输出
- 跑总闸门验证 PASS
- 写入临时目录，不覆盖正式 sidecar
- 验证人：玉夜+新安

### E2 dual-write

- 正式输出仍用旧链路
- 同时生成 canonical 输出到临时目录并 diff
- diff 必须对全池 10 只全部 PASS
- 正式日报 MD/sidecar 不受影响
- 验证人：玉夜+新安+旧影

### E3 guarded-cutover

- 真实输出来自 canonical
- **必须**保留旧链路回滚入口（旧生成脚本不动、旧 sidecar 备份到 `重点股票/股票报告/_cutover_backup/{date}/`）
- 跑总闸门 PASS 后才可确认
- **腰子放行**后才可发布
- 验证人：腰子+旧影

---

## 四、禁止一次性 full cutover

明确禁止以下操作：

- ❌ 直接修改 `daily_orchestrator.py` 让正式日报从 canonical 输出
- ❌ 直接覆盖正式 sidecar 而不保留回滚备份
- ❌ 在未跑总闸门时发布任何 canonical 关联输出
- ❌ 在已确认 BLOCK 的情况下继续发布
- ❌ 跳过 E1 直上 E2 或 E3
- ❌ 跳过任何 P0 准入项

---

## 五、回滚条件

回滚条件 = 任一出现即触发回滚。
回滚动作 = 恢复旧链路、撤回正式输出。

| # | 回滚条件 | 回滚动作 |
|:--|:---------|:---------|
| R1 | `canonical_pipeline_gate` BLOCK | 停 canonical 输出，恢复旧链路 |
| R2 | 任何 P0-A/B/C/D/E/F/G/H/I BLOCK | 停对应环节，退回设计阶段 |
| R3 | diff 不一致（render diff 或 golden diff BLOCK） | 停输出，检查映射 |
| R4 | 正式报告目录出现非预期 `_rendered.` 文件 | 立即删除，审核脚本权限 |
| R5 | `source_snapshot` 缺失导致 P0-B 无法判定 | stop-the-line，数据修复后重跑 |
| R6 | 用户发现报告数字/日期/sidecar 不一致 | stop-the-line，立即回滚 |

---

## 六、角色责任

| 角色 | 职责 |
|:-----|:-----|
| **阿黑** | 切换调度与范围控制；第6-E启动指示 |
| **情墨** | 架构与契约一致性；准入检查 |
| **玉夜** | 数据事实验证；diff 结果复审 |
| **红结** | 代码实现（E3时修改生成链路入口） |
| **新安** | 测试验证；总闸门运行 |
| **旧影** | G5 独立复查；回滚触发监督 |
| **腰子** | 🚨 **金融口径最终放行人**；E3 前必须亲笔签名放行 |
