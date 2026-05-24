# score_history.jsonl — Schema 定义

> v2026-05-24 | 情墨设计 + 腰子审核 + 红结实现

## 格式

每行一个JSON对象（JSONL），UTF-8编码。旧记录可能缺少新增字段，读取端必须使用 `.get(key, default)` 防御。

## 字段定义

### 基础标识

| 字段 | 类型 | 说明 | 版本 |
|------|------|------|------|
| date | string | 评分日期 YYYY-MM-DD | v2.9 |
| code | string | 股票代码 | v2.9 |
| name | string | 股票名称 | v2.9 |
| industry | string | 申万大类行业 | v2.9 |
| phase | string | 板块相位: 潜伏期/主升调整/高潮期/衰退期 | v2.9 |

### 行情快照

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| price | float | 当日收盘价 | [1] |
| change_pct | float | 涨跌幅(%) | [1] |
| turnover | float | 换手率(%) | [1] |
| pe | float | PE(原始值，保留兼容) | [3] |

### PE(TTM) — v2026-05-24 新增

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| pe_source | string | PE来源标注: "[5]TTM自算(Price/EPS)" / "[3]东财PE(兜底,非TTM)" / "不可得" | [5] |
| pe_ttm | float | PE(TTM) = Price[1]/TTM_EPS[3] | [5] |
| ttm_eps | float | 用于PE(TTM)计算的EPS值 | [3] |

### 六维评分

| 字段 | 类型 | 说明 |
|------|------|------|
| S_Base | int | 基础评分(0-10) |
| S_Fund | int | 基本面评分(0-15) |
| S_Tech | int | 技术面评分(0-20) |
| S_Money | int | 资金面评分(0-20) |
| S_News | int | 消息面评分(0-15) |
| S_Risk | int | 风控评分(0-5) |
| S_SectorTrend | int | 板块趋势评分(0-20) |
| TotalScore | int | 总分(0-100) |

### 技术面子项(8项) — v2.4

| 字段 | 类型 | 说明 |
|------|------|------|
| S1_MA | int | 均线系统(0-6) |
| S2_Converge | int | 均线收敛发散(0-3) |
| S3_Volume | int | 量价蓄势(0-5) |
| S4_Support | int | 底部支撑(0-4) |
| S5_RSI | int | RSI位置(0-3) |
| S6_MACD | int | MACD(0-2) |
| S7_Breakout | int | 突破确认(0-2) |
| S8_Momentum | int | 趋势动量(0-6) |
| raw_tech | int | 技术面原始分(0-27) |

### 估值指标 — v2026-05-24 新增

| 字段 | 类型 | 说明 | 适用路径 |
|------|------|------|----------|
| peg | float\|null | PEG = PE/增长率 | 强成长路径 |
| pb | float\|null | PB = Price/BPS | 周期成长路径 |
| ps | float\|null | PS = 市值/营收 | 强成长路径 |
| eps_growth | float\|null | 用于PEG的增长率(%) | 强成长路径 |
| growth_source | string | 增长率来源: "[11]一致预期" / "[TTM]历史增速" / "[TTM]营收代理" | - |

### 题材与相位 — v2026-05-24 新增

| 字段 | 类型 | 说明 |
|------|------|------|
| theme_path | string | 题材路径: 强成长/周期成长/稳定价值 |
| phase_multiplier | float | 相位折扣乘数(1.0/0.75/0.55/0.45) |
| veto_status | string | 否决状态: "passed"/V1-V6/C1-C8 |

### 技术指标 — v2026-05-24 新增

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| adx14 | float\|null | ADX(14) 趋势强度 | [5] |
| bb_upper | float\|null | 布林带上轨(20,2) | [5] |
| bb_lower | float\|null | 布林带下轨(20,2) | [5] |
| obv | float\|null | OBV能量潮最新值 | [5] |

### 超额收益

| 字段 | 类型 | 说明 |
|------|------|------|
| car5 | float\|null | 5日超额收益(%) = 个股5日涨幅 - 全市场中位数 |
| ret_t1 | float\|null | T+1收益(%) 由backfill_returns.py回填 |
| ret_t3 | float\|null | T+3收益(%) |
| ret_t5 | float\|null | T+5收益(%) |
| ret_t1_vs_market | float\|null | T+1相对大盘收益(%) |

## 版本兼容性

- **v2.9 (2026-05-24前)**: 30个字段，不含pe_source/pe_ttm/peg/pb/ps/car5/eps_growth/growth_source/phase_multiplier/theme_path/veto_status/adx14/bb_upper/bb_lower/obv
- **v2026-05-24+**: 46个字段，读取端必须对缺失字段使用 `.get(key, default)`

## 数据加载

推荐使用 `engine.load_history(date_range=None)` 统一加载，自动处理JSON解析异常和日期过滤。
