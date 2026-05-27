# 门户站 #deep / #daily 报告过滤器 — 架构设计

> pipeline_stage: complete | 版本 v1.0 | 2026-05-27
> 设计人：情墨 | 模块等级：L0（工具/展示层扩展）

---

## 一、需求

当前 `#deep`（深度分析报告）和 `#daily`（分析日报）两个 Tab 仅展示每只股票的最新一份报告卡片，无任何筛选控件。用户要求增加两个过滤维度：

1. **按日期选择** — 下拉列出所有历史报告日期，选中后仅展示该日期的报告
2. **按股票选择** — 下拉列出所有股票，选中后仅展示该股票的报告

两个过滤器为 **AND 逻辑**：同时选中日期+股票时，展示交集。

---

## 二、现状分析

### 2.1 数据模型（当前 — 扁平、仅最新）

```javascript
// 当前 window.__PORTAL_DATA__
{
  "deep_analysis": [
    {"code":"601727", "name":"上海电气", "date":"20260526", "html_url":"deep_analysis/601727/report.html", ...}
    // 每只股票仅 1 条 — 最新日期
  ],
  "daily_reports": [
    {"code":"601727", "name":"上海电气", "date":"20260526", ...}
    // 同上
  ]
}
```

### 2.2 文件部署（当前 — 单文件覆盖）

```
docs/
  deep_analysis/{code}/report.html   ← 仅最新一份，每次构建覆盖
  daily_reports/{code}/report.html   ← 同上
```

### 2.3 UI（当前 — 仅标题+卡片网格）

`#tab-deep` 和 `#tab-daily` 只有 `<div class="section-header">` + `<div class="report-grid">`，无 filter-bar。

---

## 三、设计方案

### 3.1 数据模型扩展

从"扁平、仅最新"扩展为"全量历史"：

```javascript
// 新 window.__PORTAL_DATA__
{
  "deep_analysis": [
    {"code":"601727", "name":"上海电气", "date":"20260526", "html_url":"deep_analysis/601727/20260526/report.html", ...},
    {"code":"601727", "name":"上海电气", "date":"20260523", "html_url":"deep_analysis/601727/20260523/report.html", ...},
    {"code":"600114", "name":"东睦股份", "date":"20260526", "html_url":"deep_analysis/600114/20260526/report.html", ...},
    // 每只股票 × 每个日期 = N条记录
  ],
  "daily_reports": [ /* 同上结构 */ ]
}
```

**字段定义**（向后兼容，仅 URL 路径变化）：

| 字段 | 类型 | 必填 | 说明 |
|:-----|:----:|:----:|:-----|
| code | string | ✅ | 6位股票代码 |
| name | string | ✅ | 股票名称 |
| date | string | ✅ | 8位日期 YYYYMMDD |
| html_url | string | ❌ | 相对路径，含日期子目录 |
| html_size | string | ❌ | 如 "27KB" |
| pdf_url | string | ❌ | 相对路径，含日期子目录 |
| pdf_size | string | ❌ | 如 "508KB" |
| missing | string[] | ✅ | 缺失项列表 |

### 3.2 文件部署策略

从单文件覆盖改为按日期分层存储：

```
docs/
  deep_analysis/{code}/{date}/report.html   ← 每日期一份
  deep_analysis/{code}/{date}/report.pdf
  daily_reports/{code}/{date}/report.html
  daily_reports/{code}/{date}/report.pdf
```

**决策理由**：
- GitHub Pages 仓库上限 1GB，当前约 8 股 × 10 个交易日 × 2 格式 ≈ 160 个文件，远在安全范围内
- 按日期分层避免文件名冲突，URL 直观可读
- 旧 `{code}/report.html` 路径不再写入，但无需手动清理（新条目不引用旧路径）

### 3.3 UI 设计 — 过滤器栏

在每个报告 Tab 的面板顶部、section-header 下方插入 filter-bar。**完全复用 Events Tab 已有的 `.filter-bar` CSS**，保持视觉一致。

```
┌─────────────────────────────────────────────────────┐
│ 📊 深度分析报告（周报）                               │
│ 每周深度分析 · 点击在新标签页打开完整报告               │
├─────────────────────────────────────────────────────┤
│ [股票 ▼] [日期 ▼] [重置]                             │  ← 新增 filter-bar
├─────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│ │ 上海电气  │ │ 东睦股份  │ │ 中科曙光  │ ...         │
│ │ 601727    │ │ 600114   │ │ 603019   │             │
│ └──────────┘ └──────────┘ └──────────┘             │
```

**控件清单**：

| 控件 | 类型 | ID | 说明 |
|:-----|:----:|:---|:-----|
| 股票选择 | `<select>` | `filter-deep-stock` / `filter-daily-stock` | 从数据提取唯一股票列表 |
| 日期选择 | `<select>` | `filter-deep-date` / `filter-daily-date` | 从数据提取唯一日期列表（倒序） |
| 重置按钮 | `<button>` | — | 清空两个下拉，恢复全部展示 |

### 3.4 JavaScript 逻辑设计

```
数据流：
  __PORTAL_DATA__.deep_analysis (全量数组)
    │
    ├─→ extractUniqueStocks() → 填充股票 dropdown
    ├─→ extractUniqueDates()  → 填充日期 dropdown
    │
    └─→ filterReports(stock, date) → 过滤后的数组 → renderReportCards()
```

**新增函数**：

| 函数 | 职责 |
|:-----|:-----|
| `populateReportFilters(tabId, reports)` | 从报告数组中提取唯一股票/日期，填充对应 dropdown |
| `filterAndRenderReports(tabId)` | 读取当前 filter state，过滤数据，调用 `renderReportCards()` |
| `resetReportFilters(tabId)` | 清空 filter state，恢复全部展示 |

**修改函数**：

| 函数 | 变更 |
|:-----|:-----|
| `loadReports()` | 改为调用 `populateReportFilters()` + `filterAndRenderReports()` |
| `renderReportCards()` | **不改签名**，仍接受 `(containerId, reports, badgeId)`，仅数据传入前已被过滤 |

### 3.5 构建脚本变更（generate_portal.py）

**步骤 [2/5] 深度分析扫描**：

```python
# 当前逻辑（仅取最新）
html_files = sorted(glob.glob(...), reverse=True)
latest_html = html_files[0]  # ← 只取 [0]

# 新逻辑（取全部）
for html_file in html_files:          # ← 遍历全部
    date_str = extract_date(html_file)
    dest = f"deep_analysis/{code}/{date_str}/report.html"
    shutil.copy2(html_file, dest)
    deep_index.append({...})           # ← 每条日期一条记录
```

**步骤 [3/5] 日报扫描**：同上逻辑。

**向后兼容**：`deep_index` / `daily_index` 数组结构不变（仅条目增多），现有 `portal_template.html` 的 `renderReportCards()` 无需改动。

### 3.6 性能评估

| 指标 | 当前 | 变更后 | 评估 |
|:-----|:----:|:------:|:-----|
| `index.html` 大小 | ~300KB | ~400KB | JSON 条目增多，仍在可接受范围 |
| `docs/` 目录大小 | ~5MB | ~25MB | 历史文件增多，GitHub Pages 安全 |
| 页面渲染时间 | <50ms | <100ms | 纯客户端过滤，无网络请求 |
| 构建时间 | ~2s | ~3s | 文件复制量增大 |

---

## 四、文件变更清单

| 文件 | 等级 | 变更类型 | 说明 |
|:-----|:----:|:--------|:-----|
| `代码文件/信鸽信息采集/portal_template.html` | L1 | 修改 | 新增 filter-bar HTML + JS 过滤逻辑 |
| `代码文件/信鸽信息采集/generate_portal.py` | L0 | 修改 | 全量历史文件复制 + 全量数据嵌入 |
| `docs/index.html` | — | 重新生成 | 由 generate_portal.py 产出 |

**不涉及**：`portal_deploy.ps1`（部署流程不变，仍是 `git add docs/`）

---

## 五、风险与降级

| 风险 | 概率 | 影响 | 应对 |
|:-----|:----:|:----:|:-----|
| 历史文件过多导致 index.html 超 1MB | 低 | 页面加载变慢 | 设置日期数量上限（如最近 30 个交易日），超出截断 |
| 某股票某日期仅 HTML 无 PDF | 中 | 该条目 PDF 按钮禁用 | `missing` 字段已覆盖，前端 `btn-disabled` 降级 |
| 构建时文件复制失败 | 低 | 条目缺失 | 已有 try-except 保护（generate_portal.py 中 os.path 操作） |

---

## 六、需求→代码核对清单

> 情墨+腰子共同勾签后放行（闸门1a）

| # | 需求点 | 对应实现 | 勾签 |
|:--|:------|:---------|:----:|
| 1 | #deep 页面可按日期筛选 | filter-bar 日期 dropdown → `filterAndRenderReports("deep")` | ☐ |
| 2 | #deep 页面可按股票筛选 | filter-bar 股票 dropdown → `filterAndRenderReports("deep")` | ☐ |
| 3 | #daily 页面可按日期筛选 | filter-bar 日期 dropdown → `filterAndRenderReports("daily")` | ☐ |
| 4 | #daily 页面可按股票筛选 | filter-bar 股票 dropdown → `filterAndRenderReports("daily")` | ☐ |
| 5 | 日期+股票 AND 逻辑 | `filterReports()` 双条件叠加 | ☐ |
| 6 | 历史报告可查看 | 全量文件部署到 `{code}/{date}/` 路径 | ☐ |
| 7 | 样式与现有 Events Tab 一致 | 复用 `.filter-bar` CSS | ☐ |
| 8 | 重置按钮恢复全部 | `resetReportFilters()` | ☐ |
| 9 | 不影响 Events Tab 现有功能 | 独立 filter state，不修改 Events 代码 | ☐ |
| 10 | 向后兼容 | `renderReportCards()` 签名不变 | ☐ |

---

## 七、十二项自查（CH1-CH12）

| 编号 | 审查项 | 结论 | 备注 |
|:----:|:-------|:----:|:-----|
| CH1 | 模块边界 | ✅ | 变更限定在"信鸽信息采集"模块内（portal_template + generate_portal） |
| CH2 | 接口完整 | ✅ | 数据字段已定义类型+必填，filter state 为本地状态无外部依赖 |
| CH3 | 1+2架构 | N/A | 本次为纯展示层变更，不涉及数据获取 |
| CH4 | 第三方依赖 | ✅ | 无新增依赖 |
| CH5 | 循环依赖 | ✅ | 无新增模块间引用 |
| CH6 | 单点故障 | ✅ | 静态站点无服务端，构建失败不会影响已部署版本 |
| CH7 | 反模式 | ✅ | 不触发 AP-01~AP-07 任何反模式 |
| CH8 | 影响范围 | ✅ | 仅 2 源文件 + 1 生成文件，部署流程不变 |
| CH9 | API超时 | N/A | 纯静态，无运行时 API 调用 |
| CH10 | 回退方案 | ✅ | git revert 上次提交即可恢复旧版 index.html + 旧文件结构 |
| CH11 | 通知关联 | ⚠️ | 需通知红枫（部署）确认 docs/ 大小增长在 GitHub Pages 可接受范围 |
| CH12 | 红线合规 | ✅ | 不删除 PDF、不编造数据、不涉及文档同步 |

> **CH11 说明**：`docs/` 目录预计从 ~5MB 增长至 ~25MB。GitHub Pages 源目录建议 <1GB，发布站点建议 <100MB。本次增长在安全边界内。
