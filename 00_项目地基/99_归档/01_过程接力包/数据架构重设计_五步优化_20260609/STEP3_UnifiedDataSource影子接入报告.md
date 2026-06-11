# STEP3 UnifiedDataSource 影子接入报告

> 流程编号：F-ARCH + F-DATA + F-GATE
> 阶段门：G3/G4（同阶段补修）
> 日期：2026-06-09
> formal pipeline actor/HMAC：未通过，继续作为明示例外
> 本次不等同于 formal pipeline PASS

---

## 一、接入概览

### 1.1 新增文件

| 文件 | 用途 |
|:-----|:------|
| `代码文件/数据/unified_data_source.py` | UnifiedDataSource 核心类，10 接口 + 两类降级 helper |
| `scripts/run_shadow_diff.py` | 独立 shadow diff 验证脚本（第一轮主验证入口） |
| `scripts/migrate_historical_kline.py` | K 线三处散落收敛到 L2 SQLite |
| `tests/test_d04_fallback.py` | 5 个 fallback 回归测试用例 |

### 1.2 未修改文件

| 文件 | 理由 |
|:-----|:------|
| `cached_data_source.py` | 第一轮禁止修改（pre-existing dirty） |
| `daily_workflow.py` | 第一轮禁止修改（shadow 通过独立脚本完成） |
| `daily_orchestrator.py` | 日报入口不接入 UDS |

## 二、UnifiedDataSource 接口清单

| 接口 | 类型 | L1/L2 | 降级分类 |
|:-----|:------|:-------|:---------|
| `get_quote` | 数据读取 | L1 | —（直接返回） |
| `get_kline` | 数据读取 | L1+L2 自动降级 | A 类（degraded） |
| `get_score_history` | 数据读取 | L2+L3 降级 | A 类（degraded） |
| `get_financials` | 数据读取 | L1+L2 自动降级 | A 类（degraded） |
| `get_macro` | 数据读取 | L2 | A 类（degraded） |
| `compare_current_vs_historical` | 暂存接口（→D07） | L2 预计算 | B 类（not_available_in_step3） |
| `compute_factor_ic` | 暂存接口（→D06） | L2 预计算 | B 类（not_available_in_step3） |
| `get_max_drawdown` | 暂存接口（→D08） | L2 预计算 | B 类（not_available_in_step3） |
| `get_volatility_percentile` | 暂存接口 | L2 预计算 | B 类（not_available_in_step3） |
| `export_factor_panel` | 暂存接口（→D06） | L2 预计算 | B 类（not_available_in_step3） |

## 三、两类降级 helper

### A 类：`_l2_degraded()` — 普通数据缺口

```python
def _l2_degraded(self, interface_name: str) -> dict:
    self._stats["degraded"] += 1
    return self._make_result(
        data_source="degraded",
        status="SKIP",
        data=None,
        warnings=[f"L2 l2_cache.db 不存在，接口 {interface_name} 跳过 L2 分支。"],
        ttl_hours=0,
    )
```

### B 类：`_not_available_in_step3()` — STEP3 边界外

```python
def _not_available_in_step3(self, interface_name: str, reason: str) -> dict:
    self._stats["not_available"] += 1
    return self._make_result(
        data_source="not_available_in_step3",
        status="SKIP",
        data=None,
        warnings=[reason],
        ttl_hours=0,
    )
```

## 四、当前限制

| 限制 | 说明 |
|:-----|:------|
| `l2_cache.db` 不存在 | L2 依赖接口全部 degraded 或 not_available_in_step3 |
| 预计算结果不可用 | compute_factor_ic/compare/export 等暂存接口返回 not_available_in_step3 |
| cached_data_source.py 未改造 | shadow 通过独立脚本运行，不嵌入 CachedDataSource 内部 |
| 日报/深度分析入口未修改 | 生产链路完全隔离 |

## 五、进入 Phase 2 的前提

如需后续将 UnifiedDataSource 接入日报链路，需先满足：

1. `l2_cache.db` 创建并填充数据
2. `cached_data_source.py` shadow 适配（需用户额外确认）
3. shadow diff 连续 N 日全部 PASS
4. 用户明确授权 guarded cutover
