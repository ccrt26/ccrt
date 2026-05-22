# 模拟交易系统 变更日志

> 独立于白皮书的变更记录，遵循 CLAUDE.md §2.4 真实性规则。
> 每条记录附带证据链（文件路径+行号+改动摘要）。

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
