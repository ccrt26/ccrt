# WARN W1-W4 收口记录

> **流程编号**：F-DATA + F-FIX + F-REPORT + F-GATE + F-RUNBOOK  
> **收口日期**：2026-06-09  
> **G3 执行人**：红结  
> **G4 自检**：后附  
> **G5 复查**：旧影（待进行）  
> **G6 放行**：腰子（待进行）  

---

## W1：sector_phase 不一致

**修复状态**：✅ **已修复，正式收口**

| 项目 | 内容 |
|:-----|:------|
| 问题 | 600114 东睦股份 20260604 报告产物 sector_phase="潜伏期" 与 data_scored 当前快照"主升调整"不一致 |
| G1 腰子确认 | 同意统一为"主升调整" |
| 修复文件 1 | `重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260604.json` → sector_phase.phase: "潜伏期"→**"主升调整"** |
| 修复文件 2 | `重点股票/股票报告/东睦股份(600114)/东睦股份(600114)日报_20260604.md` → 相位描述统一为**"主升调整"** |
| data_scored.json | ❌ 未修改 |
| 代码文件 | ❌ 未修改 |
| 生成链 / engine | ❌ 未碰 |
| 回滚方案 | 手工将两个文件相位改回"潜伏期" |

---

## W2：l2_cache.db 创建

**修复状态**：⬇️ **已创建空 schema（最小建库）**

| 项目 | 内容 |
|:-----|:------|
| 操作 | `build_l2_cache.py --init-empty-tables` 创建空 schema |
| API 调用 | ❌ **未调用** Tushare/任何外部 API |
| 历史数据 | ❌ 未补历史大数据 |
| 生产切换 | ❌ 未切生产 |
| 创建路径 | `代码文件/数据/l2_cache/l2_cache.db` |
| Dry-run | ✅ 先执行 dry-run 确认通过 |
| Health check | ✅ 通过 |
| 回滚方案 | 人工确认后删除 `l2_cache.db` 文件（保留目录） |

---

## W3：gen_pdf 系列 under_review

**修复状态**：⬇️ **已覆盖验证，治理状态已更新**

| 项目 | 内容 |
|:-----|:------|
| 覆盖验证 | Python 替代工具存在且 help 正常：`build_tools.py` / `convert_md_to_pdf.py` / `gen_keystock_pdf.py` |
| gen_pdf.ps1 | `under_review` → **`forbidden_when_python_available`** |
| gen_eval_pdf.ps1 | `under_review` → **`forbidden_when_python_available`** |
| gen_keystock_pdf.ps1 | `under_review` → **`forbidden_when_python_available`** |
| 更新文件 1 | `00_项目地基/06_调度与运行/win_legacy_migration_register.json` |
| 更新文件 2 | `00_项目地基/02_数据架构重设计/五步优化接力包/STEP4_旧入口最终处置矩阵.md` |
| ps1 删除 | ❌ **未删除** 任何 .ps1 文件 |
| 回滚方案 | 将 3 项状态从 `forbidden_when_python_available` 恢复为 `under_review` |

---

## W4：formal pipeline actor/HMAC 例外

**修复状态**：✅ **已记录明示例外，不伪造通过**

| 项目 | 内容 |
|:-----|:------|
| formal pipeline actor/HMAC | ❌ **未通过**，不伪造 |
| 本收口包 | ≠ formal pipeline PASS |
| 后续执行方式 | 继续按 CCRT 接力包流程 + 用户授权 **明示例外** 执行 |
| sign_off | ❌ 不得伪造 |
| 执行模型冒充角色 | ❌ 禁止 |
| 回滚方案 | 无需回滚，仅为记录例外 |

### W4 明示例外声明

> 本 W1-W4 WARN 收口包全程以 CCRT 接力包流程（非 formal pipeline）执行：
> - 无 formal pipeline actor 签名
> - 无 HMAC 验签
> - 不等同 formal pipeline 验收通过
> - 所有阶段门（G0-G6）以**设计文档 + 角色确认 + 用户授权**为事实依据
> - formal pipeline actor/HMAC 的修复属于工具链问题，与本收口包无关，单独归入 W4 挂起
> - 本声明的法律效力等同于"已知例外，用户已知情并接受"

---

## 各 Phase 执行状态

| Phase | 操作 | 状态 |
|:------|:-----|:----:|
| Phase 1 | W1 收口记录 | ✅ 完成 |
| Phase 2a | W2 L2 SQLite dry-run | ✅ 通过 |
| Phase 2b | W2 L2 SQLite 空 schema 创建 | ✅ 完成 |
| Phase 2c | W2 health check | ✅ 通过 |
| Phase 3a | W3 gen_pdf 只读覆盖验证 | ✅ PASS |
| Phase 3b | W3 win_legacy_migration_register.json 更新 | ✅ 完成 |
| Phase 3c | W3 STEP4_旧入口最终处置矩阵.md 更新 | ✅ 完成 |
| Phase 4 | W4 formal pipeline 例外记录 | ✅ 完成 |

---

## G4 自检结果

*G3 执行后运行全量验收命令，以下为实际结果。*

| # | 验收项 | 结果 | 说明 |
|:-:|:-------|:----:|:------|
| W1-V1 | sidecar JSON 合法 | ✅ **PASS** | `python3 -m json.tool` 通过 |
| W1-V2 | sidecar phase = "主升调整" | ✅ **PASS** | `jq` 输出 `主升调整` |
| W1-V3 | MD 相位文本一致 | ✅ **PASS** | 3 处相位描述全部为"主升调整"，无"潜伏期"残留 |
| W2-V1 | l2_cache.db 存在 | ✅ **PASS** | 90112 bytes，7 表 + 5 索引 |
| W2-V2 | D04 health PASS | ⚠️ **WARN（可接受）** | 6 PASS / 1 WARN / 0 BLOCK。WARN 仅因备份目录为空（空库预期行为） |
| W3-V1 | Python PDF 替代工具存在 | ✅ **PASS** | build_tools.py / convert_md_to_pdf.py / gen_keystock_pdf.py 均存在且 help 正常 |
| W3-V2 | gen_pdf 状态已更新 | ✅ **PASS** | 3 项已从 under_review → `forbidden_when_python_available` |
| W3-V3 | ps1 未删除 | ✅ **PASS** | 3 个 .ps1 文件全部保留 |
| R1 | data_scored 未改 | ✅ **PASS** | 无新增 W1-W4 修改（仅有 pre-existing dirty） |
| R2 | 代码入口未改 | ✅ **PASS** | 禁止文件列表均无新增 W1-W4 修改 |
| R3 | Git/GitHub 未处理 | ✅ **PASS** | 未执行 commit/push/PR |

### DB 结构说明

| 项目 | 值 |
|:-----|:----|
| 表数量 | 7（kline, score_history, returns, financials, macro, risk_metrics, historical_percentiles） |
| 显式索引 | 5（idx_kline_code, idx_kline_date, idx_kline_code_date, idx_score_history_code, idx_score_history_date） |
| sqlite_master 索引总数 | 12（含 sqlite_autoindex 内部索引） |
| API 调用 | ❌ 未调用 Tushare/任何外部 API |
| 数据填充 | ❌ 空 schema，未写入历史数据 |
| 生产切换 | ❌ 未切生产 |

### 前在 untracked 文件声明

以下文件为 G3 执行前已存在的 pre-existing untracked 文件，**不计入 W1-W4 新增修改**：

| 文件 | 说明 |
|:-----|:------|
| `代码文件/数据/unified_data_source.py` | pre-existing untracked，独立文件，非本收口包创建 |
| `代码文件/数据/l2_cache/` | pre-existing untracked 目录（含 README / SOP / backup 空目录），本收口包仅向其中写入 `l2_cache.db` |
| `scripts/build_l2_cache.py` | pre-existing untracked，本收口包调用已存在的脚本创建 DB |

---

*本记录由红结 G3 执行后写入，G4 自检已完成。*
*G5 待进行：旧影独立复查。*
