# 设计文档：巡检脚本一致性检查修复

**设计日期**: 2026-05-27
**设计者**: 情墨
pipeline_stage: complete
finance_confirmed: true
**代码等级**: L0（工具/数据层）

---

## 1. 问题

巡检报告3个WARN（0525/0526/0527）的 `scored vs full 股票数不一致` 是虚警。

### 根因

`inspect_data_health.py:166` 用错了字段：

```python
scored_count = len(scored['data'].get('AllStocks', []))  # 只含passed股
full_count = len(full['data'].get('Stocks', []))          # 全部入池股
```

评分引擎输出中，`AllStocks` 只包含 **passed** 股票，vetoed股票在 `VetoedStocks` 中。应比对 `Summary.Total`。

### 验证

三个"WARN"日的实际数据完全一致：
- 0525: scored.Summary.Total=134, full.Stocks=134 ✓
- 0526: scored.Summary.Total=53, full.Stocks=53 ✓
- 0527: scored.Summary.Total=53, full.Stocks=53 ✓

### 附加问题

0527 `snapshot` 缺失——当日交易快照尚未生成（盘后管线产出）。巡检不应为当日未收盘日期报 snapshot 缺失。

## 2. 修复

| # | 位置 | 变更 |
|:--|:-----|:-----|
| 1 | `check_consistency()` L166 | `len(AllStocks)` → `Summary.Total`（回退 to `len(AllStocks)+len(VetoedStocks)`） |
| 2 | snapshot检查 | 当日(today)的snapshot缺失不报WARN |

## 3. 需求→代码核对

| 需求 | 状态 |
|:-----|:----:|
| scored/full比对使用正确字段 | 待实现 |
| 当日snapshot不误报 | 待实现 |
| 巡检0525/0526/0527全部PASS | 待验证 |
