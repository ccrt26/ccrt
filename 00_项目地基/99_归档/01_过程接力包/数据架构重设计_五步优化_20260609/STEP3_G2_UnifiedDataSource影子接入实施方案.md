# STEP3 G2 实施方案：UnifiedDataSource 与旧入口影子接入

> **流程编号**：F-ARCH（主流程） + F-DATA（数据事实） + F-GATE（闸门适配）
> **阶段门**：G2（技术方案设计）— **当前在此阶段，暂停等待复查**
> **日期**：2026-06-09
> **维护人**：阿黑（路由与汇总）
> **状态**：G0 路由完成 → G2 方案已落盘（补修版）→ **⛔ 暂停，等待复查确认**

---

## 1. 前置检查结论

### 1.1 STEP2 G6 放行确认

| 检查项 | 结果 | 证据 |
|:-------|:-----|:------|
| STEP2_D04数据层建设报告.md 存在并 PASS | ✅ | 已读，G6 收口（腰子签字 + 用户确认） |
| L2 目录骨架存在 | ✅ | .gitignore / README / SOP / backup |
| L2 脚本 9/9 编译 PASS | ✅ | `STEP2_验收命令结果.md` §一 |
| build/update/rebuild/health dry-run 可执行 | ✅ | 全部通过 |
| L2 DB 路径/哨兵路径/备份路径已定 | ✅ | `代码文件/数据/l2_cache/l2_cache.db` |
| 禁止范围未越界 | ✅ | `STEP2_验收命令结果.md` §四 |
| STEP2 G5 旧影复查 | ✅ **建议通过** | `STEP2_D04数据层建设报告.md` §四 |
| STEP2 G6 腰子签字 | ✅ **同意放行**，附加条件已记录 | `STEP2_D04数据层建设报告.md` §四 |
| STEP2 G6 用户确认 | ✅ **接受放行结论** | `STEP2_D04数据层建设报告.md` §四 |

### 1.2 `STEP3_准入检查清单.md` 滞后说明

该清单中 §四 仍标注"G5 待确认 / 用户待确认"，生成于 STEP2 G5 之前。**该状态已被后续的 G6 放行过程覆盖**，以 G6 放行单和用户确认为 STEP3 前置依据。

### 1.3 Formal Pipeline 状态

| 项 | 状态 | 处理 |
|:---|:------|:------|
| 运行编号 | `RUN-20260609-012906-d11109` | — |
| 当前阶段 | `design`（停留） | — |
| 状态 | `active`，未 blocked | — |
| actor/HMAC | 无法通过 sign_off/--advance | **继续作为例外记录** |
| 含义 | **formal pipeline 未通过** | 不得写成 formal pipeline 已通过 |

**例外延续理由**：接力包流程基于用户授权的流程确认，不等同于 pipeline_engine advance 方式的 formal pipeline 通过。该例外已在 STEP2 G6 放行单中记录，STEP3 延续此约定。

### 1.4 `cached_data_source.py` 状态

```
git diff -- 代码文件/lib/cached_data_source.py
→ pre-existing dirty（约 130 行 diff，非本会话造成）
```

该文件有 pre-existing dirty。STEP3 **第一轮 G3 不强制修改该文件**。如需修改，待用户额外确认。

### 1.5 `daily_workflow.py` 状态

```
git diff -- 代码文件/每日荐股/scripts/daily_workflow.py
→ pre-existing dirty（非本会话造成）
```

该文件有 pre-existing dirty。STEP3 **第一轮 G3 不修改该文件**。shadow 验证通过独立脚本完成，不接入日报正式入口。

### 1.6 `l2_cache.db` 状态

```
test -f 代码文件/数据/l2_cache/l2_cache.db → NOT EXISTS
```

**STEP3 不得自动创建该文件。** UnifiedDataSource 的 L2 分支全部做 degraded/SKIP 处理。

### 1.7 第一轮 G3 不修改的文件汇总

| 文件 | pre-existing dirty | 第一轮 G3 是否修改 |
|:-----|:------------------|:------------------|
| `代码文件/lib/cached_data_source.py` | ✅ 是 | ❌ **不修改**（谨慎待确认） |
| `代码文件/每日荐股/scripts/daily_workflow.py` | ✅ 是 | ❌ **不修改**（不接入正式入口） |
| `代码文件/每日荐股/scripts/batch_data_collector.py` | ✅ 是 | ❌ **不修改** |

---

## 2. 流程编号与阶段门

| 字段 | 值 |
|:-----|:----|
| **主流程编号** | F-ARCH（地基/架构变更） |
| **挂载流程** | F-DATA（数据事实变更）+ F-GATE（闸门/验收脚本变更） |
| **启用阶段门** | G0 → G2（补修）→ G2（复查） |
| **跳过阶段门** | G1（无金融口径变更，D04 边界已在 STEP0 冻结） |
| **当前阶段** | **G2（技术方案设计·补修版）** |
| **下一阶段** | G3（执行实现）— **未经用户确认不得进入** |

### 阶段门路线图

```
G0 (阿黑·路由) → G1 (跳过·无金融口径变更)
 → G2 (技术方案·首次落盘) → G2 补修（本轮）→ G2 复查
 → ⛔ 暂停 → 用户书面确认 → G3 (红结·实现)
 → G4 (红结·自检) → G5 (旧影·独立复查)
 → G6 (腰子/用户·放行)
               ↑
    本轮只能做到这里
```

---

## 3. 阿黑权限边界

| 能做 | 不能做 |
|:-----|:-------|
| ✅ G0 路由、阶段调度 | ⛔ 实施 G3 |
| ✅ G2 方案汇总、补修、落盘 | ⛔ 修改任何代码文件 |
| ✅ 调度角色（通知情墨/玉夜/新安/旧影复查） | ⛔ 代签情墨、玉夜、新安、旧影、腰子 |
| ✅ 标记暂停点 | ⛔ 在用户未确认时推进下一阶段 |
| ✅ 复述方案细节供复查 | ⛔ 绕过 actor/HMAC |
| | ⛔ 以"用户授权"自行替代正式确认 |
| | ⛔ 自动启动 STEP3 |
| | ⛔ 自动创建 l2_cache.db |
| | ⛔ 自动切生产 |
| | ⛔ 创建 UnifiedDataSource 文件（G2 阶段禁止） |
| | ⛔ 处理 GitHub |

---

## 4. 角色职责与待确认项

| 角色 | 阶段门 | 职责 | 当前状态 |
|:-----|:-------|:-----|:---------|
| **阿黑** | G0→G2 | 流程路由、阶段调度、汇总影响范围、方案落盘 | ✅ G0 路由完成，G2 方案已落盘 |
| **情墨** | G2 | 复查目录结构、模块边界、契约一致性；重点看 UnifiedDataSource 文件位置、import 路径、是否触碰正式入口 | ⬜ **待复查确认** |
| **玉夜** | G2 | 复查 L1/L2/L3 权威源读取优先级、降级路径、D04 边界；确认未扩展分析/回测/交易能力 | ⬜ **待复查确认** |
| **新安** | G2 | 复查验收命令完整性、dry-run/smoke test/fallback/diff 测试覆盖、禁止范围检查有效性 | ⬜ **待复查确认** |
| **红结** | G3 | 仅在用户明确回复"确认进入 STEP3 G3"后执行编码实现 | ⬜ G3 阶段 |
| **旧影** | G5 | 独立复查验收报告+命令结果，不得由阿黑或执行模型代签 | ⬜ G5 阶段 |
| **腰子** | G6 | 放行确认签字，不得由阿黑或执行模型代签 | ⬜ G6 阶段 |

**驳回条件**：情墨、玉夜或新安对本方案任何设计点持异议 → BLOCK，退回 G2 修订。不得带异议进入 G3。

---

## 5. 允许修改范围（G3 阶段）

### 5.1 新增文件（第一轮 G3 主范围）

| 文件路径 | 操作 | 目的 | 是否影响生产 | 说明 |
|:---------|:-----|:------|:------------|:------|
| `代码文件/数据/unified_data_source.py` | **N** | UnifiedDataSource 核心类（10 接口 + 辅助方法） | ❌ 默认不激活 | 主交付物 |
| `scripts/run_shadow_diff.py` | **N** | **独立** shadow diff 验证脚本（主验证入口） | ❌ 仅分析 | **第一轮主验证入口** |
| `scripts/migrate_historical_kline.py` | **N** | K 线三处散落收敛（dry-run 模式优先） | ❌ `--dry-run` | 可选工具 |
| `tests/test_d04_fallback.py` | **N** | 3 个 fallback 回归测试用例 | ❌ 测试文件 | 验证降级逻辑 |
| `00_项目地基/02_数据架构重设计/五步优化接力包/STEP3_*交付物.md` | **N** | 交付报告 | ❌ 文档 | 验收产物 |

### 5.2 修改文件（第一轮 G3 范围）

| 文件路径 | 操作 | 修改目的 | 是否影响生产 | 说明 |
|:---------|:-----|:---------|:------------|:------|
| `scripts/check_numeric_source_consistency.py` | **可选 M** | 增加新旧路径比对（SKIP 不阻断） | ❌ enabled=false | 不改阻断逻辑 |
| `scripts/check_freshness_degradation.py` | **可选 M** | 增加新旧路径比对（SKIP 不阻断） | ❌ enabled=false | 不改阻断逻辑 |
| `scripts/check_daily_data_chain_health.py` | **可选 M** | 可选增加 UDS 健康检查 | ❌ 可选新增 | 不默认激活 |

### 5.3 谨慎待确认项（第一轮 G3 不强制，需用户额外确认）

| 文件路径 | 操作 | 说明 |
|:---------|:-----|:------|
| `代码文件/lib/cached_data_source.py` | **待确认 M** | 第一轮 **不修改**。如需接入 shadow/dual-write，必须用户额外确认后，按 §10 最小化方案实施。实施后验证返回值格式不变、fallback 逻辑不变、不影响生产。 |

### 5.4 不在本轮第一轮 G3 范围内的文件

| 文件路径 | 原因 |
|:---------|:------|
| `代码文件/每日荐股/scripts/daily_workflow.py` | 第一轮不修改。shadow 验证通过独立 `scripts/run_shadow_diff.py` 完成，不在正式日报入口内接入 UDS。后续阶段如需接入，需另起确认。 |
| `代码文件/每日荐股/scripts/batch_data_collector.py` | 第一轮不修改。 |

---

## 6. 禁止修改范围

### 6.1 本轮（G2）禁止

| 禁令 | 说明 |
|:-----|:------|
| ⛔ 禁止进入 G3 | 未收到用户明确书面确认 |
| ⛔ 禁止修改任何文件 | G2 是设计阶段，不是实施 |
| ⛔ 禁止创建 l2_cache.db | 需用户单独授权 |
| ⛔ 禁止创建 UnifiedDataSource 文件 | 虽属允许范围但本轮不得实施 |

### 6.2 G3 阶段（含未来授权）禁止

| 禁令 | 说明 |
|:-----|:------|
| ⛔ 禁止第一轮 G3 修改 `daily_workflow.py` | shadow 验证通过独立脚本完成 |
| ⛔ 禁止第一轮 G3 强制修改 `cached_data_source.py` | 需用户额外确认 |
| ⛔ 禁止实写 build/update/rebuild/sync 脚本 | 除非用户明确授权建 DB |
| ⛔ 禁止调用 tushare/API | STEP3 不应触发新采集 |
| ⛔ 禁止切换正式报告生产读取链路 | 必须保持旧路由不变 |
| ⛔ 禁止让 D04 成为唯一生产输入 | 必须 shadow 验证通过 + 另起 cutover 阶段 |
| ⛔ 禁止删除或替换 `cached_data_source.py` | STEP4 才处理 |
| ⛔ 禁止修改日报正式产出物（`重点股票/股票报告/`） | 维护报告完整性 |
| ⛔ 禁止修改深度分析相关文件 | F-ANALYSIS 流程处理 |
| ⛔ 禁止修改金融分析规则（`金融铁律/`） | F-ANALYSIS 流程处理 |
| ⛔ 禁止处理 GitHub（签出/推送/PR） | 范围外 |
| ⛔ 禁止代签任何项目角色 | 阿黑不得代签情墨/玉夜/新安/旧影/腰子 |
| ⛔ 禁止绕过 numeric/freshness 闸门（保持 enabled=false） | phase 2 前不阻断 |
| ⛔ 禁止新增签字/复查/GitHub 治理类过程文件 | 非本轮范围 |
| ⛔ 禁止把 D04 扩展到分析/回测/交易/投资建议 | NOT-01~NOT-10 边界 |
| ⛔ 禁止修改 `capability_registry.json` | STEP1 已冻结 |
| ⛔ 禁止修改 `source_registry.json` | STEP1 已冻结 |
| ⛔ 禁止在正式日报入口内接入 UDS（第一轮 G3） | 日报入口保持旧链路 |
| ⛔ 禁止使用"执行模型"冒充 actor HMAC 推进 formal pipeline | 例外继续记录 |

---

## 7. 文件级修改清单（精确到函数/模块/参数）

### 7.1 新增：`代码文件/数据/unified_data_source.py`

#### 7.1.1 类结构

```python
class UnifiedDataSource:
    """D04 统一数据访问接口（Shadow/Dual-Write 阶段）

    10 个查询接口，L1/L2/L3 自动降级。
    默认只读已有数据，不做任何分析计算。
    """

    def __init__(self, db_path=None, l1_data_dir=None, enable_shadow=False):
        # ── 路径初始化 ──
        self._root = detect_root()
        self._db_path = db_path or (self._root / "代码文件" / "数据" / "l2_cache" / "l2_cache.db")
        self._l1_data_dir = l1_data_dir or (self._root / "代码文件" / "数据")

        # ── L1 数据文件路径 ──
        self._data_full_path = self._l1_data_dir / "data_full.json"
        self._kline_dir = self._l1_data_dir / "kline_cache"
        self._fund_flow_dir = self._l1_data_dir / "fund_flow_cache"

        # ── L2 连接（lazy open） ──
        self._l2_conn = None
        self._l2_available = self._check_l2_available()

        # ── 注册表 ──
        self._registry = self._load_registry()

        # ── 统计 ──
        self._stats = {"l1_hit": 0, "l2_hit": 0, "l3_hit": 0, "miss": 0, "degraded": 0}

    def _detect_root(self) -> Path:
        ...

    def _load_registry(self) -> dict:
        """读取 capability_registry.json 获取 D04 能力边界"""
        ...

    def _check_l2_available(self) -> bool:
        """检查 l2_cache.db 是否存在且可读"""
        if not self._db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("SELECT 1 FROM kline LIMIT 1")
            conn.close()
            return True
        except sqlite3.Error:
            return False

    def _get_l2_conn(self):
        """lazy open L2 连接"""
        if self._l2_conn is None and self._l2_available:
            self._l2_conn = sqlite3.connect(str(self._db_path))
            self._l2_conn.row_factory = sqlite3.Row
        return self._l2_conn

    # ── 统一返回格式 ──
    @staticmethod
    def _make_result(data_source, status, data, warnings=None, ttl_hours=24):
        return {
            "data_source": data_source,
            "requested_at": datetime.now().isoformat(),
            "status": status,
            "data": data,
            "warnings": warnings or [],
            "ttl_hours": ttl_hours,
        }

    # ── 公共接口（见 §8 逐项定义） ──
    def get_quote(self, code: str) -> dict: ...
    def get_kline(self, code: str, days: int = 120) -> dict: ...
    def get_score_history(self, code: str, from_date: str, to_date: str) -> dict: ...
    def get_financials(self, code: str, quarters: int = 4) -> dict: ...
    def get_macro(self, indicator: str, months: int = 6) -> dict: ...
    def compare_current_vs_historical(self, code: str, field: str, window: int) -> dict: ...
    def compute_factor_ic(self, factor: str, window: int = 20) -> dict: ...
    def get_max_drawdown(self, code: str) -> dict: ...
    def get_volatility_percentile(self, code: str, window: int = 20) -> dict: ...
    def export_factor_panel(self, codes: list, from_date: str, to_date: str) -> dict: ...

    # ── 信息方法 ──
    def report(self) -> str: ...
```

#### 7.1.2 两个降级帮助方法

接口分为两类降级场景：

**A. 普通数据缺口（`_l2_degraded`）**：适用于本身属于 D04 数据读取范围、但当前 l2_cache.db 缺失的接口（如 `get_macro`）。
返回 `data_source="degraded"`。

**B. STEP3 边界外/暂存能力不可用（`_not_available_in_step3`）**：适用于仅允许读预计算结果的暂存接口（如 `compute_factor_ic`、`compare_current_vs_historical`、`get_max_drawdown`、`get_volatility_percentile`、`export_factor_panel`）。当无预计算结果、DB 不存在、表不存在时返回 `data_source="not_available_in_step3"`。

```python
def _l2_degraded(self, interface_name: str) -> dict:
    """A. 普通数据缺口 — D04 数据读取范围但 l2_cache.db 缺失"""
    self._stats["degraded"] += 1
    return self._make_result(
        data_source="degraded",
        status="SKIP",
        data=None,
        warnings=[f"L2 l2_cache.db 不存在，接口 {interface_name} 跳过 L2 分支。"
                  f"创建 l2_cache.db 需用户单独授权（build_l2_cache.py --dry-run 先行）。"],
        ttl_hours=0,
    )


def _not_available_in_step3(self, interface_name: str, reason: str) -> dict:
    """B. STEP3 边界外 — 暂存接口无预计算结果时返回"""
    self._stats["degraded"] += 1
    return self._make_result(
        data_source="not_available_in_step3",
        status="SKIP",
        data=None,
        warnings=[reason],
        ttl_hours=0,
    )
```

#### 7.1.3 10 个接口的完整定义见 §8

---

### 7.2 `cached_data_source.py` — 谨慎待确认项（第一轮 G3 不强制）

> **⚠️ 第一轮 G3 不强制修改该文件。** 以下设计方案保留供参考，如需实施需用户额外确认。确认后按 §10 的 M1-M5 最小化方案实施。

**约束**（如需实施）：
- 只增量添加（不删、不改、不回滚现有行）
- 不改返回值格式
- 不改 fallback 逻辑
- shadow 默认关闭（`_shadow_enabled=False`）
- shadow 代码受 `if self._shadow_enabled:` 包裹
- 不得让日报改读 D04

**设计稿保留位置**：§10 完整记录了 M1-M5 增量方案。

---

### 7.3 第一轮 G3 不修改 `daily_workflow.py`

**决策理由**：
- shadow 验证通过**独立脚本** `scripts/run_shadow_diff.py` 完成，无需在日报入口内接入 UDS
- 不改变日报/深度分析正式入口
- `daily_workflow.py` 存在 pre-existing dirty，修改后增加不必要的风险

**后续阶段考虑**（不在本轮）：
- 如需在日报链路内启用 shadow，需单独评估
- 可通过环境变量 `UDS_SHADOW=1` 方式接入，但不在第一轮 G3

---

### 7.4 新增：`scripts/migrate_historical_kline.py`

```python
#!/usr/bin/env python3
"""
migrate_historical_kline.py — K 线三处散落收敛到 L2 SQLite（v1.0）

将 kline_cache/{code}.json 和 data_full.json 内嵌 KClose/KDate 数组
统一收敛到 L2 SQLite kline 表。按 (code, date) 去重。

用法:
  python3 scripts/migrate_historical_kline.py --dry-run    # 只统计不写入
  python3 scripts/migrate_historical_kline.py              # 实写

退出码:
  0 = PASS
  1 = WARN（部分行失败）
  2 = BLOCK

设计约束:
  - dry-run 不碰数据库
  - 全部写入 L2 后更新哨兵
  - 保持 data_full.json 和 kline_cache/ 不变
"""

import argparse, json, sqlite3, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent

def collect_from_kline_cache(kline_dir, date_from=None, date_to=None) -> list:
    """从 kline_cache/{code}.json 收集 K 线行"""
    ...

def collect_from_data_full(data_full_path) -> list:
    """从 data_full.json 内嵌 KClose 数组收集 K 线行"""
    ...

def deduplicate(rows: list) -> list:
    """按 (code, trade_date) 去重，kline_cache 优先级高于 data_full"""
    ...

def upsert_to_l2(conn, rows: list) -> int:
    """去重后 upsert 到 L2 kline 表"""
    ...

def main():
    parser = argparse.ArgumentParser(...)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ...
```

---

### 7.5 新增：`scripts/run_shadow_diff.py`（**第一轮主验证入口**）

这是 STEP3 第一轮 G3 的**核心验证脚本**。它**独立运行**，不依赖 `cached_data_source.py` 的修改，不接入 `daily_workflow.py`，不改变任何正式输出。

#### 设计原则

1. **只读对比**：分别从 legacy 源和 UnifiedDataSource 读取数据，对比输出
2. **不写生产数据**：diff 结果仅写入独立日志文件（`shadow_diff_log.jsonl`）
3. **不修改日报入口**：不引入任何正式报告生成链路
4. **不阻断当日报告**：diff 超出容差时输出 WARN，不 BLOCK

#### 函数级设计

```python
#!/usr/bin/env python3
"""
run_shadow_diff.py — Shadow diff 自动化验证（v1.0）
**第一轮主验证入口**：独立脚本，不修改任何现有文件。

对比 UnifiedDataSource 与 legacy 源的输出差异。
差异在容差范围内 → PASS；超出容差 → WARN 不 BLOCK。

用法:
  python3 scripts/run_shadow_diff.py --date 20260609
  python3 scripts/run_shadow_diff.py --date 20260609 --json
  python3 scripts/run_shadow_diff.py --all-stocks --date 20260609

退出码:
  0 = ALL PASS（全部接口 shadow diff 通过或 SKIP）
  1 = WARN（部分接口有差异但可接受）
  2 = BLOCK（脚本错误）
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 导入 UnifiedDataSource（需显式加路径）
sys.path.insert(0, str(ROOT / "代码文件" / "数据"))
from unified_data_source import UnifiedDataSource

# ── 配置 ──
TOLERANCE = {
    "close": 0.01,       # 收盘价 ≤ ¥0.01
    "change_pct": 0.05,  # 涨跌幅 ≤ 0.05%
    "volume_wan_shou": 1.0,  # 成交量 ≤ 1 万手
    "fund_flow_wan": 1.0,    # 资金净额 ≤ ¥1 万
}

LOG_DIR = ROOT / "代码文件" / "数据" / "l2_cache"
DIFF_LOG = LOG_DIR / "shadow_diff_log.jsonl"


def load_stock_pool() -> list:
    """从 pigeon_config.json 获取重点股票列表"""
    ...


def get_legacy_kline(code: str, days: int = 120) -> dict:
    """从 legacy kline_cache/{code}.json 读取 K 线数据"""
    ...


def get_legacy_quote(code: str) -> dict:
    """从 legacy data_full.json 读取报价数据"""
    ...


def compute_diff(old_val, new_val, tolerance) -> dict:
    """计算单字段差异，返回 {old, new, delta, within_tolerance}"""
    ...


def diff_interface(interface_name: str, code: str, legacy_func, uds_func) -> dict:
    """对比单个接口的遗留源和 UDS 输出"""
    ...


def run_shadow(stock_codes: list, date_str: str, output_json: bool = False) -> dict:
    """运行全部 shadow diff 验证"""
    ...


def main():
    parser = argparse.ArgumentParser(description="Shadow diff 自动化验证（第一轮主入口）")
    parser.add_argument("--date", required=True, help="交易日 YYYYMMDD")
    parser.add_argument("--code", help="限单只股票")
    parser.add_argument("--all-stocks", action="store_true", help="验证全部重点股票")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    args = parser.parse_args()
    ...


if __name__ == "__main__":
    main()
```

#### 数据流

```
run_shadow_diff.py
  │
  ├── Legacy 源（直接文件读取）:
  │     kline_cache/{code}.json         → legacy_kline
  │     data_full.json                  → legacy_quote
  │
  └── UnifiedDataSource（新路由）:
        UnifiedDataSource.get_kline()   → uds_kline
        UnifiedDataSource.get_quote()   → uds_quote
  │
  └── 输出:
        shadow_diff_log.jsonl           ← 每只股票/每个接口的 diff 记录
        控制台报告                       ← 汇总结果
```

#### 验证接口范围（第一轮）

| 接口 | Legacy 源 | UDS 接口 | 备注 |
|:-----|:----------|:---------|:------|
| `get_kline` | kline_cache/{code}.json | `UDS.get_kline(code, 120)` | 对比 close/volume |
| `get_quote` | data_full.json Stock | `UDS.get_quote(code)` | 对比 close/change_pct |
| `get_financials` | data_full.json Financials | `UDS.get_financials(code)` | 对比当前季度值 |
| `get_score_history` | N/A（L1 不保留） | `UDS.get_score_history()` | 仅验证 UDS 返回格式 |
| `get_macro` | N/A（L1 不持宏观） | `UDS.get_macro()` | L2 缺失时验证 degraded |
| `compare_current_vs_historical` | N/A | `UDS.compare()` | L2 缺失时验证 not_available |
| `compute_factor_ic` | N/A | `UDS.compute_factor_ic()` | L2 缺失时验证 not_available |
| `get_max_drawdown` | N/A | `UDS.get_max_drawdown()` | L2 缺失时验证 not_available |
| `get_volatility_percentile` | N/A | `UDS.get_volatility_percentile()` | L2 缺失时验证 not_available |
| `export_factor_panel` | N/A | `UDS.export_factor_panel()` | L2 缺失时验证 not_available |

---

### 7.6 新增：`tests/test_d04_fallback.py`

```python
"""test_d04_fallback.py — UnifiedDataSource 降级回归测试"""

import pytest
import sys
from pathlib import Path

# UnifiedDataSource 在 代码文件/数据/ 下
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "代码文件" / "数据"))

from unified_data_source import UnifiedDataSource


class TestD04Fallback:
    """3 个 fallback 回归测试用例"""

    def test_l1_sufficient(self):
        """L1 kline_cache 覆盖 ≥ 请求天数 → data_source = 'l1_live'"""
        ds = UnifiedDataSource()
        result = ds.get_kline("600114", 60)
        assert result["data_source"] in ("l1_live", "degraded", "unavailable")
        if result["data_source"] == "l1_live":
            assert result["status"] == "PASS"
            assert len(result["data"]) > 0

    def test_l1_l2_fallback(self):
        """L1 不够天数 + L2 不存在 → degraded + WARN"""
        ds = UnifiedDataSource()
        result = ds.get_kline("600114", 9999)
        if not ds._l2_available:
            assert result["data_source"] == "degraded"
            assert any("l2_cache.db 不存在" in w for w in result["warnings"])

    def test_l2_empty_degraded(self):
        """L2 不存在时 L2 依赖接口返回 degraded"""
        ds = UnifiedDataSource()
        m = ds.get_macro("CPI", 3)
        if not ds._l2_available:
            assert m["status"] in ("SKIP", "BLOCK")
            assert m["data_source"] == "degraded"
            assert any("l2_cache.db 不存在" in w for w in m["warnings"])
```

---

### 7.7 后续阶段考虑项（本轮不实施）

以下设计保留供后续阶段参考，**不在第一轮 G3 范围内**：

| 项 | 目标 | 触发条件 |
|:----|:------|:---------|
| `cached_data_source.py` shadow/dual-write 改造 | 在 CachedDataSource 内部通过 `enable_shadow_mode()` 调用 UnifiedDataSource 并记录 diff | 用户额外确认后，按 §10 方案实施 |
| `daily_workflow.py` `--shadow-only` 参数 | 在日报生成链路中启用 shadow | 独立脚本验证通过后，另起确认 |
| 正式日报入口接入 UDS | 任一路口切换为 UnifiedDataSource | shadow 验证通过 + guarded cutover 阶段 |

---

## 8. UnifiedDataSource 10 个接口逐项定义

### 8.1 统一返回字段格式

```python
{
    "data_source": str,   # "l1_live" | "l2_cache" | "fallback_l1" | "fallback_l3"
                          # | "unavailable" | "degraded" | "not_available_in_step3"
    "requested_at": str,  # ISO 8601 timestamp
    "status": str,        # "PASS" | "WARN" | "SKIP" | "BLOCK"
    "data": any,          # 查询结果数据（None 当 degraded/unavailable）
    "warnings": [str],    # 警告信息列表
    "ttl_hours": int,     # 缓存推荐 TTL（小时）
}
```

### 8.2 `get_quote`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `get_quote(code: str) -> dict` |
| **输入参数** | `code`: 股票代码（如 `"600114"`） |
| **返回 `data` 类型** | `dict` 含 `Code`, `Name`, `close`, `open`, `high`, `low`, `volume`, `amount`, `change_pct` |
| **L1 读取** | `data_full.json` → `Stocks[]` 中 `Code==code` 的条目，取内嵌 KClose/KDate 最新日 |
| **L2 读取** | 无（L2 不存当日实时行情） |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | 直接跳过 L2（因 L2 不负责实时行情），返回 L1 + `status: "PASS"`，无额外 WARN |
| **是否只读预计算** | 是 |
| **是否允许本阶段计算** | 否 |
| **降级路径** | L1 存在 → `l1_live` / L1 不存在 → `unavailable` + `status: "WARN"` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); q=ds.get_quote('600114'); assert q and 'data_source' in q; print(q['data_source'], q['status'])"` |

### 8.3 `get_kline`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `get_kline(code: str, days: int = 120) -> dict` |
| **输入参数** | `code`: 股票代码；`days`: 请求天数（默认 120） |
| **返回 `data` 类型** | `[{"trade_date", "open", "high", "low", "close", "volume", "amount"}]` |
| **L1 读取** | `kline_cache/{code}.json` 读取后取最近 `days` 条 |
| **L2 读取** | `SELECT * FROM kline WHERE code=? ORDER BY trade_date DESC LIMIT days`（前复权） |
| **L3 读取** | 无（L1+L2 覆盖全场景） |
| **l2_cache.db 缺失时** | L2 分支跳过。若 days ≤ L1 覆盖天数 → `l1_live` + `status: "PASS"`。若 days > L1 覆盖天数 → `degraded` + `status: "WARN"` + `warnings: ["L2 不存在，仅返回 L1 数据（N 天），小于请求的 days 天"]` |
| **是否只读预计算** | 是 |
| **是否允许本阶段计算** | 否 |
| **降级路径** | L1 充足 → `l1_live,PASS` / L1 不足 + L2 存在 → `l2_cache,PASS`（合并） / L1 不足 + L2 缺失 → `degraded,WARN`（仅 L1） / 两者皆空 → `unavailable,BLOCK` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); k=ds.get_kline('600114', 60); print(len(k['data']), k['data_source'], k['status'])"` |

### 8.4 `get_score_history`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `get_score_history(code: str, from_date: str, to_date: str) -> dict` |
| **输入参数** | `code`: 股票代码；`from_date`: "YYYY-MM-DD"；`to_date`: "YYYY-MM-DD" |
| **返回 `data` 类型** | `[{"trade_date", "score", "rank", "bucket", "score_type"}]` |
| **L1 读取** | 无（L1 不持久保留评分历史） |
| **L2 读取** | `l2_cache.db` → `score_history` 表 `WHERE code=? AND trade_date BETWEEN ? AND ?` |
| **L3 读取** | `历史数据/04_原始数据/{年}/*_data_scored.json` 周级快照（兜底） |
| **l2_cache.db 缺失时** | 尝试 L3 归档重建。L3 可读 → `fallback_l3` + `status: "WARN"`。L3 不可读 → `degraded` + `status: "BLOCK"` + `warnings: ["score_history 主源为 L2，次源为 L3 归档。两者均不可用。"]` |
| **是否只读预计算** | 是 |
| **是否允许本阶段计算** | 否 |
| **降级路径** | L2 存在 → `l2_cache,PASS` / L2 缺失 + L3 可读 → `fallback_l3,WARN` / 都不可用 → `degraded,BLOCK` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); s=ds.get_score_history('600114', '2026-01-01', '2026-06-09'); print(s['data_source'], s['status'])"` |

### 8.5 `get_financials`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `get_financials(code: str, quarters: int = 4) -> dict` |
| **输入参数** | `code`: 股票代码；`quarters`: 请求季度数（默认 4） |
| **返回 `data` 类型** | `[{"report_period", "metric", "value", "unit"}]` |
| **L1 读取** | `data_full.json` → `Stocks[].Code==code.Financials`（当前季度） |
| **L2 读取** | `l2_cache.db` → `financials` 表 |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | L2 跳过，仅返回 L1 财务数据（当前季度）+ `warnings: ["L2 不存在，仅返回 L1 当前季度财务数据"]` + `status: "WARN"` |
| **是否只读预计算** | 是 |
| **是否允许本阶段计算** | 否 |
| **降级路径** | L1 有数据 → `l1_live`（L1 是实时截面）或 `WARN`（L2 缺失） / L1 无 + L2 存在 → `l2_cache,PASS` / 都无 → `unavailable,BLOCK` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); f=ds.get_financials('600114', 2); print(f['data_source'], f['status'])"` |

### 8.6 `get_macro`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `get_macro(indicator: str, months: int = 6) -> dict` |
| **输入参数** | `indicator`: 宏观指标名（如 `"CPI"`）；`months`: 月份数（默认 6） |
| **返回 `data` 类型** | `[{"trade_date", "value", "unit"}]` |
| **L1 读取** | 无（L1 不持宏观数据） |
| **L2 读取** | `l2_cache.db` → `macro` 表 `WHERE indicator=?` |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | 返回 `degraded` + `status: "SKIP"` + `warnings: ["macro 数据仅存于 L2，但 l2_cache.db 不存在"]` |
| **是否只读预计算** | 是 |
| **是否允许本阶段计算** | 否 |
| **降级路径** | L2 存在 → `l2_cache,PASS` / L2 缺失 → `degraded,SKIP` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); m=ds.get_macro('CPI', 3); print(m['data_source'], m['status'])"` |

### 8.7 `compare_current_vs_historical`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `compare_current_vs_historical(code: str, field: str, window: int) -> dict` |
| **输入参数** | `code`: 股票代码；`field`: 字段名（如 `"close"`、`"volume"`）；`window`: 回溯天数 |
| **返回 `data` 类型** | 预计算记录 |  |
| **L1 读取** | 无 |
| **L2 读取** | L2 `historical_percentiles` 表（已有预计算结果表） |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | `_not_available_in_step3("compare_current_vs_historical", reason="需要 L2 historical_percentiles 表读取预计算结果。l2_cache.db 不存在，跳过。STEP3 不现场计算统计值。")` |
| **是否只读预计算** | 是 — **仅读取 L2 已有预计算结果** |
| **是否允许本阶段计算** | ❌ **不允许在 STEP3 现场计算 mean/std/percentile**。不得生成解读或建议。无预计算结果时统一返回 `not_available_in_step3` |
| **D04 边界** | ⚠️ **暂存 D04**，Phase 3 迁移 D07（腰子）。STEP3 不扩展能力 |
| **不得输出** | ❌ 偏高/偏低/建议关注/趋势向好 等分析性语言 |
| **降级路径** | L2 预计算结果存在 → `l2_cache,PASS` / L2 不存在或表不存在或无预计算结果 → `not_available_in_step3,SKIP` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); c=ds.compare_current_vs_historical('600114', 'close', 60); assert c['data_source'] in ('l2_cache','not_available_in_step3'); print(c['data_source'], c['status'])"` |

### 8.8 `compute_factor_ic`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `compute_factor_ic(factor: str, window: int = 20) -> dict` |
| **输入参数** | `factor`: 因子名（**仅限内置因子**：`TotalScore`, `Momentum`, `Volatility`, `Turnover`, `Size`, `Value`, `Growth`, `Quality`）；`window`: 窗口天数 |
| **返回字段** | `factor, ic_series, mean_ic, icir, data_source, requested_at, status, warnings, ttl_hours` |
| **L1 读取** | 无（IC 需时间序列） |
| **L2 读取** | L2 returns 表 + kline 表 |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | 返回 `not_available_in_step3` + `status: "SKIP"` + `warnings: ["compute_factor_ic 需要 L2 returns 表用于 IC 计算。l2_cache.db 不存在，跳过。STEP3 不得新增因子计算能力。"]` |
| **是否只读预计算** | 是 — **仅读取已有预计算结果** |
| **是否允许本阶段计算** | ❌ **不允许在 STEP3 新增任何因子计算逻辑**。无预计算结果时返回 `not_available_in_step3`，**不得计算** |
| **新增因子能力** | ❌ **严格禁止**。因子计算属于 D06（青山），不在 D04/STEP3 范围内。STEP3 不得新增任何因子计算代码 |
| **降级路径** | 有预计算结果 → `l2_cache,PASS` / 无预计算结果 → `not_available_in_step3,SKIP` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); ic=ds.compute_factor_ic('TotalScore', 20); print(ic['data_source'], ic['status'])"` |

### 8.9 `get_max_drawdown`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `get_max_drawdown(code: str) -> dict` |
| **输入参数** | `code`: 股票代码 |
| **返回字段** | `max_drawdown_pct, start_date, end_date, current_drawdown, data_source, requested_at, status, warnings, ttl_hours` |
| **L1 读取** | 无（需时间序列） |
| **L2 读取** | L2 `risk_metrics` 表 `WHERE metric='max_drawdown'` |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | 返回 `not_available_in_step3` + `status: "SKIP"` + `warnings: ["get_max_drawdown 需要 L2 risk_metrics 表。l2_cache.db 不存在，跳过。"]` |
| **是否只读预计算** | 是 |
| **是否允许本阶段计算** | ❌ **不允许实时计算**。实时计算降级到 D08 Phase 3 |
| **D04 边界** | ⚠️ **暂存 D04**，Phase 3 迁移 D08（流金） |
| **降级路径** | L2 有预计算结果 → `l2_cache,PASS` / L2 无预计算结果 → `not_available_in_step3,SKIP` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); m=ds.get_max_drawdown('600114'); print(m['data_source'], m['status'])"` |

### 8.10 `get_volatility_percentile`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `get_volatility_percentile(code: str, window: int = 20) -> dict` |
| **输入参数** | `code`: 股票代码；`window`: 窗口天数 |
| **返回字段** | `current_volatility, percentile, historical_volatilities, data_source, requested_at, status, warnings, ttl_hours` |
| **L1 读取** | 无 |
| **L2 读取** | L2 `historical_percentiles` 表 |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | 返回 `not_available_in_step3` + `status: "SKIP"` + `warnings: ["get_volatility_percentile 需要 L2 historical_percentiles 表。l2_cache.db 不存在，跳过。"]` |
| **是否只读预计算** | 是 — 仅读取已有结果 |
| **是否允许本阶段计算** | ❌ STEP3 不新增波动率计算逻辑 |
| **降级路径** | L2 有预计算结果 → `l2_cache,PASS` / L2 无 → `not_available_in_step3,SKIP` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); v=ds.get_volatility_percentile('600114', 20); print(v['data_source'], v['status'])"` |

### 8.11 `export_factor_panel`

| 维度 | 值 |
|:------|:-----|
| **函数签名** | `export_factor_panel(codes: list, from_date: str, to_date: str) -> dict` |
| **输入参数** | `codes`: 股票代码列表；`from_date`: "YYYY-MM-DD"；`to_date`: "YYYY-MM-DD" |
| **返回 `data` 类型** | `[{"code", "trade_date", "TotalScore", "Momentum", ...各内置因子值}]` |
| **L1 读取** | 无（面板需时间序列） |
| **L2 读取** | L2 各表 JOIN 组装宽表 |
| **L3 读取** | 无 |
| **l2_cache.db 缺失时** | 返回 `not_available_in_step3` + `status: "SKIP"` + `warnings: ["export_factor_panel 需要 L2 各表 JOIN 组装。l2_cache.db 不存在，跳过。STEP3 只读预计算面板，不得新增回测/交易/投资建议能力。"]` |
| **是否只读预计算** | 是 — **只读已有预计算结果，不做数据组装计算** |
| **是否允许本阶段计算** | ❌ **不得新增回测/交易/投资建议能力**。只读取已存在预计算面板，不做分析、不回测、不输出建议。无预计算结果 → `not_available_in_step3` |
| **降级路径** | L2 存在且预计算面板存在 → `l2_cache,PASS` / L2 无预计算结果 → `not_available_in_step3,SKIP` |
| **验收命令** | `python3 -c "import sys; sys.path.insert(0, '代码文件/数据'); from unified_data_source import UnifiedDataSource; ds=UnifiedDataSource(); p=ds.export_factor_panel(['600114','300736'], '2026-01-01', '2026-06-09'); print(p['data_source'], p['status'])"` |

---

## 9. l2_cache.db 未创建时的 degraded/SKIP 逻辑

### 9.1 统一判定入口

```python
def _check_l2_available(self) -> bool:
    if not self._db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("SELECT 1 FROM kline LIMIT 1")
        conn.close()
        return True
    except sqlite3.Error:
        return False
```

该判定在 `__init__` 时执行一次，结果存为 `self._l2_available`。

### 9.2 各接口的 L2 缺失响应汇总（两类口径）

**A. 普通数据缺口（`= degraded`）**：D04 数据读取范围，DB 缺失时如实反映。
**B. STEP3 边界外（`= not_available_in_step3`）**：暂存接口无预计算结果时返回。

| 接口 | L2 缺失响应 | data_source | status | 分类 |
|:-----|:-----------|:------------|:-------|:-----|
| `get_quote` | 跳过 L2（不依赖 L2） | `l1_live` / `unavailable` | PASS / WARN | — |
| `get_kline` | 跳过 L2，仅用 L1 | `l1_live`（days≤L1覆盖）/ `degraded`（days>L1覆盖） | PASS / WARN | A |
| `get_score_history` | 尝试 L3 归档 | `fallback_l3` / `degraded`（L3 也失败） | WARN / BLOCK | A |
| `get_financials` | 跳过 L2，仅用 L1 | `l1_live`（当前季度） | WARN（L2 缺失） | A |
| `get_macro` | 无替代源 | `degraded` | SKIP | A |
| `compare_current_vs_historical` | 无预计算结果 | `not_available_in_step3` | SKIP | B |
| `compute_factor_ic` | 无预计算结果 | `not_available_in_step3` | SKIP | B |
| `get_max_drawdown` | 无预计算结果 | `not_available_in_step3` | SKIP | B |
| `get_volatility_percentile` | 无预计算结果 | `not_available_in_step3` | SKIP | B |
| `export_factor_panel` | 需要 L2 JOIN | `not_available_in_step3` | SKIP | B |

### 9.3 L2 缺失时的重要约束

| 约束 | 说明 |
|:-----|:------|
| ✅ L2 缺失 | **不阻断 shadow**（shadow WARN 可接受） |
| ✅ L2 缺失 | **不阻断正式日报**（旧路由不变） |
| ✅ L2 缺失 | **不阻断深度分析**（旧链路不变） |
| ⛔ STEP3 不得自动创建 DB | 需用户单独授权 |
| ⛔ 不得伪造数据 | 所有 L2 依赖接口必须按分类如实返回：A 类普通数据缺口返回 `degraded`；B 类 STEP3 边界外/暂存能力不可用返回 `not_available_in_step3`。不得把 `not_available_in_step3` 降级为 `degraded`，也不得现场计算补齐 |
| ⛔ 不得降级为自动计算 | 无预计算结果时返回 `not_available_in_step3` |

---

## 10. cached_data_source.py pre-existing dirty 基线（谨慎待确认项）

> **⚠️ 第一轮 G3 不强制修改 `cached_data_source.py`。** 以下方案保留供参考，如需实施需用户额外确认。

### 10.1 Pre-existing dirty 基线

| 项 | 值 |
|:----|:----|
| 文件 | `代码文件/lib/cached_data_source.py` |
| Pre-existing diff | 约 130 行，从 `45f4bf7e` / `a69f4d7b` 遗留 |
| 是否本次造成 | ❌ 不是 |
| 记录 baseline 命令 | `git diff 代码文件/lib/cached_data_source.py > /tmp/step3_cds_baseline.diff` |

### 10.2 修改原则（如获确认实施）

1. **只增量添加** — 不删、不改、不回滚现有行
2. **不改变返回值格式** — 现有 `_build_result()` 的 `{"data", "source", "freshness", ...}` 不变
3. **不改变 fallback 逻辑** — 6 级降级优先级不变
4. **shadow 默认关闭** — `_shadow_enabled=False`
5. **shadow 代码受 `if self._shadow_enabled:` 包裹** — 不激活时零开销
6. **不得在多重 return 路径硬塞 shadow 调用** — shadow 只放在最终 return 前的统一出口
7. **不得让日报改读 D04** — 日报入口调用 `CachedDataSource()` 时不传入 shadow 参数
8. **不得影响生产路径** — `_shadow_enabled=False` 时所有现有行为零变化

### 10.3 修改增量概况

| 编号 | 位置 | 增量行数 | 内容 |
|:-----|:------|:---------|:------|
| M1 | `__init__()` 尾部 | +5 | 初始化 `_uds`, `_shadow_enabled`, `_shadow_log_path`, `_shadow_stats` |
| M2 | 各 get_*() 最终 return 前 | +3/接口 × ~5接口 | shadow 调用（仅在最终 return 前，不在中间 return 路径插入） |
| M3 | 新增 `_shadow_verify()` | +20 | 调用 UDS 同名接口，比对结果 |
| M4 | 新增 `_shadow_diff_log()` | +40 | 记录新旧路由差异到独立日志文件 |
| M5 | 新增 `enable_shadow_mode()` | +8 | 打开 shadow 开关，lazy init UDS |

**M2 的接口适配范围**（仅在 UnifiedDataSource 有对等接口时添加）：

| 现有方法 | 对应 UDS 接口 | 是否加 shadow |
|:---------|:-------------|:-------------|
| `get_kline` | `get_kline` | ✅ 加 |
| `get_quote` | `get_quote` | ✅ 加 |
| `get_financial` | `get_financials` | ✅ 加 |
| `get_financials` (如有) | `get_financials` | ✅ 加 |
| `get_daily_basic` | 无对应 | ❌ 跳过 |
| `get_moneyflow` | 无对应 | ❌ 跳过 |
| `get_margin` | 无对应 | ❌ 跳过 |
| `get_northbound` | 无对应 | ❌ 跳过 |
| `get_holder_number` | 无对应 | ❌ 跳过 |
| `get_pledge` | 无对应 | ❌ 跳过 |
| `get_forecast` | 无对应 | ❌ 跳过 |
| `get_mainbz` | 无对应 | ❌ 跳过 |

### 10.4 验收方法（如实施后）

```bash
# 验证返回值格式未变
python3 -c "
import sys; sys.path.insert(0, '代码文件/lib')
import importlib
cds = importlib.import_module('cached_data_source')
ds = cds.CachedDataSource()
for fn in ['get_financial','get_daily_basic','get_moneyflow','get_margin','get_kline','get_quote']:
    r = getattr(ds, fn)('600114')
    assert 'data' in r and 'source' in r and 'freshness' in r
    print(f'{fn}: 返回值兼容 OK')
"
```

---

## 11. 分析/回测边界约束

### 11.1 D04 十不做对齐

| 不做 | 在 STEP3 中的实现 |
|:-----|:------------------|
| NOT-01 不做采集 | UnifiedDataSource 不调用 tushare/API |
| NOT-02 不做质量验证 | 质量检查由 D03 闸门完成 |
| NOT-03 不做回测 | `export_factor_panel` 仅读预计算结果，不运行回测 |
| NOT-04 不做因子/信号生成 | `compute_factor_ic` 仅读取预计算结果，不计算 |
| NOT-05 不做自定义因子 IC | 仅限 8 个内置因子，不新增 |
| NOT-06 不做统一解读 | `compare_current_vs_historical` 仅读预计算结果，不输出解读 |
| NOT-07 不做风控决策 | `get_max_drawdown` 不决策 |
| NOT-08 不做交易决策 | 所有接口不涉及交易 |
| NOT-09 不做投资建议 | 无"建议买入/卖出/持有"语义 |
| NOT-10 不做分析推理 | 因子计算/解读推理/决策全部禁止 |

### 11.2 三个暂存接口的迁移计划

| 接口 | 当前在 D04 | 目标域 | 迁移期限 | STEP3 约束 |
|:------|:----------|:-------|:---------|:-----------|
| `compute_factor_ic` | ✅ 暂存（仅内置因子） | **D06**（青山） | Phase 3 | 不得新增因子计算代码；无预计算结果返回 `not_available_in_step3` |
| `compare_current_vs_historical` | ✅ 暂存 | **D07**（腰子） | Phase 3 | 仅读取预计算结果，不现场计算 mean/std/percentile，不做解读。无结果 → `not_available_in_step3` |
| `get_max_drawdown` | ✅ 暂存 | **D08**（流金） | Phase 3 | 仅读取预计算结果；无结果返回 `not_available_in_step3` |

### 11.3 特殊红线

| 红线 | 违反应后果 |
|:-----|:-----------|
| ⛔ `compute_factor_ic` 在 STEP3 新增计算代码 | ❌ 直接 BLOCK，退回 G2 |
| ⛔ `compare_current_vs_historical` 在 STEP3 现场计算 mean/std/percentile | ❌ 直接 BLOCK，退回 G2 |
| ⛔ `compare_current_vs_historical` 输出"偏高/偏低/建议关注/趋势向好" | ❌ WARN + 强制修正 |
| ⛔ `export_factor_panel` 输出分析/回测/交易建议 | ❌ 直接 BLOCK |
| ⛔ 无预计算结果时伪造默认值 | ❌ BLOCK |
| ⛔ 把 D04 扩展为分析/回测/交易平台 | ❌ 架构否决 |

---

## 12. Shadow 默认策略

### 12.1 独立脚本模式（第一轮 G3）

STEP3 第一轮 G3 的 shadow 验证不嵌入任何现有模块，通过独立脚本完成：

| 配置 | 值 | 说明 |
|:-----|:----|:------|
| 主验证入口 | `scripts/run_shadow_diff.py` | 独立脚本，不依赖现有模块改造 |
| 数据流 | legacy 源 ↔ UDS → diff 日志 | 只读对比 |
| 对正式输出影响 | ❌ 无 | 不改变日报入口、不接入生产链路 |
| 是否 BLOCK 报告 | ❌ 否 | 超出容差仅 WARN |
| 日志文件 | `代码文件/数据/l2_cache/shadow_diff_log.jsonl` | 独立日志 |

### 12.2 Shadow 失败容忍

| 场景 | 处理 | 对正式输出影响 |
|:-----|:------|:----------------|
| UDS 初始化失败 | 记 WARN 日志，脚本退出码 1 | ❌ 无 |
| UDS 接口返回空 | 记 WARN 日志，继续下一接口 | ❌ 无 |
| UDS 接口抛异常 | `try/except` 捕获，记 WARN | ❌ 无 |
| Shadow diff 超出容差 | 记 WARN，输出 diff 报告，不 BLOCK | ❌ 无 |
| L2 DB 不存在 | UDS 返回 degraded，diff 日志记录 SKIP | ❌ 无 |

### 12.3 Shadow Diff 日志格式

```jsonl
{"code":"600114","interface":"get_kline","timestamp":"2026-06-09T14:30:00",
 "old_source":"kline_cache","new_source":"l1_live",
 "old_rows":120,"new_rows":122,
 "diff":{"close":{"old":35.96,"new":35.97,"delta":0.01,"within_tolerance":true},
         "volume":{"old":362000,"new":36248943,"delta":36248943,"within_tolerance":false}},
 "is_pass":false,"warn_only":true}
```

### 12.4 Shadow Diff 容忍阈值

| 字段 | 容差 | 说明 |
|:-----|:------|:------|
| `close`（收盘价） | ≤ ¥0.01 | 四舍五入差异 |
| `change_pct`（涨跌幅） | ≤ 0.05% | 四舍五入 |
| `volume`（成交量万手） | ≤ 1万手 | 股↔万手单位转换差异 |
| `fund_flow`（资金净额万） | ≤ ¥1万 | 千↔万单位转换 |
| `trade_date`（交易日期） | 完全一致 | 日期必须准确 |

### 12.5 Guarded Cutover 范围约束

```
⛔ guarded cutover 不在 STEP3 范围内。
shadow 验证通过后，如需切生产，必须另起阶段（F-ARCH + 用户书面确认）。
```

---

## 13. 闸门适配方案

### 13.1 闸门适配矩阵

| 闸门 | 当前状态 | STEP3 修改 | 是否改变现有检查 | Phase 2 启用条件 |
|:-----|:---------|:-----------|:----------------|:----------------|
| `check_numeric_source_consistency.py` | L1 数值一致性检查 | `check_kline_l2_numeric()` 增加新旧路径比对 | ❌ enabled=false 时 SKIP 不阻断 | `kline_l2.enabled=true` + `phase>=2` |
| `check_freshness_degradation.py` | L1 新鲜度 + `--tier l2` | `check_kline_l2()` 增加新旧路径比对 | ❌ enabled=false/phase<2 时 SKIP/WARN 不 BLOCK | `kline_l2.enabled=true` + `phase>=2` |
| `check_daily_data_chain_health.py` | L1 完整检查 | 可选增加 UDS 健康检查（不默认） | ❌ 可选新增 | Phase 2 强制执行 |
| `check_daily_release_gate.py` | 9 项闸门 | **不改** | ❌ 不改 | Phase 2 增 UDS 检查项 |

### 13.2 新旧路径比对逻辑

```python
# 在 check_numeric_source_consistency.py 的 check_kline_l2_numeric() 中
if not enabled or phase < 2:
    return make_check(field, f"kline_l2 enabled={enabled} phase={phase}",
                      None, None, None, "PASS",
                      f"kline_l2: SKIP (enabled={enabled}, phase={phase}) — Phase 2 前跳过 L2 数值检查")

# Phase 2 启用后：同时检查 L1 和 L2 结果，L1 优先
```

### 13.3 过渡策略

STEP3 期间所有 L2/UDS 相关闸门检查保持 `enabled=false` / `phase<2`：
- 输出 SKIP 或 WARN
- 不 BLOCK 当日报告
- 不影响现有闸门结果

---

## 14. 验收命令（G3 实施后执行）

### 14.1 编译检查

```bash
# UnifiedDataSource 核心
python3 -m py_compile 代码文件/数据/unified_data_source.py

# 独立 shadow 脚本
python3 -m py_compile scripts/run_shadow_diff.py

# K 线收敛脚本
python3 -m py_compile scripts/migrate_historical_kline.py

# 闸门脚本
python3 -m py_compile scripts/check_numeric_source_consistency.py
python3 -m py_compile scripts/check_freshness_degradation.py
python3 -m py_compile scripts/check_daily_data_chain_health.py

# 测试文件
python3 -m py_compile tests/test_d04_fallback.py

# 预期：全部 exit=0
```

### 14.2 UnifiedDataSource 单接口 smoke test

```bash
# 10 个接口逐个调用，确认返回格式正确
python3 -c "
import sys
sys.path.insert(0, '代码文件/数据')
from unified_data_source import UnifiedDataSource
ds = UnifiedDataSource()
tests = [
    ('get_quote', ds.get_quote('600114')),
    ('get_kline', ds.get_kline('600114', 60)),
    ('get_score_history', ds.get_score_history('600114', '2026-01-01', '2026-06-09')),
    ('get_financials', ds.get_financials('600114', 2)),
    ('get_macro', ds.get_macro('CPI', 3)),
    ('compare', ds.compare_current_vs_historical('600114', 'close', 60)),
    ('factor_ic', ds.compute_factor_ic('TotalScore', 20)),
    ('drawdown', ds.get_max_drawdown('600114')),
    ('vol_percentile', ds.get_volatility_percentile('600114', 20)),
    ('factor_panel', ds.export_factor_panel(['600114','300736'], '2026-01-01', '2026-06-09')),
]
for name, result in tests:
    assert 'data_source' in result and 'status' in result and 'requested_at' in result
    print(f'{name}: data_source={result[\"data_source\"]}, status={result[\"status\"]}')
print('10/10 接口返回格式正确')
"
```

### 14.3 l2_cache.db 缺失时降级测试（两类分开）

```bash
test ! -e 代码文件/数据/l2_cache/l2_cache.db && echo "DB 不存在（预期，STEP3 不自动创建）"

# A. 普通数据缺口 → data_source="degraded", status="SKIP"
python3 -c "
import sys
sys.path.insert(0, '代码文件/数据')
from unified_data_source import UnifiedDataSource
ds = UnifiedDataSource()
m = ds.get_macro('CPI', 3)
assert m['status'] in ('SKIP','BLOCK','WARN')
# get_macro 属于 D04 数据读取，缺口应返回 degraded
if m['data_source'] == 'degraded':
    assert m['status'] == 'SKIP'
    print(f'get_macro: degraded 正确 (status={m[\"status\"]})')
else:
    print(f'get_macro: {m[\"data_source\"]} (status={m[\"status\"]})')
print('A. 普通数据缺口 degraded 测试: PASS')
"

# B. STEP3 边界外 → data_source="not_available_in_step3", status="SKIP"
python3 -c "
import sys
sys.path.insert(0, '代码文件/数据')
from unified_data_source import UnifiedDataSource
ds = UnifiedDataSource()
ic = ds.compute_factor_ic('TotalScore', 20)
assert ic['status'] == 'SKIP' and 'not_available_in_step3' in ic['data_source'], \
    f'compute_factor_ic 应返回 not_available_in_step3, 实际={ic[\"data_source\"]}'
print(f'compute_factor_ic: not_available_in_step3 正确')

cp = ds.compare_current_vs_historical('600114', 'close', 60)
assert cp['data_source'] in ('l2_cache', 'not_available_in_step3')
if cp['data_source'] == 'not_available_in_step3':
    assert cp['status'] == 'SKIP'
print(f'compare_current_vs_historical: {cp[\"data_source\"]} (status={cp[\"status\"]})')

md = ds.get_max_drawdown('600114')
assert md['data_source'] in ('l2_cache', 'not_available_in_step3')
print(f'get_max_drawdown: {md[\"data_source\"]} (status={md[\"status\"]})')
print('B. STEP3 边界外 not_available_in_step3 测试: PASS')
"
```

### 14.4 Shadow diff 运行测试

```bash
# 运行独立 shadow diff 脚本
python3 scripts/run_shadow_diff.py --code 600114 --date <最近交易日>

# 预期：输出 diff 报告，exit=0 或 exit=1（WARN 可接受）
```

### 14.5 Freshness/Numeric 闸门不阻断测试

```bash
python3 scripts/check_freshness_degradation.py --code 600114 --name 东睦股份 --date <最近交易日> --tier l2 --json
# 预期：kline_l2 → SKIP/WARN，不 BLOCK

python3 scripts/check_numeric_source_consistency.py --code 600114 --name 东睦股份 --date <最近交易日> --json
# 预期：kline_l2.numeric → PASS (SKIP)
```

### 14.6 K 线收敛 dry-run 验证

```bash
python3 scripts/migrate_historical_kline.py --dry-run
# 预期：输出预计行数，不写 DB，exit=0
```

### 14.7 Fallback 回归测试

```bash
python3 -m pytest tests/test_d04_fallback.py -v
# 预期：3/3 PASS（或 SKIP 在 L2 缺失时）
```

### 14.8 禁止范围检查

```bash
# 日报入口未改读 D04
grep -rn "unified_data_source\|UnifiedDataSource" 代码文件/tools/daily_orchestrator.py 重点股票/股票报告/ 2>/dev/null
# 预期：空

# daily_workflow.py 未修改
grep -n "UnifiedDataSource\|shadow" 代码文件/每日荐股/scripts/daily_workflow.py
# 预期：空（第一轮未修改）

# cached_data_source.py 未修改（第一轮不强制）
git diff --stat 代码文件/lib/cached_data_source.py
# 预期：保持 pre-existing dirty 不变

# l2_cache.db 未创建
test ! -e 代码文件/数据/l2_cache/l2_cache.db && echo "l2_cache.db 未创建（预期）"
```

### 14.9 Git Status 检查

```bash
git status --short -- \
  代码文件/数据/unified_data_source.py \
  scripts/run_shadow_diff.py \
  scripts/migrate_historical_kline.py \
  scripts/check_numeric_source_consistency.py \
  scripts/check_freshness_degradation.py \
  scripts/check_daily_data_chain_health.py \
  tests/test_d04_*.py \
  00_项目地基/02_数据架构重设计/五步优化接力包/STEP3_*.md

# 预期：
# - 只包含允许修改范围的新增/修改文件
# - l2_cache.db 不存在（未被创建）
# - 重点股票/、历史数据/、金融铁律/ 无修改
# - 代码文件/lib/ 无修改（第一轮不强制）
# - 代码文件/每日荐股/scripts/ 无修改（第一轮不强制）
```

---

## 15. 不切生产证明

### 15.1 生产链路影响声明

| 生产链路 | 影响 | 证据 |
|:---------|:----:|:------|
| 日报生成（daily_orchestrator.py → daily_workflow.py run_daily） | ❌ 无 | `daily_workflow.py` 第一轮不修改；UDS 未接入 |
| 日报内容填充 | ❌ 无 | `cached_data_source.py` 第一轮不修改；返回值格式不变 |
| 深度分析生成 | ❌ 无 | 深度分析入口未修改 |
| 数据就绪检查（check_daily_data_chain_health.py） | ❌ 无 | UDS 检查仅可选新增，默认不运行 |
| data_full.json 读取 | ❌ 无 | L1 生产数据文件未修改 |
| kline_cache/* 缓存 | ❌ 无 | L1 缓存未修改、未删除 |
| check_freshness_degradation.py 默认 --tier l1 | ❌ 无 | 默认行为不变 |
| check_numeric_source_consistency.py | ❌ 无 | kline_l2 disabled 时跳过 |
| 报告发布闸门（check_daily_release_gate.py） | ❌ 无 | 不改，不含 UDS 检查 |
| L2 SQLite（l2_cache.db） | ❌ 未创建 | 不存在 |
| L2 闸门检查 | ❌ 不阻断 | enabled=false, phase<2 |

### 15.2 L2 SQLite 生产隔离

| 隔离项 | 措施 |
|:-------|:------|
| L2 DB 不入 git | `.gitignore` 已排除 `*.db` / `backup/*.db`（STEP2 完成） |
| 日报不读 L2 | daily_workflow.py、daily_orchestrator.py 第一轮不修改 |
| 深度分析不读 L2 | 分析入口未修改 |
| L2 仅为历史回源 | 不做当日报告的权威源（L1 当日权威不变） |
| Phase 2 前闸门不阻断 | freshness/numeric 闸门 L2 检查输出 SKIP/WARN，不 BLOCK |

### 15.3 Formal Pipeline 声明

STEP3 G3 实施基于用户授权的接力包流程确认（STEP2 G6 PASS + 本 G2 方案确认），**非标准 pipeline_engine advance 流程**。Formal pipeline `RUN-20260609-012906-d11109` 仍停留在 design 阶段，actor/HMAC 问题继续作为例外记录，**不得伪造 sign-off**。

---

## 16. 回滚方案

### 16.1 安全原则（⛔ 红线规则）

> **对存在 pre-existing dirty 的任何文件，禁止阿黑、红结或执行模型自动执行整文件 `git checkout --` 回滚。**
>
> 以下文件存在 pre-existing dirty：
> - `cached_data_source.py`
> - `daily_workflow.py`
> - `check_numeric_source_consistency.py`
> - `check_freshness_degradation.py`
> - `check_daily_data_chain_health.py`
>
> 整文件 checkout 将丢失 pre-existing 更改，**不可逆**。回滚必须逐块选择，不得覆盖 dirty。

### 16.2 新增文件删除（安全，无 pre-existing dirty）

| 文件 | 操作 | 说明 |
|:-----|:------|:------|
| `代码文件/数据/unified_data_source.py` | `rm 代码文件/数据/unified_data_source.py` | 纯新增 |
| `scripts/run_shadow_diff.py` | `rm scripts/run_shadow_diff.py` | 纯新增 |
| `scripts/migrate_historical_kline.py` | `rm scripts/migrate_historical_kline.py` | 纯新增 |
| `tests/test_d04_fallback.py` | `rm -rf tests/test_d04_fallback.py` | 纯新增 |

### 16.3 Pre-existing dirty 文件的回滚（⛔ 禁止整文件 checkout）

对存在 pre-existing dirty 的所有文件（`cached_data_source.py`、`daily_workflow.py`、`check_numeric_source_consistency.py`、`check_freshness_degradation.py`、`check_daily_data_chain_health.py`），**禁止阿黑、红结或执行模型使用整文件 `git checkout --` 回滚**。整文件 checkout 将不可逆地丢失 pre-existing 更改。

**正确流程（人工逐块）：**

```bash
# 第 1 步：保存完整 patch（含 pre-existing + STEP3 改动）
git diff 代码文件/lib/cached_data_source.py > /tmp/cds_full_patch.diff

# 第 2 步：人工审阅 patch，识别哪些行是 STEP3 新增的（标记 SHADOW:）
#         哪些行是 pre-existing（无 SHADOW 标记）

# 第 3 步：使用 git checkout -p 逐块选择只回滚 STEP3 新增块
git checkout -p -- 代码文件/lib/cached_data_source.py
# 在交互提示中: y = 回滚该块 / n = 保留
# 只对带有 SHADOW 标记的块选 y，其他所有 pre-existing 块选 n

# 第 4 步：验证 pre-existing dirty 未被覆盖
git diff 代码文件/lib/cached_data_source.py | head -20
# 应仍显示 pre-existing 内容（无 SHADOW 标记的行）
```

**如果 git checkout -p 不可用或不安全：**

```bash
# 方式 B：手工编辑文件，只删除 STEP3 新增的段落
# 在文件中搜索 "SHADOW:" 标记，删除对应代码块

# 方式 C：从保存的 patch 中用 git apply --reverse 只恢复特定块
# （需要精确的行号范围，操作复杂度高，建议用方式 A 或 B）
```

### 16.4 全量回退方法

```bash
# 安全方式：只删除纯新增文件，不改动 dirty 文件
for f in 代码文件/数据/unified_data_source.py scripts/run_shadow_diff.py \
         scripts/migrate_historical_kline.py; do
  if [ -f "$f" ]; then rm "$f"; fi
done

# 验证：只删除新增文件，不碰 dirty 文件
git status --short -- \
  代码文件/数据/ \
  scripts/run_shadow_diff.py \
  scripts/migrate_historical_kline.py \
  tests/
```

### 16.5 回滚后的验证

```bash
# UnifiedDataSource 已清除
test ! -f 代码文件/数据/unified_data_source.py && echo "UDS 已清除"

# Shadow 脚本已清除
test ! -f scripts/run_shadow_diff.py && echo "Shadow 脚本已清除"

# 正式日报入口完好（从未被修改）
grep -rn "unified_data_source\|UnifiedDataSource" 代码文件/tools/daily_orchestrator.py 重点股票/股票报告/ 2>/dev/null
# 预期：空

# Pre-existing dirty 未被覆盖
git diff 代码文件/lib/cached_data_source.py | wc -l
# 预期：约 130 行（与 STEP3 前一致）

---

## 17. 执行顺序（G3 阶段）

### Phase 1 — UnifiedDataSource 核心（纯新增，不碰旧文件）

```
第 1 步  创建 代码文件/数据/unified_data_source.py
         ├── class UnifiedDataSource（__init__ + 统一辅助方法）
         ├── _l2_degraded() — 普通数据缺口返回 data_source="degraded"
         ├── _not_available_in_step3() — STEP3 边界外返回 data_source="not_available_in_step3"
         ├── 10 个接口骨架（按分类使用对应降级方法）
         ├── L1 读取实现（get_quote / get_kline / get_financials）
         └── L2 degraded / not_available_in_step3 逻辑
第 2 步  编译验证 python3 -m py_compile 代码文件/数据/unified_data_source.py
第 3 步  创建 tests/test_d04_fallback.py（3 个用例）
第 4 步  运行 pytest tests/test_d04_fallback.py -v 确认基本降级逻辑
```

### Phase 2 — 独立 Shadow 验证（主干，不修改现有模块）

```
第 5 步  创建 scripts/run_shadow_diff.py（独立验证脚本）
         ├── 直接读取 legacy 源（kline_cache/data_full）
         ├── UnifiedDataSource 调用（同接口）
         └── diff 输出和报告
第 6 步  编译验证 python3 -m py_compile scripts/run_shadow_diff.py
第 7 步  运行 python3 scripts/run_shadow_diff.py --code 600114 --date <最近交易日>
         验证：
         - legacy vs UDS 差异在容差内 → PASS
         - L2 依赖接口返回 degraded → WARN 不 BLOCK
         - 日志写入 shadow_diff_log.jsonl
```

### Phase 3 — 闸门适配（不改阻断逻辑）

```
第 8 步  可选修改 scripts/check_numeric_source_consistency.py（新旧路径比对，SKIP 不阻断）
第 9 步  可选修改 scripts/check_freshness_degradation.py（新旧路径比对，SKIP 不阻断）
第 10 步 编译验证并运行 --dry-run 确认不 BLOCK
```

### Phase 4 — K 线收敛（可选工具）

```
第 11 步 创建 scripts/migrate_historical_kline.py
第 12 步 运行 python3 scripts/migrate_historical_kline.py --dry-run 验证
```

### Phase 5 — 验收

```
第 13 步 运行全部验收命令（§14.1-§14.9）
第 14 步 禁止范围确认（git status --short -- <path-limited>）
第 15 步 输出 STEP3 交付报告
```

### 未纳入第一轮 G3 的项（移至后续阶段）

```
(cached_data_source.py 改造)       ← 需用户额外确认
(daily_workflow.py --shadow-only)  ← 不在本轮
(正式报告入口切换)                  ← guarded cutover 阶段
```

---

## 18. 暂停点

### 18.1 当前暂停点

```
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
⛔
⛔   暂停点已到达 — 等待用户复查与确认（补修版）
⛔
⛔   当前阶段：STEP3 G2（技术方案设计·补修）— 已完成
⛔   方案文件：STEP3_G2_UnifiedDataSource影子接入实施方案.md
⛔
⛔   本次补修内容：
⛔     1. 所有验收命令已加入 sys.path.insert 显式路径
⛔     2. 第一轮 G3 不再修改 daily_workflow.py
⛔     3. cached_data_source.py 降级为谨慎待确认项（第一轮不强制）
⛔     4. run_shadow_diff.py 作为第一轮主验证入口
⛔     5. 回滚方案移除危险默认 git checkout 命令
⛔     6. 收紧 compute_factor_ic / export_factor_panel / compare 边界
⛔     7. 加入新安 G2 复查角色
⛔
⛔   后续触发条件：
⛔     用户必须明确回复 "确认进入 STEP3 G3" 方可进入实施
⛔
⛔   未经用户明确授权：
⛔     - 阿黑不得自动进入 G3
⛔     - 阿黑不得实施任何修改
⛔     - 阿黑不得创建 UnifiedDataSource 文件
⛔     - 阿黑不得创建 l2_cache.db
⛔     - 阿黑不得修改 cached_data_source.py
⛔     - 阿黑不得修改 daily_workflow.py
⛔     - 阿黑不得代签角色结论
⛔     - 阿黑不得绕过 actor/HMAC
⛔⛔
⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔ ⛔
```

### 18.2 进入 G3 的判定条件

只有同时满足以下条件，才允许进入 STEP3 G3：

1. ✅ 用户复查接受修订后的 G2 方案
2. ✅ 用户明确回复：
   - `"确认进入 STEP3 G3"`
   - 或 `"同意本方案，请进入 G3"`
3. ✅ 红结按允许范围实施
4. ✅ 阿黑不得自行解释为已授权
5. ✅ formal pipeline actor/HMAC 若仍无法推进，继续明示为例外，不得伪造 sign-off

### 18.3 G3 及后续路线

```
用户确认 → G3（红结实施）
  → Phase 1 (UnifiedDataSource 核心)
  → Phase 2 (独立 Shadow 验证)
  → Phase 3 (闸门适配，可选)
  → Phase 4 (K 线收敛，可选)
  → G4（红结·自检）
  → G5（旧影·独立复查）
  → G6（腰子放行 + 用户确认）
  → 进入 STEP4 或暂停
```

### 18.4 本方案落盘文件

```text
文件路径：00_项目地基/02_数据架构重设计/五步优化接力包/STEP3_G2_UnifiedDataSource影子接入实施方案.md
状态：G2 方案已落盘（补修版），暂停等待复查
本轮修改：仅更新本方案文件，未修改任何代码
```

---

*流程编号：F-ARCH + F-DATA + F-GATE | 当前阶段门：G2（技术方案设计·补修版）*
*状态：方案已落盘，暂停等待复查 | 输出人：阿黑（路由+汇总）*
*本轮声明：未实施 G3、未创建 UnifiedDataSource、未创建 l2_cache.db、未修改 cached_data_source.py、未修改 daily_workflow.py、未代签角色结论、formal pipeline 未 advance*
