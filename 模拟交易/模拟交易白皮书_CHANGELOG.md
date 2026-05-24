# 模拟交易系统 变更日志

> 独立于白皮书的变更记录，遵循 CLAUDE.md §2.4 真实性规则。
> 每条记录附带证据链（文件路径+行号+改动摘要）。

## v1.7 (2026-05-24)

> v1.5-v1.6 版本合并 + 8项新功能 + 8个引擎Bug修复
> 白皮书: 模拟交易白皮书_v1.5.md + 模拟交易白皮书_v1.6.md → 合并为 模拟交易白皮书_v1.7.md

### Added
- **§十 v1.7 新增功能**: 大盘熔断/共享冷却期/数据质量降级/板块相位持仓/行业集中度/周度反馈/月度校准/Task Scheduler(§10.1-10.9)（模拟交易白皮书_v1.7.md §十）
- **§2.5.2 P1止损**: 新增每日荐股赛道 ATR 动态止损说明（模拟交易白皮书_v1.7.md L167-185）
- **附录A**: 更新目录结构，新增 v1.5-v1.7 版本文件、共享模块、每日荐股赛道（模拟交易白皮书_v1.7.md 附录A）

### Fixed (引擎层面，8个Bug)
- **P0-1**: sim_trading.ps1 未加载 risk_framework.ps1 → 补充 dot-source（sim_trading.ps1）
- **P0-2**: sim_trading_daily.ps1 `$blackSwanTriggered` 未初始化 → 初始化变量（sim_trading_daily.ps1）
- **P1-3**: sim_trading_daily.ps1 "退潮期"→"衰退期" 术语对齐（sim_trading_daily.ps1）
- **P1-4**: sim_trading_daily.ps1 "主升"→"高潮期" 相位排序修正（sim_trading_daily.ps1）
- **P1-5**: risk_framework.ps1 EntrySector→EntryIndustry fallback（risk_framework.ps1 Get-SectorPhaseAlerts）
- **P1-6**: risk_framework.ps1 置信度比较逻辑修复（risk_framework.ps1 Get-SectorPhaseAlerts）
- **P2-7**: sim_trading_daily.ps1 sectorConf硬编码50→SectorTrendMap管道（sim_trading_daily.ps1）
- **P2-8**: quote_engine.ps1 + sim_trading.ps1 Get-BenchmarkValue 缺失ChangePct/Turnover（quote_engine.ps1, sim_trading.ps1）

### 文件信息
- 白皮书: `模拟交易/模拟交易白皮书_v1.7.md`
- 引擎: `模拟交易/交易引擎/sim_trading.ps1`, `模拟交易/每日荐股赛道/交易引擎/sim_trading_daily.ps1`
- 共享模块: `模拟交易/共享模块/risk_framework.ps1`, `模拟交易/共享模块/quote_engine.ps1`
- 旧版存档: v1.5.md, v1.6.md

## v1.6 (2026-05-23)

> 豆包建议「风险-黑天鹅」落地：新增组合级别单日回撤保护机制。

### Added
- **§2.8 组合级别风控—黑天鹅单日回撤保护**: 单日回撤>3%黄色预警暂停开仓，>5%红色减仓自动卖出全部持仓50%+暂停开仓3日（模拟交易白皮书_v1.5.md 原L1063后插入）
- **§2.5.1 出场优先级表**: 新增P0黑天鹅减仓行，位于P2和P3之间（模拟交易白皮书_v1.5.md L155-162）
- **§3.1 每日运行流程**: 步骤6.5新增黑天鹅减仓检查，步骤7更新优先级顺序（模拟交易白皮书_v1.5.md L273-280）
- **§4.4 自动预警条件**: 新增单日回撤>5%红旗+>3%黄旗两行（模拟交易白皮书_v1.5.md L561-566）

### 文件信息
- 白皮书: `模拟交易/模拟交易白皮书_v1.5.md`（内容已升级至v1.6，待更名）
- 引擎: `模拟交易/交易引擎/sim_trading.ps1`（待实现P0检查逻辑）

## v1.5 (2026-05-23)

> 青山策略审查发现3个P0硬伤，阿黑修复。引擎行为修正，白皮书规格未变。

### 修复

- **P0-1 绩效归因含费用**: FIFO配对盈亏计算改用 `TotalCost`（含佣金+印花税），此前用 `Amount`（裸成交额）系统性高估收益约0.15%/笔（sim_trading.ps1 L996/L999/L1004, `$t.Amount`→`$t.TotalCost`）
- **P0-2 09:45超时阻断生效**: `$skipOpenNewPositions` 标志原仅写日志未实际阻断，Step 9 整体包裹进 `if (-not $skipOpenNewPositions) { ... }` else块（sim_trading.ps1 L651-818）
- **P0-3 冷却期持久化**: 止损/止盈冷却标记原存于持仓对象，清仓后随 `positions.json` 丢弃次日失效。新增独立 `Cooldowns` 字典持久化，出场时同步写入，开仓时从 Cooldowns 回退读取（sim_trading.ps1 L383-396 加载, L640-648 写入, L680-697 检查, L873 保存）

### 文件信息
- 引擎: `模拟交易/交易引擎/sim_trading.ps1`
- 白皮书: `模拟交易/模拟交易白皮书_v1.5.md`
- 持仓结构: `positions.json` 新增 `Cooldowns` 字段

## v1.4 (2026-05-23)

> 版本号同步：白皮书v1.4、引擎v1.4、文件名统一。
> v1.4 的实质变更内容与 v1.3 相同（见下），仅修正版本号不一致。

### 修复

- **文件名与版本号同步**: 白皮书文件名 v1.3.md→v1.4.md，引擎头部 v1.3→v1.4（模拟交易白皮书_v1.3.md rename→v1.4.md, sim_trading.ps1 L3）
- **CHANGELOG 补齐 v1.4**: 本记录（CHANGELOG.md L6-L19）
- **附录A目录树更新**: 移除不存在的 v1.0 引用，v1.3 改为旧版存档，新增 v1.4 当前版本（白皮书附录A）

## v1.3 (2026-05-23)

> 对应代码文件：`模拟交易/交易引擎/sim_trading.ps1`（1045行）

### 新增

- **1+2数据源架构**: Get-QuoteMap新增新浪行情API备源 + 缓存文件兜底（sim_trading.ps1 L98-140, Get-QuoteMap函数）
- **节假日检测**: Step 0增加2026年法定节假日列表，非交易日静默跳过（sim_trading.ps1 L347-355）
- **09:45超时逻辑**: 超过09:45设置$skipOpenNewPositions标志，仅执行止损（sim_trading.ps1 L370-372, Step 9检查处L585）
- **Get-SellProceeds**: 提取P1-P5重复卖单计算为公共函数，减少约40行重复代码（sim_trading.ps1 L254-260）
- **写入后验证**: Assert-WriteSuccess函数，所有Set-Content后验证文件写入成功（sim_trading.ps1 L57-60, 调用处L799/L832/L895/L1011）
- **数据来源标记**: transactions.csv增加data_source列，标注"腾讯行情[1]"（sim_trading.ps1 L787/803）
- **监督机制集成**: 纳入version_supervisor版本监督、CLAUDE.md任务监督表、文档版本索引

### 修复

- **BUG-004**: Get-CoolingDays自然日($d1-$d2).Days→交易日Get-TradingDaysBetween辅助函数（sim_trading.ps1 L272-285, 原L185）
- **BUG-007**: 补齐数据质量检查KeyLevels完整性/Support<Price×1.5/Resistance>Price×0.5三项（sim_trading.ps1 L428-436, Step 4）
- **BUG-008**: ConvertFrom-Json全部包裹try/catch，文件损坏时有意义报错而非崩溃（sim_trading.ps1 L80/116/161/196多处）
- **BUG-003**: Get-R2R3 ATR分支加throw "not implemented"（sim_trading.ps1 L237）
- **BUG-005**: 置信度映射`-or 0`改为`ContainsKey`显式检查（sim_trading.ps1 L692）
- **BUG-006**: Calc-StampTax增加$IsSell参数，OnSellOnly逻辑移到调用方（sim_trading.ps1 L258, Calc-StampTax函数L264-268）

### 变更

- 版本号从v1.0更新至v1.3，与白皮书同步（sim_trading.ps1 L3/L269）
- Get-QuoteMap重写: 主源腾讯qt.gtimg.cn→备源新浪hq.sinajs.cn→本地缓存兜底三级降级，日志输出[1]/[1B]/[C]标记（sim_trading.ps1 L67-148）
- P1-P5退出逻辑重构: 统一调用Get-SellProceeds，消除5份重复计算代码（sim_trading.ps1 L457-576）

---

## 更早版本

更早版本的变更记录见 [模拟交易白皮书_v1.3.md §1.3 版本历史](模拟交易白皮书_v1.3.md)。
