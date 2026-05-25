# 数据获取健康检测机制 — 架构设计

> 情墨 | 2026-05-25 | L1级
> pipeline_stage: complete
> finance_confirmed: true (腰子确认：T0/T1/T2分级表+三级响应矩阵已审核通过)
> gate_1a: PASS | gate_1b: PASS (新安+旧影独立审查通过)
> 触发背景：5月25日数据管线多次QC失败+回填全链断裂，用户要求设计主动检测机制

---

## 一、问题诊断

经阿黑调查+腰子全团评审，确认以下缺陷：

| ID | 严重度 | 文件 | 问题 |
|:---|:------|:-----|:-----|
| B1 | P0 | `backfill_returns.py:28` | ROOT=PowerShell代码字符串，不是实际路径，回填全链失效 |
| B2 | P1 | `check_data_quality.ps1:99` | 查找`$data.Recommendations`但data_full.json字段名为`Stocks` |
| B3 | P1 | `daily_workflow.ps1` | 无最大重试/熔断机制，5月25日重试7+次不停止 |
| B4 | P2 | 缺失 | 无开机主动检测，用户无法感知数据健康状态 |
| B5 | P2 | 缺失 | 无T0/T1/T2数据字段分级，所有缺失统一处理 |

---

## 二、设计方案

### 2.1 整体架构

```
开机(不定时)
  │
  ▼
invoke_daily.ps1 (幂等守卫，已有)
  │
  ├─ Step 0 (新增): health_check.ps1  ← 开机健康检测
  │     ├─ API连通性(主+备)
  │     ├─ 数据文件新鲜度
  │     ├─ 关键字段完整性(T0/T1/T2)
  │     ├─ 回填覆盖率
  │     └─ 输出: JSON + HTML报告
  │
  ├─ L3阻断? → 停止，弹HTML告警，exit 1
  └─ L1/L2/正常 → 继续
       │
       ▼
  daily_workflow.ps1 (现有管线)
       │
       ├─ QC-1 (修复后): check_data_quality.ps1
       ├─ 评分 → QC-2
       ├─ backfill_returns.py (修复后)
       └─ 报告/归档/模拟交易
```

### 2.2 数据字段T0/T1/T2分级（腰子终版）

| 级别 | 定义 | 字段 | 缺失动作 |
|:----:|:-----|:-----|:-----|
| **T0 阻断** | 评分/排序/否决/后评估的根 | Price, KLine, EPS_TTM, TotalScore, VetoStatus, 回填覆盖率<50% | **L3阻断** |
| **T1 降级** | 辅助因子，可走缓存 | FundFlow, Northbound, Margin, SectorKLine | **L1标记**[C] |
| **T2 可选** | 非核心信号 | PB, PS, PEG, 一致预期, 研报数 | **静默跳过** |

### 2.3 告警三级响应

| 级别 | 触发条件 | 行为 |
|:----:|:-----|:-----|
| **L1 降级** | 主源挂+备源OK，或个别T1字段降级 | 终端黄色输出，日志记录，流水线继续 |
| **L2 缓存** | 主备双源全挂，走缓存 | 终端黄色+弹HTML简报，流水线继续(标注[C]) |
| **L3 阻断** | T0字段缺失/双源+缓存全挂/数据文件损坏 | 终端红色+弹HTML告警+**停止所有下游流水线**+模拟交易强制停止 |

### 2.4 新增文件（2个）

| 文件 | 行数 | 等级 | 用途 |
|:-----|:---:|:---:|:-----|
| `代码文件/tools/health_check.ps1` | ~180 | **L1** | 健康检测主脚本（开机+流水线前置共用） |
| `代码文件/tools/health_report_template.html` | ~60 | L0 | HTML告警报告模板 |

### 2.5 修改文件（4个）

| 文件 | 等级 | 改动 |
|:-----|:---:|:-----|
| `代码文件/每日荐股/scripts/backfill_returns.py` | **L0** | 第28行ROOT路径修复：`os.path.dirname(__file__)`×3 |
| `代码文件/tools/check_data_quality.ps1` | **L1** | ①第99行兼容`Stocks`/`Recommendations`双字段名 ②加入T0/T1/T2分级检查逻辑 |
| `代码文件/每日荐股/scripts/daily_workflow.ps1` | **L1** | ①Step 0新增health_check前置调用 ②QC失败时最大重试3次+熔断 |
| `代码文件/每日荐股/scripts/invoke_daily.ps1` | L1 | 幂等检查前先调health_check（开机即检测） |

---

## 三、接口契约

### 3.1 health_check.ps1

```
输入参数:
  -Mode        daily_sim | key_stock | eval | boot (开机模式)
  -DataFile    待检数据文件路径 (可选，boot模式不需要)
  -RootDir     项目根目录 (可选，自动检测)
  -OutputHtml  输出HTML报告路径 (可选，L2/L3时默认生成到临时报告/)

输出 (stdout JSON):
{
  "checked_at": "2026-05-25T09:00:00",
  "flag": "normal" | "degraded" | "cached" | "blocked",
  "alert_level": "L0" | "L1" | "L2" | "L3",
  "passed": true | false,
  "t0_status": { "Price": "ok", "KLine": "ok", "EPS_TTM": "degraded", ... },
  "t1_status": { "FundFlow": "cached", ... },
  "t2_status": { "PB": "missing", ... },
  "backfill_coverage": 0.85,
  "api_latency_ms": 230,
  "messages": ["腾讯API正常(230ms)", "新浪备源可用", ...],
  "html_report_path": "临时报告/health_report_20260525.html"
}

退出码: 0=正常/L1/L2 | 1=L3阻断
```

### 3.2 daily_workflow.ps1 熔断逻辑

```
$maxRetries = 3
$retryCount = 0
while ($retryCount -lt $maxRetries) {
    # QC-1 检查
    if (QC-1 PASS) { break }
    $retryCount++
    if ($retryCount -ge $maxRetries) {
        Write-Log "QC-1 failed after $maxRetries retries, ABORTING" -Level "ERROR"
        # 生成告警HTML
        & $healthCheckScript -Mode daily_sim -DataFile $dataFullPath -OutputHtml $alertHtml
        exit 1
    }
    Write-Log "QC-1 retry $retryCount/$maxRetries" -Level "WARN"
    Start-Sleep -Seconds 30
    # 重新采集数据...
}
```

---

## 四、数据流

```
health_check.ps1
  ├─ API检测: 腾讯行情[1] → 失败→ 新浪行情[2] → 双挂→ 标记cached
  ├─ 文件检测: data_full.json/score_history.jsonl 存在+新鲜度+可解析
  ├─ 字段检测: 读取data_full.json → 按T0/T1/T2分级统计缺失率
  └─ 回填检测: score_history.jsonl → 统计ret_t1非null比例 → <50%=T0阻断

输出:
  ├─ stdout JSON → 调用方解析(如daily_workflow判断是否继续)
  ├─ HTML报告 → 临时报告/health_report_{date}.html (L2/L3时)
  └─ 终端彩色输出 ─ 用户可见
```

---

## 五、代码分级

| 模块 | 等级 | 审核路径 | 理由 |
|:-----|:---:|:--------|:-----|
| health_check.ps1 | **L1** | 情墨复审+新安全量 | 涉及数据质量判定策略，影响评分输入 |
| health_report_template.html | L0 | 红结自查+新安常规 | 纯展示层 |
| backfill_returns.py (修复) | L0 | 红结自查+新安常规 | 单行路径修复 |
| check_data_quality.ps1 (修复) | L1 | 情墨复审+新安全量 | 涉及质检逻辑变更 |
| daily_workflow.ps1 (修复) | L1 | 情墨复审+新安全量 | 流程控制变更(熔断) |
| invoke_daily.ps1 (修复) | L1 | 情墨复审+新安全量 | 流程控制变更(前置检测) |

---

## 六、风险与缓解

| 风险 | 缓解 |
|:-----|:-----|
| 开机检测耗时过长 | 所有API超时设3s，整体控制在30s内 |
| L3阻断误报(网络波动) | 双源均尝试+3秒超时，挂了才是真的挂 |
| HTML报告堆积 | 保留最近7天，health_check内部自动清理 |
| 回填修复后仍需历史K线 | 首次修复后运行`--catch-up`模式补全所有历史null |

---

## 七、需求→代码核对清单

| 编号 | 检查项 | 条款 | 情墨勾 | 腰子勾 |
|:----:|:------|:-----|:-----:|:-----:|
| R1 | backfill_returns.py ROOT路径修复 | Bug #1 | ☐ | ☐ |
| R2 | check_data_quality.ps1兼容Stocks/Recommendations | Bug #2 | ☐ | ☐ |
| R3 | health_check.ps1 T0/T1/T2三级字段检查 | 腰子分级表 | ☐ | ☐ |
| R4 | L1/L2/L3三级告警响应逻辑 | 腰子响应矩阵 | ☐ | ☐ |
| R5 | daily_workflow.ps1 熔断(max 3 retries) | Bug #3 | ☐ | ☐ |
| R6 | invoke_daily.ps1 开机即调health_check | 开机检测 | ☐ | ☐ |
| R7 | 数据源1+2架构完整(API检测主+备) | 红线§1.2 | ☐ | ☐ |
| R8 | L3阻断时模拟交易强制停止 | 流金硬约束 | ☐ | ☐ |
| R9 | HTML报告L2/L3生成+7天自动清理 | 告警展示 | ☐ | ☐ |
| R10 | 单文件≤500行(health_check.ps1目标~180行) | 红线§9.2 | ☐ | ☐ |
