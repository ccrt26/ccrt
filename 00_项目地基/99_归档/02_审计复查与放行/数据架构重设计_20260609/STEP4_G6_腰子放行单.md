# STEP4 G6 腰子放行单 — 地基脚本整体优化与遗留清理

> **流程编号**：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE
> **阶段门**：G6（放行归档）
> **放行角色**：腰子（金融业务负责人）
> **日期**：2026-06-09
> formal pipeline actor/HMAC：未通过，继续作为明示例外
> 本次 G6 放行不等同于 formal pipeline PASS
> 用户确认后方可正式收口

---

## 一、前置确认

| 确认项 | 结论 | 证据 |
|:-------|:-----|:------|
| G5 旧影独立复查 | ✅ **建议通过（WARN 可接受）** | `STEP4_G5_旧影独立复查报告.md` |
| G5 WARN 重复条目补修 | ✅ D5/D6 重复已消除，废弃冻结由 7→6 | 用户确认补修通过 |
| G6 前无 BLOCK | ✅ | G5 结论明确 |
| G2 腰子金融口径前置确认 | ✅ PASS | `STEP4_G2_腰子金融口径前置确认.md` |
| formal pipeline 例外 | 明示例外 | 本次不等同 formal pipeline PASS |

---

## 二、腰子独立验证命令结果

| 命令 | 结果 | 说明 |
|:-----|:-----|:------|
| `test ! -e l2_cache.db` | ✅ exit=0 | l2_cache.db 不存在 |
| `grep UDS daily_workflow.py / daily_orchestrator.py / cached_data_source.py` | ✅ exit=1 | 三份正式入口无 UDS 引用 |
| `json.tool runtime_entry_registry.json` | ✅ 合法 | — |
| `json.tool win_legacy_migration_register.json` | ✅ 合法 | — |
| `win_legacy entries` | ✅ **27 条** | 原有 15 条 + 新增 12 条 |
| gen_pdf 系列状态 | ✅ **under_review**（3 项） | 未冻结，待后续确认完整覆盖 |
| 五步总结口径 | ✅ 阶段性总结，G5/G6 待完成 | 非最终版 |

---

## 三、放行确认

### 3.1 不切生产确认

| 隔离项 | 状态 |
|:-------|:------|
| 日报/深度分析正式入口 | ✅ 未修改，UDS 未接入 |
| cached_data_source.py | ✅ pre-existing dirty，未新增 UDS 引用 |
| daily_workflow.py | ✅ pre-existing dirty，未新增 UDS 引用 |
| daily_orchestrator.py | ✅ pre-existing dirty，未新增 UDS 引用 |
| l2_cache.db | ✅ 未创建 |
| UnifiedDataSource | ✅ 保持 shadow 模式，未切生产 |
| data_full.json / kline_cache / fund_flow_cache | ✅ 未修改 |
| D04 能力扩展 | ✅ C-D04-0001 未新增 consumed_by，四做+十不做边界未突破 |

### 3.2 金融规则安全确认

| 检查项 | 结论 |
|:-------|:------|
| 金融铁律新增内容 | ✅ 仅新增 D04/L1/L2/L3 数据源口径说明（19 行） |
| PE(TTM) 计算规则 | ✅ 未改变 |
| 数据真实性铁律 | ✅ 未改变 |
| 双源交叉验证 | ✅ 未改变 |
| 报告样式冻结 | ✅ 未改变 |
| D04 未扩展为分析/回测/交易/投资建议 | ✅ 能力边界保持 |
| 腰子 G6 最终放行权保留 | ✅ 本放行单由腰子独立签署 |

### 3.3 注册表与旧入口确认

| 检查项 | 结论 |
|:-------|:------|
| runtime_entry_registry.json | ✅ JSON 合法，19 条 |
| win_legacy_migration_register.json | ✅ JSON 合法，27 条 |
| 废弃冻结 | ✅ 6 项（无重复） |
| under_review | ✅ 9 项（含 gen_pdf 系列 3 项） |
| 遗留隔离 | ✅ 3 项 |
| 物理文件删除或移动 | ✅ **未执行** |

### 3.4 回滚安全确认

| 检查项 | 结论 |
|:-------|:------|
| 禁止 git reset | ✅ |
| 禁止整文件 checkout | ✅ |
| 禁止默认 rm | ✅ |
| 保护 pre-existing dirty | ✅ |
| patch + 人工审核 + 逐块回退 | ✅ |

### 3.5 五步总结口径确认

| 检查项 | 结论 |
|:-------|:------|
| 标题为"STEP4 G4 自检版" | ✅ |
| 明确声明不代表 G5/G6 | ✅ |
| STEP4 完成度：G3/G4 已完成，G5/G6 待完成 | ✅ |
| under_review 数量一致（9 项） | ✅ |
| no psil typo | ✅ |
| G5/G6 进入条件已写明 | ✅ |

---

## 四、腰子放行意见

| 字段 | 内容 |
|:-----|:------|
| **放行角色** | **腰子**（金融业务负责人） |
| **放行范围** | STEP4 地基脚本整体优化与遗留清理：旧入口矩阵、runtime/win_legacy 注册表更新、D04 运行手册/回滚手册/常规审计接入、金融铁律 D04 口径同步、五步优化阶段性总结 |
| **意见** | **✅ 同意放行** |
| **日期** | **2026-06-09** |

### 附加条件

1. **五步优化正式收口需用户最终确认** — 本放行单不等同于用户确认，需用户明确签署确认后方可宣布收口。
2. **l2_cache.db 创建需用户单独授权**，且须先 `--dry-run` 验证。
3. **sector_phase 不一致**需后续以 F-DATA/F-FIX 单独处理（非 STEP4 问题）。
4. **gen_pdf 系列（3 项）** 保持 under_review，不得视为已冻结。后续需逐项验证 convert_md_to_pdf.py / gen_keystock_pdf.py 覆盖完整性。
5. **formal pipeline actor/HMAC** 需继续作为流程工具链例外记录，不得伪造 sign-off。
6. **UnifiedDataSource 不得切生产**，guarded cutover 需另起阶段并用户确认。
7. **D04 不得扩展为分析/回测/交易/投资建议系统**，保持 NOT-01~NOT-10 边界。

---

## 五、用户确认区

```
**【✅】接受 STEP4 G6 放行，五步优化正式收口**
【】不接受，需修正（请说明）

用户签字：用户（CCRT）
日期：2026-06-09
```

> 用户确认前，不得宣布五步优化最终完成。
> 阿黑不得代签用户确认。
> 执行模型不得代签用户确认。
> G6 放行不等同 formal pipeline PASS。

---

## 六、暂停声明

```
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
⛔
⛔   STEP4 G6 腰子放行单已落盘。
⛔   腰子意见：同意放行（附条件）。
⛔
⛔   用户确认前 STEP4 不正式收口。
⛔   当前不得自动宣布五步优化最终完成。
⛔   sector_phase 清理需另起 F-DATA/F-FIX。
⛔   gen_pdf 系列为 under_review，未冻结。
⛔   formal pipeline actor/HMAC 继续明示例外。
⛔
⛔   等待用户决定：
⛔     1. 是否接受 STEP4 G6 放行；
⛔     2. 是否正式收口五步优化；
⛔     3. 是否另起 F-DATA/F-FIX 清理 WARN 项。
⛔
⛔   阿黑不得代签用户确认。
⛔   执行模型不得代签用户确认。
⛔
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
```

---

*流程编号：F-ARCH + F-DATA + F-GATE + F-MIGRATE + F-SCHEDULE | 阶段门：G6*
*formal pipeline actor/HMAC：未通过，继续作为明示例外 | 本次 G6 放行不等同于 formal pipeline PASS*
*腰子：同意放行（附条件）| 日期：2026-06-09*
