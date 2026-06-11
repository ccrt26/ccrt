# 日期新鲜度与降级路径权威契约

> 版本: 1.0 | 生效日期: 2026-06-02 | 维护人: 玉夜+阿黑

---

## 一、契约目的

定义日报中每个数据类别的新鲜度标准和降级处理规则，确保报告引用的数据不会因过期、缺失或降级未声明而影响决策质量。

---

## 二、权威数据类别

本契约覆盖以下 6 类数据的新鲜度检查：

| 编号 | 数据类别 | 权威源 |
|:----:|:---------|:-------|
| A | K 线行情 | `代码文件/数据/kline_cache/{code}.json`（L1 当日）+ `代码文件/数据/l2_cache/l2_cache.db`（L2 历史，Phase 2 启用） |
| B | 四档资金 | `代码文件/数据/fund_flow_cache/{code}.json` |
| C | 融资融券 | `代码文件/数据/tushare/margin_detail/{code}.json` |
| D | 板块相位 | `代码文件/数据/data_scored.json`（三桶） |
| E | Baseline | `00_项目地基/02_权威注册表/baseline_registry.json` |
| F | Eval_hooks | sidecar 内嵌 |

---

## 三、数据中台新鲜度权威分层（D04 / L1/L2/L3）

### 3.1 三层权威源新鲜度规则

| 层级 | 定位 | 新鲜度要求 | 降级策略 |
|:-----|:-----|:-----------|:---------|
| **L1** | 当日权威 | T+0 必须存在当日记录 | 不可降级——L1 缺失 → BLOCK，日报不得提交 |
| **L2** | 历史权威（Phase 2 启用） | 允许 T+1 延迟 | 降级至 L1（WARN 记录） |
| **L3** | 归档权威 | 周级快照，仅审计追溯 | 不被程序常规读取 |

### 3.2 新鲜度裁决规则

1. **当日判断以 L1 为准**：freshness 检查以 L1（kline_cache / fund_flow_cache）为先，L1 有当日数据即 PASS。
2. **历史分析以 L2 补充**：超过 kline_cache 覆盖范围（122 天+）的历史查询回源 L2 SQLite。freshness 检查对 L2 仅做 WARN。
3. **L3 不被闸门检查**：L3 归档数据不参与当日 freshness 判定。
4. **STEP1 注册不启用**：kline_l2 规则的 `enabled: false`、`phase: 2`，Phase 2 前 freshness 闸门仅基于 L1 路径。

### 3.3 权威源路径

| 层级 | 权威源路径 | freshness 规则引用 |
|:-----|:-----------|:------------------|
| L1 K 线 | `代码文件/数据/kline_cache/{code}.json` | `freshness_rules.json → rules.kline` |
| L2 K 线 | `代码文件/数据/l2_cache/l2_cache.db (kline表)` | `freshness_rules.json → rules.kline_l2`（Phase 2 启用） |
| L1 资金流 | `代码文件/数据/fund_flow_cache/{code}.json` | `freshness_rules.json → rules.fund_flow` |

---

## 四、K 线新鲜度规则

| 维度 | 规则 |
|:-----|:------|
| 权威源 | `代码文件/数据/kline_cache/{code}.json` |
| 日期格式 | `YYYY-MM-DD` |
| 要求 | T+0 必须存在 trade_date 当日记录 |
| **缺失** | ⛔ **BLOCK**，日报不得提交 |
| **日期不匹配** | ⛔ **BLOCK**，报告声称"当日"但缓存无当日记录 |

---

## 五、四档资金新鲜度规则

| 维度 | 规则 |
|:-----|:------|
| 权威源 | `代码文件/数据/fund_flow_cache/{code}.json` |
| 日期格式 | `YYYYMMDD` |
| 要求 | T+0 必须匹配 trade_date |
| **缺失** | ⛔ **BLOCK**，日报不得提交 |
| **日期不匹配** | ⛔ **BLOCK**，source 声称当日但实际不是 |
| **已声明降级** | ⚠️ **WARN**，允许但不推荐 |

---

## 六、融资融券新鲜度规则

| 维度 | 规则 |
|:-----|:------|
| 权威源 | `代码文件/数据/tushare/margin_detail/{code}.json` |
| 日期格式 | `YYYYMMDD` |
| 允许延迟 | **T+1**（常规），**T+2**（降级容忍极限） |
| **T+1 内且已声明** | ✅ **PASS** |
| **T+2 内且已声明** | ⚠️ **WARN** |
| **超过 T+2 且未声明降级** | ⛔ **BLOCK** |
| **超过 T+2 且已声明降级** | ⚠️ **WARN** |
| **文件缺失且不影响动作** | ⚠️ **WARN** |
| **文件缺失且融资作为动作依据** | ⛔ **BLOCK** |

---

## 七、板块相位新鲜度规则

| 维度 | 规则 |
|:-----|:------|
| 权威源 | `代码文件/数据/data_scored.json`（承接第2阶段三家权威） |
| 查询桶 | Recommendations → AllStocks → VetoedStocks |
| **影响动作判断且缺失** | ⛔ **BLOCK** |
| **仅披露且缺失** | ⚠️ **WARN** |

---

## 八、Baseline 有效期规则

| 维度 | 规则 |
|:-----|:------|
| 权威源 | `00_项目地基/02_权威注册表/baseline_registry.json` |
| 有效期判定 | `baseline_date <= trade_date <= valid_until` |
| **无有效 baseline** | ⛔ **BLOCK** |
| **多有效 baseline** | ⛔ **BLOCK** |

---

## 九、Eval_hooks 日期规则

| 维度 | 规则 |
|:-----|:------|
| 来源 | sidecar.eval_hooks |
| **t1 日期早于 next_trade_date** | ⛔ **BLOCK** |
| **t5 日期不晚于 trade_date** | ⛔ **BLOCK** |
| **日期格式不可解析** | ⚠️ **WARN** |

---

## 十、降级声明规则

降级声明必须包含以下信息：

| 字段 | 说明 | 示例 |
|:-----|:------|:------|
| 数据类别 | 股票代码+数据类别 | 600114 margin |
| 权威源路径 | 实际数据源路径 | 代码文件/数据/tushare/margin_detail/600114.json |
| 应有日期 | 本应达到的日期 | 20260602 |
| 实际最新日期 | 缓存中能取到的最新年月日 | 20260527 |
| 延迟天数 | 应有日期与实际日期间隔 | 6天 |
| 是否影响决策 | 降级是否削弱了报告结论的可靠性 | 否 |
| 降级结论 | 综合判定 | WARN |

---

## 十一、禁止事项

| 禁止 | 说明 |
|:-----|:------|
| ⛔ 禁止通过修改历史日报适配闸门 | 历史报告保持原地不动 |
| ⛔ 禁止通过修改缓存数据适配闸门 | 缓存是权威源，不是适配目标 |
| ⛔ 禁止用口头说明替代降级声明 | 降级必须在 sidecar 中声明 |

---

## 十二、source_snapshot 与发布后数据更新（第5.5-C）

日报生成时，daily_orchestrator.py 必须在 sidecar 中写入：
- `report_generated_at`：报告生成时间（ISO 8601, Asia/Shanghai）
- `source_snapshot.margin`：融资数据快照（latest_trade_date, report_trade_date, lag_days, degraded, declared_in, source_path）

### source_snapshot_exception

P0-B 闸门在检测到 MD 融资日期与权威源不一致时，会进入 `source_snapshot_exception` 分支。该分支严格验证 7 个条件，全部满足时降为 WARN「发布后数据更新」。任一不满足仍为 BLOCK。

该机制不改变无 snapshot 的历史报告的 BLOCK 状态。

---

## 十三、生成前/生成后要求

| 阶段 | 要求 |
|:-----|:------|
| **日报生成前** | 必须执行 `python3 scripts/check_freshness_degradation.py --all --date <日期>`，确认无 BLOCK |
| **日报生成后** | 降级声明必须保留在 sidecar 的 `degraded_items` 字段中 |
