# 深度分析WEB周去重 + 动态股票过滤 — 架构设计

> pipeline_stage: complete
> 设计者: 情墨 | 日期: 2026-05-27 | 代码分级: L类（单文件≤50行，不改接口签名）
> 关联: [[design_portal_local_first_workflow_20260527]]

---

## 一、需求

| # | 需求 | 来源 |
|:--|:-----|:-----|
| R1 | 深度分析周报按自然周去重 — 同一周多份报告时WEB只展示最新版本 | 用户 |
| R2 | 动态股票过滤 — WEB仅显示 `pigeon_config.json` 中 `target_stocks` 的股票，非重点股票(如招商银行/长电科技)不展示 | 用户 |

---

## 二、现状分析

### 2.1 当前数据流

```
重点股票/深度分析/深度分析报告/{股票名(代码)}/*.html|pdf
        │
        ▼ generate_portal.py [2/5]
        │ 扫描所有股票目录 → 按日期建索引 → 复制到 docs/deep_analysis/{code}/{date}/
        │ 问题1: 同周多日期 → 多条记录
        │ 问题2: 不检查 config 白名单 → 非重点股票也展示
        ▼
docs/index.html  ← portal_template.html + 内嵌数据
```

### 2.2 焦点股票清单（2026-05-27）

`pigeon_config.json` → `target_stocks`: 8只
600114(东睦), 603019(中科曙光), 301075(多瑞医药), 601689(拓普集团), 000967(盈峰环境), 601727(上海电气), 002230(科大讯飞), 603092(德力佳)

**不在白名单但仍存在报告目录的**: 600036(招商银行), 600584(长电科技)

---

## 三、设计方案

### 3.1 改动文件

**单文件**: `代码文件/信鸽信息采集/generate_portal.py` — [2/5] 深度分析扫描段

### 3.2 R1: 自然周去重

```python
# 在 all_dates 循环收集完所有 entries 后，写入 deep_index 前：
from datetime import date

# 按 (code, iso_week) 分组，每组保留 date_str 最大的（最新）
week_groups = {}
for entry in all_entries_raw:
    d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
    iso_year, iso_week, _ = d.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"
    group_key = (code, week_key)
    if group_key not in week_groups or date_str > week_groups[group_key]['date_str']:
        week_groups[group_key] = entry  # 保留最新的

# 输出路径改为: deep_analysis/{code}/{week_key}/report.html
# 索引字段: "date" → week_label(展示用), "report_date" → 精确日期
```

**ISO周计算示例**:
- 2026-05-25(周一) → 2026-W21
- 2026-05-26(周二) → 2026-W21
- 2026-05-27(周三) → 2026-W21
- → 去重后仅保留 20260527

### 3.3 R2: 动态股票过滤

```python
# 从 config 读取白名单
target_codes = {s['code'] for s in config.get('target_stocks', [])}

# 扫描时跳过不在白名单的股票
if code not in target_codes:
    print(f"  {name}({code}): SKIP (不在重点股票清单)")
    continue
```

### 3.4 输出结构变化

```
docs/deep_analysis/
  旧: {code}/{date}/report.html     (按日期)
  新: {code}/{week}/report.html     (按自然周)
  例: deep_analysis/603019/2026-W21/report.html
```

### 3.5 不变部分

- 日报(Tab 3) — 仍按交易日展示，不做周去重
- 事件面板(Tab 1) — 不变
- 门户模板样式 — 不变
- `portal_deploy.ps1` — 流程不变

---

## 四、需求→代码核对清单

| # | 需求点 | 代码位置 | 验证方法 |
|:--|:-----|:-----|:-----|
| ✓1 | 同周多日期→仅保留最新 | [2/5] week_groups 分组逻辑 | 构建后检查 deep_analysis 索引，同(code,week)仅1条 |
| ✓2 | 非白名单股票不展示 | [2/5] target_codes 过滤 | 构建后确认 600036/600584 不出现在索引中 |
| ✓3 | 周标签格式 2026-W21 | [2/5] iso_year, iso_week 格式化 | 构建后索引 date 字段格式校验 |
| ✓4 | 输出文件路径按周 | [2/5] out_dir = DEEP_OUT/code/week | 目录名匹配周标签 |
| ✓5 | 日报Tab不受影响 | [3/5] 不变 | 构建后 daily_reports 索引正常 |

---

## 五、执行流程

```
build → verify(本地:8888) → deploy(git push → GitHub Pages)
```

情墨 ✓ | 待腰子确认 → 待新安旧影审查 → 红结编码 → 新安验证 → 红枫部署
