# 日报Recent4Days历史换手率修复

> 情墨 | 阶段① 设计交付物 | 2026-05-27
> pipeline_stage: complete
> 代码等级: L0 (工具/数据层)
> finance_confirmed: true
> 关联: design_daily_report_1_2_data_fix.md（Recent4Days原始设计）

---

## 一、根因

| # | 空洞 | 根因 | 数据是否存在 |
|:--|:-----|:-----|:----:|
| H1 | Recent4Days历史三天换手率全部为null | `batch_data_collector.ps1:612` 硬编码 `TurnoverRate = $null`，因为新浪K线API[2]不含换手率字段 | ✅ 东方财富[3]K线API有 |

**验证**：东方财富K线API（`push2his.eastmoney.com`）返回11字段，第11字段=换手率。实测600114：`2026-05-27,...,4.82`（换手率=4.82%）。

---

## 二、修复方案

### 2.1 变更范围

| 文件 | 等级 | 变更 | 预估行数 |
|:-----|:----:|:-----|:----:|
| `代码文件/每日荐股/scripts/batch_data_collector.py` | L0 | Recent4Days构造段：增加东方财富K线调用获取历史换手率，按日期匹配填入 | +20行 |

### 2.2 实现方案

在 `Recent4Days` 构造之前，调用东方财富K线API获取近5日数据（含换手率），构建日期→换手率的映射表。

```powershell
# 在 Recent4Days 构造之前（~line 597）增加：
# 东方财富K线 → 日期→换手率映射（新浪K线不含换手率，东方财富含）
$turnoverMap = @{}
try {
    $emUrl = "http://push2his.eastmoney.com/api/qt/stock/kline/get?secid=$($emSecID)$s.Code&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&end=20500101&lmt=5"
    # $emSecID: 1=沪, 0=深 — 已在脚本前面计算
    $emResp = Invoke-WebRequest -Uri $emUrl -UseBasicParsing -TimeoutSec 5
    $emJson = $emResp.Content | ConvertFrom-Json
    if ($emJson.data -and $emJson.data.klines) {
        foreach ($kl in $emJson.data.klines) {
            $parts = $kl -split ','
            # parts[0]=日期, parts[10]=换手率
            if ($parts.Count -ge 11 -and $parts[10]) {
                $turnoverMap[$parts[0]] = [double]$parts[10]
            }
        }
    }
} catch { }
```

然后修改 Recent4Days 循环中的 TurnoverRate 赋值：

```powershell
# 将 line 612:
#     TurnoverRate = $null
# 改为:
#     TurnoverRate = if ($turnoverMap.ContainsKey($k.KDate[$i])) { $turnoverMap[$k.KDate[$i]] } else { $null }
```

### 2.3 降级路径

```
东方财富K线(主) → 失败时TurnoverMap为空 → TurnoverRate回退为$null（旧行为）
```

---

## 三、影响评估

| 维度 | 评估 |
|:-----|:-----|
| **下游消费者** | scoring_engine_v2.py 忽略未知字段，不受影响 |
| **data_final.json** | 字段透传，不受影响 |
| **日报模板** | 无需变更（模板已删除数据源说明行） |
| **向后兼容** | null→数值，旧消费者忽略 |
| **API调用增量** | 每只股票+1次东方财富K线调用（已有限速机制兜底） |
| **换手率可用性** | 东方财富正常时全部4天有值；降级时回退为null |
| **风险** | 极低。新增调用复用已有API模式，失败静默降级 |

---

## 四、需求→代码核对清单

| # | 需求 | 验证方式 |
|:--|:-----|:-----|
| 1 | Recent4Days历史日换手率非null | `jq '.[].Recent4Days[0].TurnoverRate' data_full.json` — 重点股有值 |
| 2 | Recent4Days近4日换手率全部非null | `jq '.[].Recent4Days | [.[].TurnoverRate]' data_full.json` |
| 3 | 东方财富失败时回退null | 断网测试：TurnoverRate=null，脚本不崩溃 |
| 4 | 现有字段不受影响 | scoring_engine_v2.py 正常运行 |
| 5 | 8只重点股票4日换手率完整 | 核查段输出全部OK |

---

> 情墨+腰子勾签放行后 → 流入阶段③ 新安+旧影审查
