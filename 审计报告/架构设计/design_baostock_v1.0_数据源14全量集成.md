# 架构设计 — baostock数据源[14]全量集成

> pipeline_stage: ① complete | finance_confirmed: true | 情墨 v1.0 | 腰子确认 2026-05-26
> 代码等级: L0（数据/工具模块）
> 白皮书依据: 规则红线v1.16 §1.1(1+2主备) §1.2(数据源编号)

---

## 一、需求概述

集成 baostock Python库作为新数据源[14]，填补3个当前数据空白，并增强现有数据的备源深度。

### 集成范围（4个Phase，一次性全量）

| Phase | 数据类型 | 当前状态 | 集成后 |
|:-----:|:--------|:--------|:------|
| 1 | 分红除权+复权因子 | 无源 | [14]主源→[C]缓存 |
| 2 | 宏观经济(5接口) | 山猫手工 | [14]主源→[C]缓存 |
| 3 | 业绩预告+业绩快报 | 无源 | [14]主源→[C]缓存 |
| 4 | K线/财务备源增强 | 已有主备 | 插入降级链做第三备源 |

---

## 二、模块设计

### 2.1 新增文件

```
代码文件/每日荐股/scripts/stock_data_fetcher_baostock.py  (~250行, L0)
代码文件/数据/schema_baostock_dividend.json               (分红数据结构)
代码文件/数据/schema_baostock_macro.json                   (宏观数据结构)
代码文件/数据/schema_baostock_forecast.json                (业绩预告结构)
```

### 2.2 修改文件

| 文件 | 改动 | 行数 |
|:-----|:----|:---:|
| `代码文件/每日荐股/scripts/modules/core.ps1` | SourcePriority新增Dividend/Macro/Forecast三类；CacheTTL新增对应TTL；SourceUsed注册 | ~15行 |
| `.claude/agents/玉夜-知识库/01-数据源全景.md` | 新增§[14] baostock详细规格 | ~60行 |
| `.claude/agents/玉夜-知识库/08-数据源故障历史.md` | 新增[14]风险记录行 | ~5行 |
| `.claude/agents/玉夜-知识库/05-异常检测与告警.md` | 新增P级事件：baostock会话超时/数据缺失 | ~10行 |

### 2.3 不修改的文件

- 评分引擎、回测引擎、报告生成：不涉及
- 模拟交易逻辑：不涉及
- 现有fetcher脚本（THS/必盈/知途等）：各自独立，无耦合

---

## 三、接口契约

### 3.1 Python→PowerShell 桥接协议

沿用 `stock_data_fetcher_ths.py` 的成熟模式：

```
调用: python stock_data_fetcher_baostock.py <action> [--param value ...]
输出: JSON → stdout (UTF-8)
退出码: 0=成功, 1=失败
```

**契约要点**：
- 所有输出通过 `sys.stdout.buffer.write(utf8_bytes)` 确保Windows编码兼容
- NaN/NaT → `null`（与THS桥接一致）
- 空结果返回 `{"error": "no data", "source": "baostock[14]"}`

### 3.2 支持的操作（action）

| action | 对应Phase | 参数 | 返回格式 |
|:-------|:--------:|:-----|:--------|
| `dividend` | 1 | `--code sh.600519 --start 2020-01-01` | 除权除息记录数组 |
| `adjust_factor` | 1 | `--code sh.600519 --start 2020-01-01` | 复权因子数组 |
| `macro_deposit_rate` | 2 | `--start 2020-01-01` | 存款利率时间序列 |
| `macro_loan_rate` | 2 | `--start 2020-01-01` | 贷款利率时间序列 |
| `macro_rrr` | 2 | `--start 2020-01-01` | 准备金率时间序列 |
| `macro_money_supply` | 2 | `--freq month` | 货币供应量 |
| `macro_shibor` | 2 | `--year 2026` | SHIBOR数据 |
| `forecast` | 3 | `--code sh.600519 --quarter 2026q2` | 业绩预告 |
| `express` | 3 | `--code sh.600519 --quarter 2026q1` | 业绩快报 |
| `kline` | 4 | `--code sh.600519 --freq d --start 2020-01-01 --adjust 2` | K线(日/周/月/分钟) |
| `financial_profit` | 4 | `--code sh.600519 --year 2025 --quarter 4` | 季频盈利 |
| `financial_growth` | 4 | `--code sh.600519 --year 2025 --quarter 4` | 季频成长 |
| `financial_balance` | 4 | `--code sh.600519 --year 2025 --quarter 4` | 季频偿债 |
| `financial_cashflow` | 4 | `--code sh.600519 --year 2025 --quarter 4` | 季频现金流 |
| `financial_dupont` | 4 | `--code sh.600519 --year 2025 --quarter 4` | 杜邦分析 |
| `stock_basic` | 4 | `--code sh.600519` | 股票基本信息 |
| `trade_dates` | — | `--start 2026-01-01 --end 2026-12-31` | 交易日历 |

### 3.3 会话管理契约

```python
# baostock 必须显式login/logout，30min无操作自动过期
# 封装策略：
#   单次action: login → query → logout（每次独立会话）
#   批量action: login → query1...queryN → logout（复用会话，<30min）
#   超时恢复: 捕获超时异常 → 重新login → 重试query（最多1次）
```

### 3.4 限速契约

- baostock未认证: ~60次/分钟
- 本项目实际: 间隔≥0.5s（比腾讯的0.3s更保守，因为非线程安全必须串行）
- 单次查询上限: ~1000条记录（批量查询时需分页）

---

## 四、数据流设计

### 4.1 Phase 1: 分红除权数据流

```
PowerShell: Invoke-DataSource -Category "Dividend" -PrimaryCall {...}
  ↓
Python: stock_data_fetcher_baostock.py dividend --code sh.600519
  ↓
baostock: bs.login() → query_dividend_data() → bs.logout()
  ↓
返回: [{"date":"2025-06-15","type":"分红","cash_div":12.5,...}, ...]
  ↓
PowerShell: Save-DataCache → 缓存到 data_cache/Dividend_sh.600519.json
```

### 4.2 Phase 2: 宏观经济数据流

```
山猫调用 / 每日调度触发
  ↓
PowerShell: Invoke-DataSource -Category "Macro" -PrimaryCall {...}
  ↓
Python: stock_data_fetcher_baostock.py macro_money_supply --freq month
  ↓
baostock: query_money_supply_data_month()
  ↓
缓存到 data_cache/Macro_money_supply_month.json
```

### 4.3 Phase 3: 业绩预告/快报数据流

```
腰子深度分析触发
  ↓
PowerShell: Invoke-DataSource -Category "Forecast" -PrimaryCall {...}
  ↓
Python: stock_data_fetcher_baostock.py forecast --code sh.600519 --quarter 2026q2
  ↓
baostock: query_forcast_report()
  ↓
返回业绩预告 → 腰子综合研判
```

### 4.4 Phase 4: K线/财务备源增强（插入现有降级链）

现有降级链更新：
```
KLine:     新浪[2] → 腾讯[B] → 必盈[13] → baostock[14] → 缓存[C]
Financial: 东方财富[3] → 同花顺[THS] → 必盈[13] → baostock[14] → 缓存[C]
```

---

## 五、降级路径与1+2架构合规

### 5.1 新增数据类的降级路径

| 数据类 | Category | 主源 | 备源 | 缓存 | 独有源风险 |
|:------|:--------|:----:|:----:|:---:|:--------:|
| 分红除权 | Dividend | [14]baostock | — | [C] | ⚠️ 独有源，标注"仅供参考" |
| 复权因子 | AdjustFactor | [14]baostock | — | [C] | ⚠️ 独有源 |
| 宏观经济 | Macro | [14]baostock | — | [C] | ⚠️ 独有源 |
| 业绩预告 | Forecast | [14]baostock | — | [C] | ⚠️ 独有源 |
| 业绩快报 | Express | [14]baostock | — | [C] | ⚠️ 独有源 |

> ⚠️ 独有源处理：遵循红线规则，Phase 1-3新增字段均为全新数据域，baostock是唯一已知免费源。在报告中强制标注"仅供参考"，并在数据源故障历史中标记高风险。后续寻找备源（如Tushare免费额度、akshare对应接口）降低单点风险。

### 5.2 合规措施

1. **缓存TTL设定**：分红/宏观数据变化慢 → 168h(7天)；预告/快报 → 24h(日频更新)
2. **缓存过期兜底**：缓存过期后，过期数据仍可用（标记`[C-EXP]`），但强制触发告警P3
3. **独有源声明**：所有Phase 1-3数据在报告中标注"数据源[14]baostock，无备源，仅供参考"

---

## 六、数据准确性保障

### 6.1 字段校验规则（ValidateBlock）

| 数据类 | 校验规则 | 失败动作 |
|:------|:--------|:--------|
| 分红除权 | cash_div >=0; 除权日期非未来; 至少1条记录 | 标记P3，使用缓存 |
| 宏观经济 | M2>=M1>=M0; 利率在0-20%范围内 | 标记P3异常值 |
| 业绩预告 | 净利润增长率在-500%~+500%范围内 | 标记P3，人工复核 |
| K线 | OHLC四价全>0; high>=low; volume>=0 | 标准K线校验 |
| 财务 | ROE在-100%~+100%范围内 | 标记异常，不使用该字段 |

### 6.2 跨源交叉验证（存量数据）

- K线OHLC：baostock vs 新浪[2] → 差异>0.5%标记P3
- 财务EPS：baostock vs 东方财富[3] → 差异>5%标记P3
- 分红记录：baostock vs 手工台账(如有) → 差异标记P3

---

## 七、玉夜巡检集成

### 7.1 新增巡检项

在玉夜现有的盘前全量巡检框架中增加：

**API连通性**：
```
[14] baostock API → Python import baostock → bs.login() 成功/失败
```

**数据新鲜度检查**（盘前8:00）：
```
- 分红除权缓存: 最后更新时间 < 7天
- 宏观数据缓存: 最后更新时间 < 7天（月度数据）或 < 30天（年度数据）
- 业绩预告缓存: 最后更新时间 < 24h（财报季）或 < 7天（非财报季）
```

**1+2架构合规**：
```
- [14]作为主源: Phase 1-3新增5类数据 → 独有源标记
- [14]作为备源: Phase 4增强K线/财务 → 插入降级链后确认路径有效
```

### 7.2 新增P级异常事件

| 事件 | 等级 | 触发条件 |
|:-----|:---:|:--------|
| baostock会话超时 | P4 | 30min无操作session过期（预期内） |
| baostock库不可用 | P2 | `import baostock`失败 |
| 分红数据缺失 | P2 | 某股票分红记录为空（可能是停牌/新股） |
| 宏观数据延迟 | P3 | 月度数据超30天未更新 |
| 跨源K线差异 | P3 | baostock与新浪K线差异>0.5% |

### 7.3 知识库更新清单

```
1. 01-数据源全景.md  — 新增§[14] baostock完整规格（16个action/端点/字段/限制）
2. 05-异常检测与告警.md — 新增§baostock专项P2-P4事件
3. 08-数据源故障历史.md — 新增[14]风险记录行（高风险-独有源）
```

---

## 八、缓存策略

| 数据类 | CacheKey格式 | TTL | 说明 |
|:------|:-----------|:---:|:-----|
| 分红除权 | `Dividend_{code}` | 168h | 历史数据不常变 |
| 复权因子 | `AdjustFactor_{code}` | 168h | 同上 |
| 存款利率 | `Macro_deposit_rate` | 168h | 宏观政策低频 |
| 贷款利率 | `Macro_loan_rate` | 168h | 同上 |
| 准备金率 | `Macro_rrr` | 720h | 极少调整 |
| 货币供应(月) | `Macro_money_supply_month` | 720h | 月度发布 |
| 货币供应(年) | `Macro_money_supply_year` | 720h | 年度数据 |
| SHIBOR | `Macro_shibor_{year}` | 24h | 日频更新 |
| 业绩预告 | `Forecast_{code}` | 24h | 财报季高频 |
| 业绩快报 | `Express_{code}_Q{1-4}` | 72h | 快报发布后基本不变 |
| K线(日) | `KLine_baostock_{code}` | 24h | 日频 |
| 财务 | `Financial_baostock_{code}_Y{year}Q{quarter}` | 168h | 季度不变 |

---

## 九、技术约束与风险

### 9.1 防劣化约束

| 约束 | 措施 |
|:-----|:-----|
| 非线程安全 | 脚本内全部串行调用，不引入多线程/多进程（单次查询量小） |
| 30min超时 | 每次action独立login/logout，不依赖长会话 |
| pandas 2.0+ | 使用`pd.concat()`替代`.append()` |
| 单次1000条限制 | K线>1000条时分批查询，按年份切片 |
| 无实时数据 | 不参与盘中实时链路，仅盘后/按需调用 |

### 9.2 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:---:|:---:|:-----|
| baostock服务中断 | 低 | 中 | Phase 1-3数据降级到缓存[C]，标注过期 |
| baostock API变更 | 中 | 低 | 版本锁定在requirements.txt，升级前测试 |
| 数据质量偏差 | 中 | 中 | ValidateBlock校验+跨源交叉验证 |
| 独有源单点故障 | 中 | 中 | 缓存延长TTL兜底；后续找备源 |

---

## 十、需求→代码核对清单

> 情墨+腰子共同勾签后放行

| # | 需求项 | 设计覆盖 | 情墨勾 | 腰子勾 |
|:--|:------|:-------|:----:|:----:|
| 1 | 分红除权数据接入 | §三 dividend/adjust_factor | ☐ | ☐ |
| 2 | 宏观经济数据接入(5接口) | §三 macro_* | ☐ | ☐ |
| 3 | 业绩预告/快报接入 | §三 forecast/express | ☐ | ☐ |
| 4 | K线/财务备源增强 | §三 kline/financial_* | ☐ | ☐ |
| 5 | 1+2架构合规(降级路径) | §五 | ☐ | ☐ |
| 6 | 数据字段校验 | §六 ValidateBlock | ☐ | ☐ |
| 7 | 玉夜巡检集成 | §七 新增巡检项+P级事件+知识库更新 | ☐ | ☐ |
| 8 | 缓存策略 | §八 TTL配置 | ☐ | ☐ |
| 9 | 独有源标注 | §五 "仅供参考"声明 | ☐ | ☐ |
| 10 | Python脚本单文件≤500行 | §九 预估~250行 | ☐ | ☐ |
| 11 | 代码等级L0 | §一 L0标注 | ☐ | ☐ |

---

> **pipeline_stage: complete** | 下一站: 腰子 → 闸门1a确认（全团咨询: 山猫→玉夜→流金→青山）
