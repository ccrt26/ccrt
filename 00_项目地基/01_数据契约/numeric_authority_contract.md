# 数值权威契约

> 版本: 1.0 | 生效日期: 2026-06-02 | 维护人: 玉夜+腰子+阿黑

---

## 一、数值权威源定义

所有日报、sidecar、统一解读引用数值字段时，按以下权威源表查询。

| 字段类别 | 权威源路径 | 日期格式 | 允许延迟 |
|:---------|:-----------|:--------|:--------|
| **行情 K 线** | `代码文件/数据/kline_cache/{code}.json` | YYYY-MM-DD | T+0 |
| **四档资金** | `代码文件/数据/fund_flow_cache/{code}.json` | YYYYMMDD | T+0 |
| **融资融券** | `代码文件/数据/tushare/margin_detail/{code}.json` | YYYYMMDD | T+1 |
| **板块相位** | `代码文件/数据/data_scored.json` | 嵌入日期 | — |

---

## 二、板块相位权威源规则

板块相位（SectorPhase）的权威源为 `代码文件/数据/data_scored.json`。

查询三个桶，按优先级顺序扫描：

1. **Recommendations**（重点推荐池）
2. **AllStocks**（全量股票池）
3. **VetoedStocks**（观察/否决池）

查到即返回，不再扫描后续桶。

**禁止事项：**
- ⛔ 不得修改 data_scored.json 来适配日报
- ⛔ 日报/sidecar 不得使用 data_scored 之外的板块相位来源
- ⛔ 日报不得自行判断板块相位替代 data_scored

---

## 三、字段映射文件

详细映射规则见：

```
00_项目地基/04_一致性闸门/numeric_field_mapping.json
```

该文件定义每个字段的：
- sidecar 路径
- 权威源路径
- 兼容字段名
- 单位转换规则
- 容差

---

## 四、P0-B source_snapshot_exception（第5.5-C）

P0-B 的 `check_margin()` 在检测到 MD 融资日期与 margin_detail 权威源最新日期不一致时，进入 `source_snapshot_exception` 分支。

### 进入条件
仅当 `MD_融資日期 != margin_detail[0].trade_date` 时进入。

### 7 个必须全部满足的条件
1. `report_generated_at` 存在且为合法 ISO 8601 时间
2. `source_snapshot.margin.latest_trade_date` 存在
3. `source_snapshot.margin.report_trade_date == trade_date`
4. `source_snapshot.margin.lag_days` 为 int，且等于 report_trade_date - latest_trade_date
5. `source_snapshot.margin.declared_in` 包含 `degraded_items`
6. MD 融资日期 == `source_snapshot.margin.latest_trade_date`
7. 当前 `margin_detail[0].trade_date > source_snapshot.margin.latest_trade_date`

### 结果
- 全部满足 → WARN「发布后数据更新」
- 任一不满足 → BLOCK（保持硬闸门）
- `degraded_items` 不能单独使 P0-B 通过
- 无 snapshot 的历史报告仍为 BLOCK

---

## 五、字段注册表

详细注册表见：

```
00_项目地基/02_权威注册表/numeric_field_registry.json
```

每个字段的注册信息包括：
- 字段名
- 数据类型
- 权威源
- 是否必填
- 用途描述

---

## 五、数据降级规则

| 字段类别 | 降级路径 | 需声明 |
|:---------|:---------|:------|
| 行情 K 线 | 主源不可用 → BLOCK，日报不得提交 | 当日 |
| 四档资金 | 主源→本地fund_flow_cache | 当日或T+1 |
| 融资融券 | 允许T+1延迟 | 需声明最新日期 |
| 板块相位 | 三个桶均无数据 → 禁止使用，报告不得引用 | — |

---

## 六、生成日报前必须执行的命令

```bash
# 全池数值一致性检查
python3 scripts/check_numeric_source_consistency.py --all --date <日期>
```

返回 PASS 10/0 后，日报生成才可提交。

---

## 七、违规处理

| 违规类型 | 检测方式 | 处理 |
|:---------|:---------|:-----|
| 字段值与权威源不一致 | `check_numeric_source_consistency.py` | BLOCK，日报不得发布 |
| 引用 data_scored 之外来源 | 人工审查 | BLOCK |
| 使用未注册字段 | `numeric_field_registry.json` 对照 | WARN |
