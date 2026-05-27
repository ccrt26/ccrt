# 重点股票报告命名统一 — 架构设计 v1.0

> **情墨产出** | pipeline_stage: complete | finance_confirmed: true | 2026-05-27T21:30
> 代码等级: **L1** (策略/评分管线 — 报告命名)

## 一、问题定义

分析报告管理规范要求 #3 重点股票跟踪分析 使用命名 `{name}({code})分析日报_YYYYMMDD.pdf`。当前3个脚本产出3种不同命名，且 Invoke-DailyReportParser.py 读取的MD文件名与 gen_daily_brief.py 产出的不匹配，下游后评估链断裂。

## 二、影响范围

| 文件 | 等级 | 位置 | 当前值 | 目标值 |
|:---|:----|:---|:---|:---|
| `run_keystock_analysis.ps1` | L1 | L1941-1942 | `{name}({code})跟踪日报_{date}.pdf/.html` | `{name}({code})分析日报_{date}.pdf/.html` |
| `gen_daily_brief.py` | L1 | L338 | `{name}({code})日报_{date}.md` | `{name}({code})分析日报_{date}.md` |
| `Invoke-DailyReportParser.py` | L0 | L10-14 | STOCK_MAP 7只(旧池，含长电科技) | 8只(新池) |
| `Invoke-DailyReportParser.py` | L0 | L189 | `重点关注股票日报_{date}.md`(旧) | `{name}({code})分析日报_{date}.md` |
| `convert_daily_brief_pdf.py` | — | 全文 | **删除** — 死代码，无调用方 | — |

## 三、数据流

```
run_keystock_analysis.ps1
  ├─ 直接生成 PDF: {name}({code})分析日报_{date}.pdf  (命名修复 #1)
  └─ 调用 gen_daily_brief.py
       └─ 产出 MD: {name}({code})分析日报_{date}.md    (命名修复 #2)
            └─ Invoke-DailyReportParser.py 读取          (命名修复 #3+#4)
                 └─ 产出: 评估数据_{date}.json → 后评估白皮书v1.8
```

`convert_daily_brief_pdf.py` 不在任何活跃调用链中，确认删除。

## 四、变更方案

### 4.1 run_keystock_analysis.ps1 L1941-1942

```powershell
# 旧
$pdfFile = Join-Path $outDir "${folderName}跟踪日报_${dateStr}.pdf"
$htmlFile = Join-Path $outDir "${folderName}跟踪日报_${dateStr}.html"

# 新
$pdfFile = Join-Path $outDir "${folderName}分析日报_${dateStr}.pdf"
$htmlFile = Join-Path $outDir "${folderName}分析日报_${dateStr}.html"
```

### 4.2 gen_daily_brief.py L338

```python
# 旧
md_path = os.path.join(out_dir, f'{name}({code})日报_{date_str}.md')

# 新
md_path = os.path.join(out_dir, f'{name}({code})分析日报_{date_str}.md')
```

### 4.3 Invoke-DailyReportParser.py L10-14 (STOCK_MAP)

```python
# 旧
STOCK_MAP = {
    '600114': '东睦股份', '601727': '上海电气', '603019': '中科曙光',
    '301075': '多瑞医药', '601689': '拓普集团', '000967': '盈峰环境',
    '600584': '长电科技',
}

# 新
STOCK_MAP = {
    '600114': '东睦股份', '601727': '上海电气', '603019': '中科曙光',
    '301075': '多瑞医药', '601689': '拓普集团', '000967': '盈峰环境',
    '002230': '科大讯飞', '603092': '德力佳',
}
```

### 4.4 Invoke-DailyReportParser.py L189 (MD读取路径)

```python
# 旧
report_path = os.path.join(report_dir, f'{name}({code})', f'重点关注股票日报_{date_str}.md')

# 新
report_path = os.path.join(report_dir, f'{name}({code})', f'{name}({code})分析日报_{date_str}.md')
```

### 4.5 convert_daily_brief_pdf.py — 删除

- 硬编码7只旧池股票(L5-13)
- 硬编码日期 `20260526`(L149)
- 读取旧命名 `重点关注股票日报_`(L153)
- 无任何活跃脚本或调度任务调用
- PDF生成已由 run_keystock_analysis.ps1 直接完成

## 五、接口契约

无接口变更。评分引擎、数据结构、API调用均不变。仅变更报告文件命名和MD读取路径对齐。

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解 |
|:---|:---|:---|:---|
| 旧命名MD被其他脚本读取 | 低 | 中 | 已grep全量搜索，仅 Invoke-DailyReportParser.py 读取MD |
| convert_daily_brief_pdf.py 被调度任务调用 | 低 | 中 | 已搜索 .claude/scheduled_tasks.json，无引用 |
| 后评估链因MD路径变更断裂 | 低 | 高 | Invoke-DailyReportParser.py 同步更新读取路径 |

## 七、需求→代码核对清单

| # | 需求 | 文件 | 行号 | 验证方法 |
|:--|:-----|:-----|:----|:-----|
| 1 | PDF命名 `分析日报` | run_keystock_analysis.ps1 | L1941-1942 | grep `分析日报` |
| 2 | MD命名 `分析日报` | gen_daily_brief.py | L338 | grep `分析日报` |
| 3 | STOCK_MAP 8只新池 | Invoke-DailyReportParser.py | L10-14 | 人工比对 focus-stock-list.md |
| 4 | MD读取路径对齐 | Invoke-DailyReportParser.py | L189 | grep `分析日报` |
| 5 | 删除死代码 | convert_daily_brief_pdf.py | — | 文件不存在 |

---

> 情墨+腰子勾签：________ / ________ | 日期：2026-05-27
