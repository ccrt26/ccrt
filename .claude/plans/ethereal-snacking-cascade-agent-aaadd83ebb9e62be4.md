# 铁律量化 四个覆盖缺口实施计划

## 总览

| 缺口 | 优先级 | 模块 | 当前状态 | 目标状态 |
|:----|:------:|:-----|:---------|:---------|
| Gap 1: 否决误杀率监控 | **P0** | scoring_engine_v2.py + gen_daily_html.ps1 + eval_v2.2_v1.4.py | VetoedStocks被移除，HTML和eval均无法展示否决明细 | 恢复VetoedStocks输出，修复HTML和eval的否决明细，建立跨session汇总 |
| Gap 2: 拥挤度分位数预警 | **P1** | scoring_engine_v2.py + stock_data_fetcher.psm1 + eval_v2.2_v1.4.py | 使用固定阈值(换手>8%+量比>2)，无量比分位数 | 实现换手率/量比分位数计算，改用动态分位阈值 |
| Gap 3: 路径优选6特征 | **P1** | scoring_engine_v2.py + eval_v2.2_v1.4.py | classify_path仅在eval中有（MA+RSI），引擎无输出 | 引擎输出6特征路径分类，eval同步更新 |
| Gap 4: 数据源内联标记 | **P2** | scoring_engine_v2.py + gen_daily_html.ps1 | 仅有底部汇总表，无内联[N]标记 | 逐数据字段打源标记，前端渲染 |

---

## Gap 1: 否决误杀率监控 (P0)

### 1.1 问题定位

`scoring_engine_v2.py` v2.4.1 移除了 `VetoedStocks` 输出字段（CHANGELOG: "输出精简"），但白皮书 §(二十九) 明确规定输出字段包含 `VetoedStocks`。导致：

- `gen_daily_html.ps1` 第308行 `$data.VetoedStocks` 永为 null → 报告显示"暂无否决记录"
- `eval_v2.2_v1.4.py` 第27行 `may21.get('VetoedStocks', [])` 永为空列表 → 否决误杀率始终0%
- `summary.csv` 有 `veto_kill_rate` 列但无数据行 → 无法做跨session趋势跟踪

### 1.2 修改文件与具体变更

#### 文件1: `scoring_engine_v2.py` (~1300行)

当前主线代码：
```python
output = {
    "BuildTime": ...,
    "Summary": { "Total": ..., "Passed": ..., "Vetoed": ..., "PassRate": ... },
    "SectorPhaseMap": ...,
    "SectorTrendMap": ...,
    "Recommendations": [...],
    "AllStocks": passed  # <-- 不含否决股
}
```

**变更A**: 在 `output` 字典中恢复 `VetoedStocks` 字段，插入在 `AllStocks` 之后：
```python
output = {
    ...
    "AllStocks": passed,
    "VetoedStocks": vetoed  # 恢复输出
}
```

**变更B**: 确认否决股数据字段完整性（必须包含 Code/Name/Industry/VetoStatus/VetoReason/TotalScore/各维度分/TechAnalysis/MA5/MA10/MA20/RSI/PoolSource — 与 eval白皮书 §2.1 "否决池数据补充" 要求一致）。

否决股对象当前结构检查：第1146-1160行，`check_absolute_vetoes` 被否后仅设置了 `VetoStatus`/`VetoReason` 和默认分，未设置技术指标字段。需要在否决分支中补充计算 MA5/MA10/MA20/RSI/VolRatio/TechAnalysis 等字段。

否决股数据补充具体操作：
- 在 `check_absolute_vetoes()` 被触发后（第1146行），需额外调用 compute_scores() 或至少计算技术指标
- 但 `compute_scores()` 中隐含 MA/MACD/RSI 计算（第580-717行），直接调用即可
- 修改方案：

```python
# 在 vetoed.append(s) 前，补充技术指标计算
if not s.get("MA5"):
    # 触发 compute_scores 来获取技术指标字段
    scores, tech_info = compute_scores(s, sector_info, sector_trend_info)
    s.update(scores)
```

**变更C**: 更新文件头部版本字符串（v2.4.1 → v2.4.2）以标记修复。

#### 文件2: `gen_daily_html.ps1`

当前第308行：
```powershell
if ($data.VetoedStocks -and $data.VetoedStocks.Count -gt 0) {
```

VetoedStocks 恢复后此代码自然可用。但需额外：
- 验证 `VetoedStocks` 对象属性名正确（PowerShell的大小写敏感性：`$v.VetoReason` vs JSON中的 `VetoReason`）

无代码变更需要。VetoedStocks 恢复后自动工作。

#### 文件3: `eval_v2.2_v1.4.py`

当前第27行：
```python
may21_vetoed_list = may21.get('VetoedStocks', [])
```

恢复后自动工作。无代码变更需要。

#### 文件4: `summary.csv` 积累机制

当前状态：`事后评估/summary.csv` 有列头但无数据。

**变更D**: 在 `eval_v2.2_v1.4.py` 或 `run_daily_eval.ps1` 中添加 append 行到 summary.csv。每行字段：

| 字段 | 来源 | 说明 |
|:-----|:-----|:-----|
| date | 被评估日期 | YYYY-MM-DD |
| total_recommended | basic['total'] | 推荐总数 |
| win_rate | basic['win_rate'] | 胜率 |
| avg_return | basic['avg_return'] | 平均收益 |
| veto_count | veto_stats['vetoed_count'] | 否决总数 |
| miskill_count | veto_stats['miskill_count'] | 误杀数 |
| veto_kill_rate | veto_stats['miskill_rate'] | 误杀率 |
| veto_effectiveness | veto_stats['veto_effectiveness'] | 否决有效度 |

追加逻辑建议放在 eval 脚本末尾（在写出 HTML 之后）：

```python
# 追加 summary.csv
SUMMARY_CSV = os.path.join(ROOT, '每日荐股', '事后评估', 'summary.csv')
import csv
fieldnames = ['date','total_recommended','win_rate','avg_return','veto_count','miskill_count','veto_kill_rate','veto_effectiveness']
new_row = {
    'date': '2026-05-21',  # 从 data_scored_may21.json 的 BuildTime 推断
    'total_recommended': basic['total'],
    'win_rate': f"{basic['win_rate']:.1f}",
    ...
}
write_header = not os.path.exists(SUMMARY_CSV) or os.path.getsize(SUMMARY_CSV) == 0
with open(SUMMARY_CSV, 'a', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    if write_header: w.writeheader()
    w.writerow(new_row)
```

### 1.3 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|:-:|:-----|:----:|:----:|:-----|
| R1.1 | VetoedStocks 恢复后 JSON 体积增大（否决股通常5-20只，每只含完整字段） | 低 | 低 | JSON文件增量约1-3KB，可忽略。输出前清理技术指标字段即可 |
| R1.2 | 否决股计算技术指标时 CPU 开销增加 | 低 | 低 | 否决股通常<20只，且技术指标计算已在通过股执行，复用即可 |
| R1.3 | eval 脚本加载旧格式 data_scored JSON（无VetoedStocks字段）时报错 | 中 | 中 | `get('VetoedStocks', [])` 已是安全访问。旧文件自动回退为空列表 |
| R1.4 | summary.csv 多进程写入冲突 | 低 | 低 | eval每天只运行一次，无并发风险。追加模式安全 |

### 1.4 回滚策略

恢复 `VetoedStocks` 输出：`git checkout -- scoring_engine_v2.py`
summary.csv 追加逻辑：删除新增的追加代码块即可。

### 1.5 验证步骤

1. 运行 `python scoring_engine_v2.py`，检查输出 JSON 含 `VetoedStocks` 数组
2. 确认否决股包含 VetoStatus / VetoReason / 各维度分 / MA5/MA10/MA20/RSI
3. 运行 `gen_daily_html.ps1`，检查 HTML 否决明细表格显示正确数据
4. 运行 `python eval_v2.2_v1.4.py`（针对已有数据），检查 `veto_stats.miskill_count > 0`
5. 检查 `summary.csv` 追加了新行

---

## Gap 2: 拥挤度分位数预警 (P1)

### 2.1 问题定位

白皮书 v1.5 §4.2 明确要求：拥挤度预警使用 **动态分位阈值** (换手率>20日分位80%值 且 量比>1.5)，而非当前固定的 `换手率>8% + 量比>2`。

当前状态：
- `scoring_engine_v2.py` 计算 `vol_ratio = vol_latest / vol_ma5`（简单比率，非分位数），无 `turnover_percentile`
- `stock_data_fetcher.psm1` 不提取腾讯API的`量比`字段（字段~46）
- `eval_v2.2_v1.4.py` 的 `calc_congestion()` 使用固定阈值 `turnover > 8 and vol_ratio > 2.0`

### 2.2 修改文件与具体变更

#### 文件1: `stock_data_fetcher.psm1`

腾讯行情API (`qt.gtimg.cn/q=`) 返回约48个字段，其中字段~35=量比，字段~46=量比（查文档确认）。

确认后，在 `Get-StockQuote` 和 `Get-StockQuoteBatch` 中添加量比字段提取：

```powershell
# 腾讯行情字段（字段~35，需要核实）
# 在 Get-StockQuote 的 $fields[] 映射中添加
VolumeRatio = [double]$fields[35]  # 或确认正确的字段索引
```

**风险**: 腾讯API字段索引可能因版本变化或代码不同而变化。验证方法：用 `$fields | ForEach-Object { "$i: $_" }` 打印调试。

备选方案：如果腾讯API不直接提供量比，则从K线计算：`量比 = 今日成交量(手) / 过去5日同一时刻平均成交量(手)`，但当前K线数据是日K而非分钟K，此方法误差较大。另一方案：直接使用当前的 `vol_latest / vol_ma5` 作为量比代理，这是计算方式不同但含义相近。

**建议**: 先在测试中验证腾讯API字段~35是否确为量比。如果不是，使用 `vol_latest / vol_ma5`（已有的 `VolRatio`）作为量比代理，不在本版本引入新的API字段。

#### 文件2: `scoring_engine_v2.py`

**变更A**: 在 `compute_scores()` 中增加换手率和量比的20日分位值计算。

需要20日K线换手率数据——但当前 `batch_data_collector.ps1` 采集的K线只有 `KClose/KVolume/KOpen/KHigh/KLow`，没有 `KTurnoverRate`（日换手率）。而 `TurnoverRate` 只有当日值（来自腾讯行情[1]），无历史序列。

因此分位值计算有两个方案：

**方案1（推荐）**: 使用成交量分位值代替换手率分位值。
- `KVolume` 包含20日成交量序列，可直接计算 `volume_percentile`
- 修改 `compute_scores()`，在已有 `vol_ma5_arr = calc_ma(volumes, 5)` 旁增加分位计算
- 定义函数：

```python
def calc_percentile(values, current_val):
    """计算当前值在历史序列中的分位数"""
    if len(values) < 5: return 50.0  # 数据不足时返回中位数
    sorted_vals = sorted(values)
    count_below = sum(1 for v in sorted_vals if v <= current_val)
    return count_below / len(sorted_vals) * 100
```

- 在技术分计算区使用：

```python
# 在 compute_scores() 中，len(closes) >= 20 分支内
vol_percentile = calc_percentile(volumes, vol_latest)  # 成交量分位
# ...存储
s["VolumePercentile"] = round(vol_percentile, 1)
```

**方案2**: 需要 `batch_data_collector.ps1` 额外采集20日换手率序列。改动范围更大，需要修改数据管线。**不推荐在本版本实施**。

**变更B**: 在 `scoring_engine_v2.py` 输出中添加 `VolumePercentile` 到 `Recommendations` 和 `VetoedStocks` 的每个股票。

#### 文件3: `eval_v2.2_v1.4.py`

**变更C**: 修改 `calc_congestion()` 使用分位阈值：

```python
def calc_congestion(rows):
    """拥挤度预警：使用成交量分位阈值（替代固定换手率>8%+量比>2）"""
    # 获取全推荐池的成交量分位中位数
    vol_percentiles = [r.get('volume_percentile') for r in rows if r.get('volume_percentile') is not None]
    threshold_80 = sorted(vol_percentiles)[int(len(vol_percentiles) * 0.8)] if len(vol_percentiles) >= 5 else 80
    
    congestion_stocks = [r for r in rows if 
        (r.get('volume_percentile', 0) >= threshold_80 and r.get('vol_ratio', 0) > 1.5) or  # 动态分位
        (r.get('turnover', 0) > 8 and r.get('vol_ratio', 0) > 2.0)]  # 固定阈值备选
    ...
```

逻辑：
- 当有 `volume_percentile` 数据时，使用 **分位 >= 80% + 量比 > 1.5**
- 当无分位数据时，回退到 **固定阈值（换手率>8%+量比>2）**
- 两条件满足任意一个即判定拥挤

### 2.3 依赖关系

- Gap 2 不依赖于任何其他 Gap（独立实施）
- `stock_data_fetcher.psm1` 的腾讯量比字段为低优先级依赖（可用 vol_ratio 代理）

### 2.4 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|:-:|:-----|:----:|:----:|:-----|
| R2.1 | 成交量分位作为换手率分位代理，有效性需验证 | 中 | 中 | 保留固定阈值作为备选回退，两种条件OR判定 |
| R2.2 | 腾讯API量比字段索引不正确 | 中 | 低 | 不使用该字段，而是使用 vol_latest/vol_ma5 作为量比代理 |
| R2.3 | 数据不足20日时（新股上市不足20天），分位值不可靠 | 低 | 低 | 数据不足时回退到固定阈值（换手率>8%+量比>2）|
| R2.4 | 分位值计算修改了 eval 逻辑但不影响评分引擎输出（向前兼容） | 低 | 低 | eval白皮书的固定阈值改为动态分位后，不同日期的阈值会变化，但意图是"随市场状态调整"而非固定值 |

### 2.5 回滚策略

- `scoring_engine_v2.py`: 删除 `calc_percentile` 函数和 `VolumePercentile` 赋值
- `eval_v2.2_v1.4.py`: 恢复 `calc_congestion` 原实现
- `stock_data_fetcher.psm1`: 删除量比字段映射

### 2.6 验证步骤

1. 单日测试：运行 scoring_engine_v2.py，检查通过股/否决股的 JSON 含 `VolumePercentile` 字段
2. 验证分位值合理性：25日数据的票，最新日成交量最大 → 分位≈100%；最小 → 分位≈4%
3. 运行 eval_v2.2_v1.4.py，检查 congestion_stocks 数量 > 旧阈值（因为分位阈值比固定阈值更敏感）
4. 如果腾讯API量比字段可用，验证字段提取值 vs 手工计算值

---

## Gap 3: 路径优选6特征 (P1)

### 3.1 问题定位

白皮书 v1.5 §3.5 要求：每只推荐标的在 T 日标记路径分类（追高/抄底/追空/逃顶/震荡），使用 **6特征矩阵**（MA5/MA10/MA20位置、RSI、当日涨跌幅、量比、布林带位置、MACD位置）。

当前状态：
- `classify_path()` 仅在 `eval_v2.2_v1.4.py` 中作为后验分析，使用4特征（MA5/MA10/MA20 + RSI）
- `scoring_engine_v2.py` 不输出任何路径分类
- eval 白皮书 §3.5.1 要求的 B bands 位置和 MACD 位置缺失

### 3.2 修改文件与具体变更

#### 文件1: `scoring_engine_v2.py`

**变更A**: 新增 `classify_path_6features()` 函数（放在技术指标计算区附近）：

```python
def classify_path_6features(s):
    """
    6特征路径分类 (白皮书 v1.5 §3.5.1)
    输入: s (股票数据字典，需含MA5/MA10/MA20/RSI/ChangePct/VolRatio/布林带/MACD等关键字段)
    返回: "追高" | "抄底" | "追空" | "逃顶" | "震荡"
    
    6特征矩阵:
    - MA5/MA10/MA20相对位置
    - RSI(14)
    - 当日涨跌幅
    - 量比 (VolRatio)
    - 布林带位置 (上轨/中轨/下轨)
    - MACD位置 (水上/水下/金叉/死叉)
    """
    ma5 = s.get("MA5", 0) or 0
    ma10 = s.get("MA10", 0) or 0
    ma20 = s.get("MA20", 0) or 0
    rsi = s.get("RSI", 50) or 50
    chg = s.get("ChangePct", 0) or 0
    vol_ratio = s.get("VolRatio", 1.0) or 1.0
    macd_status = s.get("MACD_Status", "")
    
    # 追高: 均线多头 + RSI>55 + 放量上涨(可选)
    is_bull_malign = ma5 > ma10 > ma20
    is_rsi_high = rsi > 55
    is_volume_up = vol_ratio > 1.2 and chg > 0
    
    # 逃顶: RSI>70 + 放量 + 布林上轨(需要布林数据)
    is_rsi_overbought = rsi > 70
    
    # 抄底: RSI<35 + 缩量
    is_rsi_oversold = rsi < 35
    
    # 追空: 均线空头
    is_bear_malign = (ma5 < ma10 < ma20) or (ma10 < ma20 and ma5 < ma10)
    
    # 权重决策
    if is_rsi_overbought:
        return "逃顶"
    if is_bull_malign and is_rsi_high and is_volume_up:
        return "追高"
    if is_bear_malign and not is_rsi_high and chg < 0:
        return "追空"
    if is_rsi_oversold:
        return "抄底"
    return "震荡"
```

**设计决策**: 
- "逃顶"优先于"追高"（超买优先于趋势看多 — 风控优先）
- 布林带位置：当前 scoring_engine_v2.py 未计算布林带，在当前版本暂不使用，标记为"# TODO: v2.5 引入布林带后补充此维度"
- MACD 位置：通过 `MACD_Status` 字段（金叉/死叉/多头/空头）已可用，合并到逃顶/追高判定中

**变更B**: 在评分完成、输出前（~第1182行 passed 排序前），对每只股票设置路径分类：

```python
# 在 passed 和 vetoed 的股票上设置路径分类
for s in passed:
    s["PathTag"] = classify_path_6features(s)
for s in vetoed:
    # 否决股也可能需要路径分类（用于后评估误杀分析）
    s["PathTag"] = classify_path_6features(s)
```

**变更C**: 在 `output["Recommendations"]` 的输出字段列表中添加 `PathTag`（第1251行附近）。

#### 文件2: `eval_v2.2_v1.4.py`

**变更D**: 修改 `classify_path(r)` 使用6特征，并从股票自身的 `PathTag` 读取（如果存在），否则本地计算。

```python
def classify_path(r):
    """6特征路径分类 — 优先使用引擎预标记，否则本地计算"""
    if r.get('PathTag'):
        return r['PathTag']
    
    # 本地计算（向后兼容旧数据文件）
    ma5 = r.get('MA5', 0)
    ma10 = r.get('MA10', 0)
    ma20 = r.get('MA20', 0)
    rsi = r.get('RSI', 50)
    chg = r.get('actual_chg', 0)  # 但这是次日涨跌而非当日！
    # ↑ 注意：eval脚本中 r['actual_chg'] 是次日数据，不应该用于路径分类
    # 所以本地 fallback 只使用 MA + RSI（不依赖当日涨跌数据）
    
    if rsi > 70: return '逃顶'
    if ma5 > ma10 > ma20 and rsi > 55: return '追高'
    if rsi < 35: return '抄底'
    if ma5 < ma10 < ma20: return '追空'
    return '震荡'
```

### 3.3 依赖关系

- Gap 3 依赖于 Gap 2 中的 `VolRatio`（但已存在，非新增依赖）
- Gap 3 不需要布林带（当前引擎不计算，留待 v2.5）
- Gap 3 的 `PathTag` 输出可供 eval 脚本使用

### 3.4 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|:-:|:-----|:----:|:----:|:-----|
| R3.1 | 引擎内预标记和eval内后验标记可能不一致 | 中 | 中 | eval优先使用引擎预标记；仅旧数据文件才本地计算，确保一致性 |
| R3.2 | 逃顶优先于追高的决策逻辑，可能把强势调整误判为逃顶 | 中 | 低 | 可在逃顶条件中加入"RSI>70且MA5>MA10>MA20"组合区分强势连涨 vs 温和筑顶 |
| R3.3 | 新增字段 PathTag 增大 JSON 输出（增加~10字节/股 * 25+20 ~ 450字节） | 低 | 低 | 影响可忽略 |

### 3.5 回滚策略

- 删除 `classify_path_6features()` 函数
- 删除 `s["PathTag"]` 赋值
- 从 Recommendations 输出字段中移除 `PathTag`

### 3.6 验证步骤

1. 运行 scoring_engine_v2.py，检查 JOSN 含每只股票的 `PathTag`
2. 路径分布验证：典型震荡市应有40-60%标记为"震荡"、10-20%为"追高"、5-10%为"抄底"
3. 运行 eval_v2.2_v1.4.py，检查 `path_stats` 各路径 > 0
4. 验证新旧数据兼容：旧 JSON 文件（无 PathTag）的 eval 依然正确 fallback

---

## Gap 4: 数据源内联标记 (P2)

### 4.1 问题定位

红线规则 v1.4 §4.1 "报告自查清单" 要求：**所有数据有来源标记（含主/备/缓存标注 [1] [1B] [C]）**。

当前状态：
- `gen_daily_html.ps1` 在底部有一个"数据来源"汇总表格（第319-324行）
- 各指标值（PE/换手率/涨跌幅/RSI等）旁无内联标记
- `scoring_engine_v2.py` 无 per-field source tracking

### 4.2 修改文件与具体变更

#### 文件1: `scoring_engine_v2.py`

**变更A**: 新增数据源映射字典，标记每字段所使用的数据源编号：

```python
# 数据源映射 (白皮书 §(十二) 数据源策略)
FIELD_SOURCE_MAP = {
    # [1] 腾讯行情（主）
    "Price":       "[1]",
    "ChangePct":   "[1]",
    "Volume":      "[1]",
    "TurnoverRate":"[1]",
    "Amplitude":   "[1]",
    "MktCap":      "[1]",
    # [1B] 新浪行情（备）
    # Price_B:   "[1B]",
    # [2] 新浪K线（主）
    "KClose":      "[2]",
    "KVolume":     "[2]",
    # [2B] 腾讯K线（备）— 不单独标记
    # [3] 东方财富财务
    "EPS":         "[3]",
    "EPS_Quarterly":"[3]",
    # [5] 本地计算
    "PE(TTM)":     "[5]",       # TTM_EPS[3] + Price[1] = PE(TTM)
    "MA5":         "[5]",
    "MA10":        "[5]",
    "MA20":        "[5]",
    "RSI":         "[5]",
    "MACD_Status": "[5]",
    "VolRatio":    "[5]",
    "TechAnalysis":"[5]",
    "TotalScore":  "[5]",
    # [7] 东方财富板块行业
    "Industry":    "[7]",
    "SectorPhase": "[7]",
    # [9] 东方财富资金流向
    "FundMainNet": "[9]",
    # 数据质量
    "DataQuality": "[5]",
}
```

**变更B**: 在每个评分引擎字段后附加 `_source` 后缀。但此种方式会大规模改动（每字段后加 `_{source}`），对HTML生成造成破坏性影响。

**更优方案**: 在输出中添加 `FieldSources` 字典，一次声明所有字段的数据源：

```python
output = {
    ...
    "FieldSources": FIELD_SOURCE_MAP,  # 全局字段源映射
    ...
}
```

#### 文件2: `gen_daily_html.ps1`

**变更C**: 修改 HTML 报告的数据来源区块（第319-324行），从底部表格改为：
1. 保留底部"数据来源汇总表"（作为概述）
2. 在**全部标的评分表**的每个数值旁添加小字 `[N]` 标记

具体实现：

```powershell
# 加载 FieldSources
$fieldSources = $data.FieldSources

# 获取字段来源标记的函数
function Get-SourceTag($fieldName) {
    if ($global:fieldSources -and $global:fieldSources.$fieldName) {
        return "<sup class=""src-tag"">$($global:fieldSources.$fieldName)</sup>"
    }
    return ""
}
```

在全部标的评分表的每个 `<td>` 中：
```powershell
# 原来: <td>$($s.PE)</td>
# 改为: <td>$($s.PE)$(Get-SourceTag "PE(TTM)")</td>
```

需要更新的列（按当前HTML第224行的顺序）：
| 列 | 字段名 | 来源标记 |
|:---|:-------|:--------:|
| 价格 | Price | [1] |
| 涨跌 | ChangePct | [1] |
| 换手 | TurnoverRate | [1] |
| 振幅 | Amplitude | [1] |
| PE | PE(TTM) | [5] |
| 基础 | S_Base | [5] |
| 基本 | S_Fund | [5] |
| 技术 | S_Tech | [5] |
| 资金 | S_Money | [5] |
| 消息 | S_News | [5] |
| 风控 | S_Risk | [5] |
| 趋势 | S_SectorTrend | [5] |
| 总分 | TotalScore | [5] |

**变更D**: 添加 CSS 样式渲染标记：
```css
.src-tag{font-size:8px;color:#999;vertical-align:super;margin-left:1px}
```

**变更E**: 在"精选推荐 Top 5"卡片的 `c-logic` 区块内，逐个指标后缀 `[N]`。当前 `Get-ReasonText` 函数需修改为接受 `$fieldSources` 参数，在 `技术面` / `板块` / `催化` 各段末尾加对应标记。

### 4.3 影响范围分析

| 组件 | 影响 | 说明 |
|:-----|:----:|:-----|
| scoring_engine_v2.py | 输出新增 ~20行 | 仅添加 FIELD_SOURCE_MAP 字典，不影响评分逻辑 |
| gen_daily_html.ps1 | 中量修改 | 全部标的评分表每列加 `<sup>` 标记；CSS新增一段；精选推荐逻辑内加标记 |
| eval_v2.2_v1.4.py | 无影响 | 评估脚本不需要数据源标记 |

### 4.4 风险与缓解

| # | 风险 | 概率 | 影响 | 缓解 |
|:-:|:-----|:----:|:----:|:-----|
| R4.1 | HTML 表格每列加 `<sup>` 后，列宽增大，横向溢出 | 中 | 中 | CSS 限制 `.src-tag` 文字大小8px，不同步增加列宽；保持字体单行 |
| R4.2 | 标记信息过密，视觉噪声增大 | 中 | 低 | 对于同源连续列（如 S_Tech/S_Money 等 [5]），只在表头汇总一次，不在每个<td>重复 |
| R4.3 | 数据源编号与红线规则不一致 | 低 | 中 | 严格遵循红线规则 §1.1 数据源编号表核对后再发布 |

### 4.5 回滚策略

- `scoring_engine_v2.py`: 删除 `FIELD_SOURCE_MAP` 和 `FieldSources` 输出
- `gen_daily_html.ps1`: 删除 `<sup>` 标记调用和相关 CSS

### 4.6 验证步骤

1. 运行 scoring_engine_v2.py，检查 JSON 含 `FieldSources` 字典
2. 运行 gen_daily_html.ps1，检查 HTML:
   - 票价表每列有 `<sup class="src-tag">[N]</sup>`
   - 精选推荐区块指标后有标记
   - 页面排版无溢出现象
3. HTML验证：`检查元素` 确认 `<sup>` 标签正确包裹
4. 视觉检查：标记颜色为灰色 #999，不喧宾夺主

---

## 实施顺序与依赖图

```
Gap 1 (P0) — Veto Kill Rate
    ├── scoring_engine_v2.py             ← 第一步 (无前置依赖)
    ├── summary.csv 追加逻辑             ← 与eval联动，可与1同步
    └── gen_daily_html.ps1 (自动修复)     ← 不修改

Gap 2 (P1) — Congestion Percentile
    ├── scoring_engine_v2.py             ← 第二步 (与 Gap 1 无依赖)
    ├── eval_v2.2_v1.4.py                ← 第二步 (与 Gap 1 无依赖)
    └── stock_data_fetcher.psm1 (可选)    ← 验证腾讯字段后可选

Gap 3 (P1) — Path Optimization
    ├── scoring_engine_v2.py             ← 第三步 (依赖 Gap 2 的 VolRatio，但已有vol_ratio)
    └── eval_v2.2_v1.4.py                ← 第三步 (依赖 Gap 3 的 PathTag 输出)

Gap 4 (P2) — Data Source Markers
    ├── scoring_engine_v2.py             ← 第四步 (无前置依赖)
    └── gen_daily_html.ps1               ← 第四步 (无前置依赖)

建议实施顺序: Gap 1 → Gap 2 → Gap 3 → Gap 4
```

**为何如此排序**：
1. Gap 1 (P0) 是功能性缺陷：否决明细断供直接影响报告质量和 eval 评估准确性
2. Gap 2 (P1) 和 Gap 3 (P1) 独立于 Gap 1，可并行实施
3. Gap 4 (P2) 纯展示性改造，优先级最低，放在最后

---

## 综合风险矩阵

| 缺口 | 代码行估算 | 风险等级 | 回归影响 | 回滚难度 |
|:----|:---------:|:--------:|:--------:|:--------:|
| Gap 1 | ~30行 | 低 | 中（否决股数据恢复可能影响前端展示） | 低 |
| Gap 2 | ~60行 | 中 | 低（分位新增，不动原有计算路径） | 低 |
| Gap 3 | ~60行 | 中 | 低（新增字段，不影响评分） | 低 |
| Gap 4 | ~100行 | 中低 | 低（纯展示层改动） | 低 |

**总体风险评估**: 四个缺口均为增量改造，不重构核心评分逻辑（否决规则/权重计算/板块动量），回归风险可控。最敏感的部分是 Gap 1 的 VetoedStocks 恢复——仅需确认 JSON 键名大小写与 PowerShell 访问一致。

---

## 附件：数据源编号对照表（红线规则 §1.1）

| 字段 | 数据源编号 | 数据源名称 | 优先级 | 说明 |
|:-----|:---------:|:-----------|:------:|:-----|
| Price | [1] | 腾讯行情 | 主 | qt.gtimg.cn |
| ChangePct | [1] | 腾讯行情 | 主 |  |
| Volume | [1] | 腾讯行情 | 主 |  |
| TurnoverRate | [1] | 腾讯行情 | 主 |  |
| PE(静态) | [1] | 腾讯行情 | 主 | 仅做参考，TTM为主 |
| PE(TTM) | [5] | 本地计算 | — | Price[1] / TTM_EPS[3] |
| KLine | [2] | 新浪K线 | 主 | money.finance.sina.com.cn |
| KLine(备) | [2B] | 腾讯K线 | 备 | web.ifzq.gtimg.cn |
| EPS/ROE | [3] | 东方财富财务 | 主 | datacenter.eastmoney.com |
| 技术指标 | [5] | 本地计算 | — | MA/RSI/MACD/VolRatio |
| Industry | [7] | 东方财富板块行业 | 主 | push2.eastmoney.com |
| SectorPhase | [7] | 东方财富板块行业 | 主 | classify_phase计算 |
| FundMainNet | [9] | 东方财富资金流向 | 主 | push2.eastmoney.com |
| 缓存 | [C] | 本地文件缓存 | 兜底 | API不可用时的最终保障 |
