# 信鸽消息面数据Web展示面板 — 架构设计

> 版本 v1.0 | 2026-05-26 | 情墨 | pipeline_stage: complete
> 关联：design_pigeon_info_collection_v1.0.md | pigeon_config.json
> 需求来源：用户要求本地Web页面浏览信鸽采集事件

---

## 一、需求概述

### 1.1 背景

信鸽每日19:00采集7只重点股票的公告/研报事件，经五层过滤后存入 `events_db.json`。目前数据只能通过直接阅读JSON文件查看，缺少直观的浏览界面。

### 1.2 目标

提供本地Web面板：按股票、日期、类别、方向筛选浏览事件；实时查看最新采集结果；展示每日过滤漏斗统计。

### 1.3 范围

- **纳入**：HTTP服务器 + SPA面板 + 启动器
- **不纳入**：移动端适配、多用户权限、数据编辑功能、实时推送

---

## 二、技术架构

### 2.1 技术选型

| 决策点 | 选择 | 理由 | 备选 |
|:-------|:-----|:-----|:-----|
| 后端 | Python `http.server` | 零依赖，Python 3.6+内置，~120行 | Flask（过重）|
| 前端 | 纯HTML/CSS/JS SPA | 零依赖，无框架，与现有dashboard_template.html模式一致 | React（过重）|
| 样式 | 内嵌CSS暗色主题 | 继承项目品牌色，无外部CSS文件依赖 | 外链CSS |
| 启动 | PowerShell脚本 | 与项目现有启动模式一致(pigeon_boot.bat) | .bat直接启动 |

### 2.2 不引入的技术

- npm/Node.js生态：项目未使用，引入会新增依赖
- React/Vue等SPA框架：功能简单，框架开销>收益
- ECharts/D3图表库：无复杂图表需求，CSS进度条足够
- Flask/FastAPI：http.server已在标准库，功能已满足

### 2.3 系统架构图

```
┌────────────────────────────────────────────────────────┐
│  浏览器  http://127.0.0.1:8888/pigeon_dashboard.html    │
│  ┌──────────────────────────────────────────────────┐  │
│  │  摘要卡片 | 筛选栏 | 漏斗统计 | 事件卡片列表        │  │
│  └──────────────────────┬───────────────────────────┘  │
│     fetch() 按需请求     │  GET /api/*                    │
└─────────────────────────┼──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  pigeon_server.py  (http.server.HTTPServer, 127.0.0.1)   │
│  ┌─────────────────────────────────────────────────────┐│
│  │ GET /pigeon_dashboard.html  → 静态HTML文件           ││
│  │ GET /api/summary            → events_db.json 汇总    ││
│  │ GET /api/events?filters     → 筛选后事件列表          ││
│  │ GET /api/daily_stats        → 每日过滤漏斗统计        ││
│  │ GET /api/stocks             → 目标股票列表(config)    ││
│  └─────────────────────────────────────────────────────┘│
└──────────────┬─────────────────────────────────────────┘
               │  json.load()
┌──────────────▼─────────────────────────────────────────┐
│  重点股票/消息面数据/                                     │
│  ├─ events_db.json          (累积事件库)                 │
│  ├─ YYYY-MM-DD_events.json  (每日快照+过滤统计)          │
│  └─ cache/                   (缓存目录)                  │
├────────────────────────────────────────────────────────┤
│  代码文件/信鸽信息采集/pigeon_config.json                 │
└────────────────────────────────────────────────────────┘

启动: launch_pigeon_dashboard.ps1
  → 检测空闲端口 → 启动pigeon_server.py → 打开浏览器
  → 窗口关闭时自动杀进程
```

---

## 三、模块设计

### 3.1 模块清单 + 代码分级

| 文件 | 级别 | 行数 | 职责 | 依赖 |
|:-----|:----:|:----:|:-----|:-----|
| `pigeon_server.py` | L0 | ~100 | HTTP服务+4个JSON API | Python stdlib |
| `pigeon_dashboard.html` | L0 | ~300 | SPA面板(内嵌CSS+JS) | 无 |
| `launch_pigeon_dashboard.ps1` | L0 | ~60 | 启停生命周期管理 | pigeon_server.py |

> 三个文件均为L0（工具/展示层），不涉及评分/交易/风控逻辑，红结自查+新安常规审查即可。

### 3.2 pigeon_server.py

**路径解析**：通过 `__file__` 自动定位项目根目录，读 `../../重点股票/消息面数据/` 和同目录 `pigeon_config.json`。

**API端点**：

| 端点 | 方法 | 参数 | 返回 |
|:-----|:-----|:-----|:-----|
| `/` 或 `/pigeon_dashboard.html` | GET | - | text/html |
| `/api/summary` | GET | - | 汇总统计JSON |
| `/api/events` | GET | code, date, category, direction, search | 事件列表JSON |
| `/api/daily_stats` | GET | - | 每日漏斗统计JSON |
| `/api/stocks` | GET | - | 目标股票列表JSON |

**错误处理**：JSON解析失败返回 `{"error": "..."}` + HTTP 500；文件不存在返回404。

**安全约束**：仅绑定 `127.0.0.1`，不对外暴露。

### 3.3 pigeon_dashboard.html

自包含SPA，无外链CSS/JS，浏览器原生Fetch API。

**前端组件**：

| 组件 | 实现 |
|:-----|:-----|
| 摘要卡片行 | CSS Grid 4列，总事件/覆盖股票/平均影响/方向分布 |
| 筛选栏 | 3个`<select>`(股票/日期/类别) + 4个方向按钮 + 文本搜索 + 重置 |
| 过滤漏斗面板 | 可折叠`<table>`，L1-L4丢弃数+进度条 |
| 事件卡片列表 | 左边框方向色，标题+标签+影响分进度条 |

**CSS变量（品牌色）**：`--bg-primary: #1a1a2e`, `--bg-secondary: #16213e`, `--bg-card: #1f2b47`, `--accent-up: #e74c3c`, `--accent-down: #27ae60`

**交互逻辑**：
- 页面加载 → fetch `/api/summary` + `/api/events` + `/api/daily_stats` + `/api/stocks`
- 筛选变更 → debounced fetch `/api/events?{params}`
- 搜索输入 → 300ms防抖

### 3.4 launch_pigeon_dashboard.ps1

**生命周期**：检测Python → 寻找空闲端口(8888起) → Start-Process启动服务器 → 等待2s确认存活 → Start-Process打开浏览器 → 用户按Enter → Stop-Process杀服务器。

**异常处理**：Python未安装→报错退出；端口全占→报错退出；服务器启动后立即退出→报退出码。

---

## 四、接口契约

### 4.1 事件对象 (JSON)

```json
{
  "event_id": "PIGEON_20260526_600114_001",
  "code": "600114",
  "name": "东睦股份",
  "category": "并购重组",
  "subtype": "并购进展",
  "title": "东睦股份关于实施2025年度利润分配后发行股份...",
  "direction": 1,
  "impact_score": 9.0,
  "fetch_date": "2026-05-26"
}
```

### 4.2 汇总对象 (JSON)

```json
{
  "total_events": 5,
  "today_events": 5,
  "today_date": "2026-05-26",
  "stocks_covered": 4,
  "total_stocks": 7,
  "avg_impact_score": 7.2,
  "by_category": {"业绩":1, "并购重组":1, "股东行为":2, "经营事件":1},
  "by_direction": {"positive":1, "negative":2, "neutral":2},
  "last_fetch_time": "2026-05-26 19:00:59"
}
```

### 4.3 每日统计对象 (JSON)

```json
{
  "date": "2026-05-26",
  "fetch_time": "19:00:59",
  "total_raw": 11,
  "total_filtered": 0,
  "filter_stats": {"L1_dropped":0, "L2_dropped":6, "L3_dropped":5, "L4_dropped":0}
}
```

### 4.4 API筛选参数

| 参数 | 格式 | 示例 |
|:-----|:-----|:-----|
| code | 逗号分隔 | `?code=600114,603019` |
| date | YYYY-MM-DD | `?date=2026-05-26` |
| category | 逗号分隔 | `?category=并购重组,股东行为` |
| direction | 逗号分隔数字 | `?direction=1` 或 `?direction=1,-1` |
| search | URL编码字符串 | `?search=减持` |

### 4.5 消费者集成

| 消费者 | 用法 |
|:-------|:-----|
| 腰子(每日分析) | 打开面板→筛选单只股票→浏览事件→辅助判断 |
| 青山(后评估) | 查看daily_stats→评估过滤效果→调整规则权重 |
| 用户(快速浏览) | 双击launch→查看今日所有事件 |

---

## 五、与现有系统集成

### 5.1 无侵入设计

- 不修改 `pigeon_collector.ps1` 和 `pigeon_output.ps1` 代码
- 不修改 `events_db.json` 格式
- 不新增Python/Node依赖
- 从 `pigeon_config.json` 读取股票列表（保持单一数据源）

### 5.2 部署位置

```
代码文件/信鸽信息采集/
├─ pigeon_server.py           ← 新增
├─ pigeon_dashboard.html      ← 新增
├─ launch_pigeon_dashboard.ps1 ← 新增
├─ pigeon_collector.ps1       (已有)
├─ pigeon_config.json         (已有，读取)
└─ ...
```

---

## 六、风险与回滚

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:----:|:----:|:-----|
| 端口8888被占用 | 中 | 低 | 自动探测空闲端口(8888-8897) |
| Python未安装 | 低 | 高 | 启动脚本检测并报中文错误 |
| events_db.json增长过大 | 低 | 中 | 当前5条，一年~13K条仍<2MB；必要时加`?page=`分页 |
| 浏览器缓存旧HTML | 低 | 低 | 服务器返回 `Cache-Control: no-cache` |

**回滚方案**：删除3个新增文件即可，无其他修改。

---

## 七、需求→代码核对清单

| # | 需求 | 对应代码位置 | 状态 |
|:--|:-----|:-----------|:----:|
| 1 | 本地Web页面展示信鸽事件 | pigeon_dashboard.html | ✓ |
| 2 | 按股票筛选 | `/api/events?code=` + 前端`<select>` | ✓ |
| 3 | 按日期筛选 | `/api/events?date=` + 前端`<select>` | ✓ |
| 4 | 按类别筛选 | `/api/events?category=` + 前端`<select>` | ✓ |
| 5 | 按方向筛选(利好/利空/中性) | `/api/events?direction=` + 前端按钮组 | ✓ |
| 6 | 标题关键词搜索 | `/api/events?search=` + debounce输入 | ✓ |
| 7 | 显示影响分 | 事件卡片分数+进度条 | ✓ |
| 8 | 显示过滤漏斗统计 | `/api/daily_stats` + 可折叠面板 | ✓ |
| 9 | 汇总摘要卡片 | `/api/summary` + 4格CSS Grid | ✓ |
| 10 | 双击启动，关闭窗口停止 | launch_pigeon_dashboard.ps1 | ✓ |
| 11 | 项目品牌色暗色主题 | CSS变量引用品牌色 | ✓ |
| 12 | 零外部依赖 | Python stdlib + 纯HTML/CSS/JS | ✓ |

---

> 情墨签字：✓ 已勾签 &nbsp;&nbsp; 腰子签字：✓ 已勾签
> 闸门1a: 全团咨询完成 → PASS (山猫✓ 信鸽✓ 玉夜✓ 流金✓ 青山✓)
> 闸门1b: 新安+旧影审查 → PASS (新安✓ 旧影✓, WARN:docx同步→已闭环)
> 闸门2: 新安四层验证 → PASS (L1✓ L2✓ L3✓ L4✓)
> 闸门3: 红枫灰度部署 → PASS (部署记录✓ docx✓ 回滚方案✓)
>
> ### v1.1 增量 (2026-05-26): 事件原文查看
> - pigeon_filter.ps1 +2行: L4事件保留 `pdf_url`
> - pigeon_output.ps1 +1行: dbEntry写入 `pdf_url`
> - pigeon_dashboard.html +80行: 点击卡片内联展开详情面板 + PDF原文链接
> - 级别: L0 展示层增量
