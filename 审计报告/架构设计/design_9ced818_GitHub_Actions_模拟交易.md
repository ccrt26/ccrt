# 架构设计: GitHub Actions模拟交易自动运行 + 引擎-Force参数
> 设计人: 情墨 | 日期: 2026-05-25 (事后补) | 对应 commit: `9ced818`

## 一、模块划分

### 1.1 GitHub Actions Workflow
- 文件: `.github/workflows/sim_trading.yml`
- 触发: cron `35 09 * * 1-5` (交易日09:35) + workflow_dispatch (手动)
- 两个赛道: `sim_trading.ps1` (主线) + `sim_trading_daily.ps1` (日频)

### 1.2 引擎-Force参数
- 两个引擎各加 `-Force` switch参数
- 默认 `$false`，向后兼容
- 用途: 绕过09:45时间门禁，workflow_dispatch手动回填时使用

## 二、接口契约

| 模块 | 输入 | 输出 | 消费者 |
|:-----|:-----|:-----|:-----|
| sim_trading.yml | cron触发 / workflow_dispatch | 调用两个ps1 | GitHub Actions runner |
| sim_trading.ps1 | -Force (可选) | 模拟交易执行 | 交易日志 |
| sim_trading_daily.ps1 | -Force (可选) | 日频模拟交易 | 交易日志 |

## 三、数据流
```
cron 09:35 → sim_trading.yml
  ├─ sim_trading.ps1 -Force    (workflow级默认-Force)
  └─ sim_trading_daily.ps1 -Force
       ↓
  引擎时间门禁 → -Force=$true → 跳过门禁 → 执行交易
```

## 四、风险点
- Force参数绕过时间门禁——仅限GitHub Actions环境使用，本地手动需确认
- cron时区为UTC，`35 09 * * 1-5` = UTC 09:35 = 北京时间 17:35 (可能不是盘前)
  - ⚠️ 实际触发时间为北京时间17:35，非盘前09:35。此问题需腰子确认交易时间窗口

## 五、需求→代码核对清单
- [x] GitHub Actions cron 工作日自动触发 → sim_trading.yml
- [x] workflow_dispatch 手动触发 → sim_trading.yml
- [x] 引擎-Force参数 → engine.ps1 (两个赛道)
- [x] 向后兼容 ($false默认) → engine.ps1

> 情墨签字: 情墨 ✅ | 腰子确认: cron时区问题需确认 ⚠️
