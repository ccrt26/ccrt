# 日报v1.8对齐工程 — 架构设计

> **pipeline_stage**: complete
> **设计者**: 情墨 | **日期**: 2026-05-26 | **触发**: 后评估白皮书v1.8 P0/P1待办

---

## 一、变更范围

| # | 任务 | 目标文件 | 等级 | 改动量 |
|:--|:-----|:--------|:----:|:------|
| T1 | 日报§2信号表增加P0/P1字段 | `gen_daily_brief.py` | L1 | ~60行 |
| T2 | 日报新增§4.5"一周情景展望" | `gen_daily_brief.py` | L1 | ~50行 |
| T3 | 新建日报→JSON解析脚本 | `Invoke-DailyReportParser.ps1`(新) | L0 | ~150行 |

> T4(P2维度追踪)无代码变更，已在改进日志中标记追踪。

---

## 二、T1: 信号表字段扩展

### 2.1 现有数据→新字段映射

gen_daily_brief.py 已从 eval JSON 中提取了大部分所需数据，只需在日报中显式输出：

| §2.2.2.0字段 | 优先级 | 现有变量 | 输出位置 | 改动 |
|:------------|:------|:---------|:--------|:----|
| `market_regime` | P0 | 无→需从大盘数据推断 | §1.1 大盘环境表 | 新增行 `市场状态: 牛/熊/震荡` |
| `market_breadth` | P0 | 无→需从大盘数据提取 | §1.1 大盘环境表 | 新增行 `涨跌比: X.X` |
| `ma_arrangement` | P0 | `ma_trend`(已有) | §2.1 技术四维表 | 已输出，加 `key: value` 标记 |
| `adx_value` | P0 | `adx`(已有) | §2.1 技术四维表 | 已输出数值 ✅ |
| `rsi_value` | P0 | `rsi`(已有) | §2.1 技术四维表 | 已输出数值 ✅ |
| `macd_signal` | P1 | 需从sig提取MACD状态 | §2.1 技术四维表 | 新增MACD行 |
| `volume_signal` | P1 | `vol_rel`(已有) | §2.1 技术四维表 | 已有量价关系，加标准化标签 |
| `wyckoff_stage` | P0 | `wyckoff`(已有) | §2.2 资金面表 | 已输出 ✅ |
| `fund_flow_direction` | P0 | `fund_flow`(已有) | §2.2 资金面表 | 已输出 ✅ |
| `sector_rank_percentile` | P1 | 需从板块数据计算 | §1.2 板块定位 | 新增百分位数值 |
| `bollinger_position` | P1 | `bb_pos`(已有) | §2.1 技术四维表 | 已输出 ✅ |

### 2.2 具体改动点（gen_daily_brief.py）

**改动1**: §1.1 大盘环境表增加 market_regime + market_breadth 行
```python
# 从 data['Market'] 或 stocks 的宏观数据提取
market_regime = "牛" if macro_score >= 80 else ("熊" if macro_score <= 20 else "震荡")
# 在MD模板中新增行: | 市场状态 | {market_regime} | {market_breadth} |
```

**改动2**: §2.1 技术四维表增加 MACD 行
```python
macd_signal = sig.get('MACD_Signal', '—')  # 从eval JSON读取
# 新增表行: | 趋势 | MACD | {macd_signal} | ... |
```

**改动3**: §1.2 板块定位增加 sector_rank_percentile
```python
sector_pct = sc.get('SectorPercentile', '—')  # 从板块数据
# 新增行: | 板块排名 | 前{sector_pct}% |
```

**改动4**: 各字段增加机器可解析的 `key: value` 注释标记
在日报HTML注释或Markdown中嵌入结构化标签：
```html
<!-- eval:market_regime=牛 -->
<!-- eval:market_breadth=10.5 -->
```

**决策**: 使用HTML注释而非纯文本标记——不影响日报阅读体验，同时正则可精确提取。替代方案（YAML front matter）会污染日报头部，否决。

---

## 三、T2: 一周情景展望(T+5)

### 3.1 新增位置

日报第四章"明日情景应对"之后、"核心矛盾"之前，新增 §4.5 "一周情景展望"。

### 3.2 生成逻辑

```python
def t5_outlook(sc, sig, kl, price):
    """Generate T+5 outlook based on current signals."""
    tech = sc['Technical']
    fund = sc['Fundamental']
    sector = sc['Sector']
    
    # T+5方向预判
    if tech >= 65 and sector >= 55:
        direction = "看多"
        confidence = "中"
    elif tech >= 65 and sector < 35:
        direction = "偏多"  # 技术好但板块弱，降低预期
        confidence = "低"
    elif tech < 40:
        direction = "偏空"
        confidence = "中" if fund <= 30 else "低"
    else:
        direction = "中性"
        confidence = "低"
    
    # T+5目标区间 (基于ATR或历史波动率估算)
    weekly_atr_pct = 0.05  # A股周波动率约5%
    target_high = round(price * (1 + weekly_atr_pct * (1 if direction in ("看多","偏多") else 0.5)), 2)
    target_low = round(price * (1 - weekly_atr_pct * (1 if direction in ("看空","偏空") else 0.5)), 2)
    
    # 相对大盘判断
    if sector >= 55 and fund >= 40:
        vs_market = "有望跑赢"
    elif fund <= 25:
        vs_market = "可能跑输"
    else:
        vs_market = "持平"
    
    # 关键验证点
    catalysts = []
    if sig.get('FundFlow_Trend') and "流入" in str(sig['FundFlow_Trend']):
        catalysts.append("主力资金是否持续流入")
    if sector >= 55:
        catalysts.append("板块能否维持强势排名")
    if fund <= 25:
        catalysts.append("基本面评分是否改善")
    if not catalysts:
        catalysts.append("大盘整体走势")
    
    return direction, confidence, target_high, target_low, vs_market, catalysts
```

### 3.3 MD模板片段

```markdown
## 四.5 一周情景展望 (T+5)

> 基于今日信号对未来5个交易日的预判，用于后评估§2.1.5主窗口验证

| 项目 | 内容 |
|:-----|:-----|
| T+5方向预判 | {direction} |
| T+5相对大盘 | {vs_market} |
| T+5目标区间 | {target_low:.2f}元 – {target_high:.2f}元 |
| 预判置信度 | {confidence} |
| 关键验证点 | {catalysts} |
```

---

## 四、T3: Invoke-DailyReportParser.ps1

### 4.1 脚本定位

- **等级**: L0（工具/数据/缓存）
- **输入**: `重点股票/股票报告/*/重点关注股票日报_YYYYMMDD.md`
- **输出**: `重点股票/次日评估/评估数据_YYYYMMDD.json`
- **调度**: 日报生成完成后手动或Task Scheduler触发

### 4.2 模块设计

```
Invoke-DailyReportParser.ps1
├── param([string]$Date)           # 日期参数，默认今天
├── Find-DailyReports              # 扫描日报文件
├── ConvertFrom-DailyReportMD      # 单个MD→PSObject（正则提取）
│   ├── 提取 scores (§3.7.3正则)
│   ├── 提取 signals
│   ├── 提取 technical_values
│   ├── 提取 price_levels
│   ├── 提取 daily_report_sections
│   └── 提取 data_source_status
├── Merge-EvalData                 # 合并所有股票→JSON
└── Export-EvalJson                # 写入JSON文件
```

### 4.3 正则提取规则（每个目标字段一行）

```powershell
$extractors = @{
    'scores.composite'   = '综合评分\*\*(\d+)分'
    'scores.technical'   = '技术(\d+)分'
    'signals.S01'        = 'MA排列.*?(多头排列)'
    'signals.S27'        = 'Wyckoff阶段.*?(Markup|Distribution|Accumulation|Markdown)'
    'adx'                = 'ADX\(14\).*?([\d.]+)'
    'rsi'                = 'RSI\(9\).*?([\d.]+)'
    'close_price'        = '收盘\*\*([\d.]+)元\*\*'
    'R1'                 = 'R1.*?([\d.]+)'
    'S1'                 = 'S1.*?([\d.]+)'
    'S3'                 = 'S3.*?([\d.]+)'
    'market_regime'      = '<!-- eval:market_regime=(\S+) -->'
    'market_breadth'     = '<!-- eval:market_breadth=([\d.]+) -->'
}
```

### 4.4 JSON输出Schema

严格按白皮书§3.7.2定义的结构输出。`[MISS]`标记的字段填null，`[INFER]`标记的字段附加`_quality: "infer"`。

### 4.5 错误处理

- 日报文件缺失 → Warn继续，该股票不进入当日JSON
- 正则匹配失败 → 字段标记`[MISS]`，不中断流程
- JSON写入失败 → Error退出，exit code 1

---

## 五、影响评估

| 模块 | 影响 | 风险 |
|:-----|:-----|:-----|
| gen_daily_brief.py | 修改MD模板+新增函数 | 低——纯增量，不改现有逻辑 |
| 日报.md输出格式 | 新增字段和章节 | 低——向后兼容，旧字段不变 |
| 新脚本 | 独立L0工具 | 低——不依赖其他模块，独立运行 |
| 后评估流程 | 日报→JSON链路打通 | 正向——解决v1.8识别的P0断层 |

---

## 六、需求→代码核对清单

| # | 需求来源 | 实现点 | 验证方式 |
|:--|:--------|:------|:--------|
| 1 | §2.2.2.0 P0字段 | gen_daily_brief.py输出7个P0字段 | 检查日报MD含market_regime/ma_arrangement/adx/rsi/wyckoff/fund_flow/breadth |
| 2 | §2.2.2.0 P1字段 | gen_daily_brief.py输出4个P1字段 | 检查日报MD含macd_signal/volume_signal/sector_pct/bollinger |
| 3 | §2.1.5 T+5展望 | gen_daily_brief.py新增t5_outlook() | 检查日报含"一周情景展望"章节+5个字段 |
| 4 | §3.7 解析规范 | Invoke-DailyReportParser.ps1 | 运行脚本→验证JSON schema+正则提取完整性 |
| 5 | §3.7.4 质量标记 | 解析脚本输出[OK]/[C]/[INFER]/[MISS]/[CALC] | 检查JSON中每个字段含quality标记 |

---

> **情墨签**: 设计完成，闸门1a待腰子确认。三任务均为增量改动，不修改现有数据接口，L0/L1分级合理。
