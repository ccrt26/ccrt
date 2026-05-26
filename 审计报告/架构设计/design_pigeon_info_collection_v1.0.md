# 信鸽信息采集与噪音过滤系统 — 架构设计

> 版本 v1.0 | 2026-05-26 | 情墨 | pipeline_stage: complete | finance_confirmed: true | gate_1a: 2026-05-26 腰子+山猫+玉夜+流金+青山全团确认
> 关联：腰子知识库/10-催化剂事件追踪 + 腰子知识库/18-事件驱动策略框架
> 前置讨论：山猫评估 + 腰子全团咨询 + 阿黑外部调研 + 五层漏斗方案

---

## 一、需求概述

### 1.1 背景

腰子团队（山猫/玉夜/流金/青山）确认：缺少个股消息面/事件驱动数据是当前AI分析体系最致命的短板。外部调研确认技术方案成熟（cninfo公开JSON API + china-stock-mcp + baostock[14]已有预告/快报）。学术实证表明原始财经信息93%是噪音，需五层过滤。

### 1.2 目标

1. 每日盘后自动采集6只重点股票的四类消息（公司公告/行业政策/机构观点/风险事件）
2. 五层噪音过滤漏斗 → 每只股票每日入库≤5条高价值信号
3. 结构化输出对接腰子催化剂追踪表 + 青山事件数据库

### 1.3 范围

- **纳入**：信鸽采集脚本 + 五层过滤逻辑 + 结构化输出 + 缓存层
- **不纳入**：信鸽角色定义（M类元操作，阿黑负责）、评分模型修改（后续Phase）、WebFetch行业政策采集（本设计覆盖但标记为Phase 2）

---

## 二、技术架构

### 2.1 数据源方案（基于阿黑外部调研）

| 消息类别 | 主源 | 备源 | 获取方式 |
|:--------|:-----|:-----|:--------|
| 公司公告 | cninfo JSON API | china-stock-mcp `get_news_data` | HTTP GET 结构化JSON |
| 业绩预告/快报 | baostock[14] | cninfo JSON API | 已有桥接脚本 |
| 研报/评级 | 东财研报[11] | china-stock-mcp | 已有封装 |
| 行业政策 | WebFetch 工信部/发改委 | 百度资讯搜索 | Phase 2（每周2次） |
| 风险事件 | cninfo JSON API | china-stock-mcp | 同公司公告 |

> **关键决策**：cninfo有公开JSON API (`cninfo.com.cn/new/fulltextSearch/full`)，不需要爬HTML。WebFetch从"主力"降为仅行业政策场景的"补充"。

### 2.2 系统架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                      千光 - 定时调度                               │
│                 每日 15:30 (收盘后) 触发                           │
│              节假日跳过 (holidays_2026.csv)                        │
└─────────────────────────────┬────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────┐
│                    信鸽采集管线 (主控脚本)                          │
│                   pigeon_collector.ps1                             │
│                                                                   │
│  Step 1: baostock[14] 业绩预告/快报 (6股×2类, 串行, 0.5s间隔)      │
│  Step 2: cninfo API 公司公告 (6股×关键词搜索, 串行, 1s间隔)         │
│  Step 3: 东财[11] 研报 (已有封装, 1+2架构)                         │
│  Step 4: china-stock-mcp 备源补充 (仅主源失败时触发)                │
│  Step 5: WebFetch 行业政策 (仅周二/周五, Phase 2)                   │
└─────────────────────────────┬────────────────────────────────────┘
                              │ 原始消息 (~50条/股)
┌─────────────────────────────▼────────────────────────────────────┐
│                    五层噪音过滤漏斗                                 │
│                   pigeon_filter.ps1                                │
│                                                                   │
│  L1: 黑名单关键词丢弃 (~40%)                                       │
│  L2: 腰子五问法 (Q1-Q5至少YES一个) (~50%)                          │
│  L3: 山猫增量性+可传导性检查 (~30%)                                 │
│  L4: 青山标签分类+流金5条上限+去重 (~50%)                           │
│  → 输出: ≤5条/股/日                                                │
└─────────────────────────────┬────────────────────────────────────┘
                              │ 结构化事件记录
┌─────────────────────────────▼────────────────────────────────────┐
│                    结构化输出 + 缓存                                │
│                                                                   │
│  输出: 重点股票/消息面数据/<YYYY-MM-DD>_events.json                │
│  缓存: 消息面数据/cache/ (TTL=24h)                                 │
│  格式: 腰子知识库/18 §五 事件记录JSON Schema                       │
└─────────────────────────────┬────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼───────┐   ┌─────────▼─────────┐   ┌───────▼───────┐
│ 山猫(行业层)   │   │ 腰子(个股分析)     │   │ 青山(因子库)   │
│ 行业政策信号   │   │ 催化剂追踪表更新   │   │ 事件IC数据库   │
└───────────────┘   └───────────────────┘   └───────────────┘
```

### 2.3 技术选型

| 决策点 | 选择 | 理由 |
|:------|:-----|:-----|
| 采集脚本语言 | PowerShell (.ps1) | 与现有管线一致，复用限速器/日志/缓存模块 |
| cninfo API封装 | PowerShell `Invoke-RestMethod` | 无需新增Python依赖 |
| baostock桥接 | 已有 `Invoke-BaostockFallback` | 复用[14]现有封装 |
| china-stock-mcp | MCP协议调用 | Claude Code原生支持，零封装 |
| 过滤引擎 | PowerShell | 规则型过滤，无需ML推理 |
| 输出格式 | JSON (腰子知识库/18 Schema) | 与现有事件驱动框架对齐 |
| 调度 | 千光 Task Scheduler | 复用现有每日管线调度框架 |

---

## 三、模块设计

### 3.1 模块总览

| 模块 | 文件 | 等级 | 职责 | 行数上限 |
|:-----|:-----|:----:|:-----|:------:|
| 主控脚本 | `pigeon_collector.ps1` | L1 | 采集流程编排、Step 1-5调度 | ≤300 |
| cninfo API | `pigeon_cninfo.ps1` | L0 | cninfo JSON API封装、重试、错误处理 | ≤150 |
| 五层过滤 | `pigeon_filter.ps1` | L1 | L1-L4过滤规则引擎 | ≤250 |
| 结构化输出 | `pigeon_output.ps1` | L0 | JSON序列化、缓存写入、去重检查 | ≤100 |
| 配置文件 | `pigeon_config.json` | L0 | 重点股票列表、关键词黑/白名单、Q1-Q5规则 | — |
| 事件数据库 | `消息面数据/events_db.json` | L1 | 历史事件归档、事后IC验证数据源 | — |

### 3.2 模块详细设计

#### 3.2.1 主控脚本 `pigeon_collector.ps1`

```
参数:
  -Stocks <string[]>   目标股票代码列表 (默认: 重点股票6只)
  -Date <string>       采集日期 (默认: 当日)
  -SkipFilter          跳过过滤层 (调试用)
  -OutputPath <string> 输出路径 (默认: 重点股票/消息面数据/)

流程:
  1. 读取 pigeon_config.json
  2. foreach stock in Stocks:
       a. Step 1: 调用 baostock[14] → 获取业绩预告/快报
       b. Step 2: 调用 cninfo API → 获取公司公告
       c. Step 3: 调用 东财[11] → 获取研报
       d. Step 4: (备源触发) 主源失败→调用 china-stock-mcp
       e. Step 5: (仅周二/周五) WebFetch行业政策
  3. 汇总原始消息 → 传入五层过滤
  4. 输出结构化JSON
  5. 更新缓存[C], TTL=24h

退出码:
  0 - 全部成功
  1 - 部分源失败(已降级备源/缓存)
  2 - 全部源失败(仅缓存兜底)
  3 - 配置错误
```

#### 3.2.2 cninfo API封装 `pigeon_cninfo.ps1`

```
函数: Invoke-CninfoAnnouncement
参数:
  -StockCode <string>   股票代码 (如 600114)
  -StockName <string>   股票名称 (如 东睦股份)
  -StartDate <string>   起始日期 (yyyy-MM-dd)
  -EndDate <string>     结束日期 (yyyy-MM-dd)
  -MaxResults <int>     最大返回条数 (默认: 20)

API端点:
  GET http://www.cninfo.com.cn/new/fulltextSearch/full
  参数: searchkey=<StockName>&sdate=<StartDate>&edate=<EndDate>
        &isfulltext=false&sortName=pubdate&sortType=desc&pageNum=1

返回: 结构化公告列表
  [
    {
      "announcementTitle": "...",
      "announcementTime": "2026-05-26 16:30:00",
      "adjunctUrl": "final/2026/05/26/...",
      "secName": "东睦股份",
      "secCode": "600114"
    }
  ]

重试策略: 间隔≥1s, 最多重试2次, 指数退避(1s→2s→4s)
降级路径: cninfo API失败 → china-stock-mcp[备] → 缓存[C]
```

#### 3.2.3 五层过滤引擎 `pigeon_filter.ps1`

```
函数: Invoke-PigeonFilter
输入: 原始消息数组 (RawMessages[])
输出: 过滤后消息数组 (FilteredMessages[], 每只股票≤5条)

=== L1: 黑名单关键词丢弃 ===
规则:
  - 标题包含黑名单任一关键词 → 丢弃
  - 来源域名在黑名单 → 丢弃

黑名单关键词 (从 pigeon_config.json 读取):
  "行情点评","原因何在","技术分析","MACD","金叉","死叉",
  "压力位","支撑位","明日展望","涨停预测","机构推荐",
  "盘后总结","龙虎榜解读","资金流向解读","涨停板复盘",
  "短线机会","牛股推荐","暴涨","暴跌","翻倍","腰斩",
  "散户","股吧","吧友","大神","老师"

黑名单来源域名:
  "guba.eastmoney.com","xueqiu.com","weibo.com",
  "tieba.baidu.com","douyin.com","kuaishou.com"

=== L2: 腰子五问法 ===
每条消息必须满足 Q1-Q5 至少一项:

Q1_财务数据: 标题/摘要包含 "净利润|营收|EPS|ROE|毛利|订单金额|减值|分红"
Q2_股权结构: 标题/摘要包含 "增持|减持|回购|质押|解禁|收购|股权|控制权"
Q3_监管法律: 标题/摘要包含 "问询|立案|处罚|警示|ST|*ST|退市|注册批复|核准"
Q4_产能产品: 标题/摘要包含 "投产|量产|定点|获批|新产品|新线|产能"
Q5_竞争格局: 标题/摘要包含 "破产|退出|禁令|制裁|反倾销|补贴|关税|准入"

五个问题全答 NO → 丢弃

=== L3: 山猫增量性检查 ===
规则:
  - 与近3日已入库消息标题相似度>80% → 标记为"重复" → 丢弃
  - 行业政策类: 检查是否与已知政策口径重复 → 重复则丢弃
  - 研报类: 无评级调整+无盈利预测修正 → 丢弃

=== L4: 青山标签 + 流金上限 ===
规则:
  - 每只股票按 impact_score 排序, 取前5条
  - impact_score = 事件权重 × 确定性 × 时效性 (算法见§4.2)
  - P0级事件(立案/ST/全部质押/重组失败)不受5条上限限制
  - 打标签: Layer1大类 + Layer2子类 + Layer3方向/幅度/确定性

=== 过滤统计 ===
每层记录: 输入条数 → 丢弃条数 → 丢弃原因分布 → 输出条数
写入日志: 每日采集完成后输出 "L1: 50→30 | L2: 30→15 | L3: 15→10 | L4: 10→5"
```

#### 3.2.4 结构化输出 `pigeon_output.ps1`

```
函数: Export-PigeonEventJson
输入: FilteredMessages[] (≤5条/股)
输出: 重点股票/消息面数据/<YYYY-MM-DD>_events.json

JSON Schema (对齐腰子知识库/18 §五):
{
  "fetch_date": "2026-05-26",
  "fetch_time": "15:35:00",
  "total_raw": 287,
  "total_filtered": 28,
  "filter_stats": {
    "L1_dropped": 115, "L2_dropped": 86, "L3_dropped": 42, "L4_dropped": 16
  },
  "events": [
    {
      "event_id": "PIGEON_20260526_600114_001",
      "code": "600114",
      "name": "东睦股份",
      "category": "公司公告",       // Layer1大类
      "subtype": "并购重组",         // Layer2子类
      "title": "发行股份购买上海富驰34.75%股权获证监会注册批复",
      "source": "cninfo",
      "source_type": "primary",
      "reliability": "verified",    // verified/single_source/unverified
      "quantifiable": true,
      "direction": 1,              // +1利好/-1利空/0中性
      "impact_score": 8.5,         // 0-10
      "probability": 1.0,          // 0-1
      "structured_fields": {
        "event_type": "merger_registration",
        "status": "approved",
        "amount": null,
        "related_party": "上海富驰"
      },
      "raw_summary": "证监会批复同意东睦股份发行股份购买上海富驰高科技股份有限公司34.75%股权...",
      "expiry_date": "2026-06-05",
      "keywords": ["并购","证监会","注册","富驰"]
    }
  ]
}

函数: Update-PigeonCache
  写入 消息面数据/cache/<YYYY-MM-DD>.json
  TTL=24h, 过期自动清理
```

### 3.3 配置文件 `pigeon_config.json`

```json
{
  "target_stocks": [
    {"code": "600114", "name": "东睦股份", "market": "sh"},
    {"code": "600519", "name": "贵州茅台", "market": "sh"},
    {"code": "000858", "name": "五粮液", "market": "sz"},
    {"code": "300750", "name": "宁德时代", "market": "sz"},
    {"code": "300308", "name": "中际旭创", "market": "sz"},
    {"code": "300418", "name": "昆仑万维", "market": "sz"}
  ],
  "blacklist_keywords": [
    "行情点评","原因何在","技术分析","MACD","金叉","死叉",
    "压力位","支撑位","明日展望","涨停预测","机构推荐",
    "盘后总结","龙虎榜解读","短线机会","牛股推荐"
  ],
  "blacklist_domains": [
    "guba.eastmoney.com","xueqiu.com","tieba.baidu.com"
  ],
  "q1_q5_rules": {
    "Q1_financial": "净利润|营收|EPS|ROE|毛利|订单金额|减值|分红|派现",
    "Q2_ownership": "增持|减持|回购|质押|解禁|收购|股权|控制权|定增",
    "Q3_regulatory": "问询|立案|处罚|警示|ST|退市|注册批复|核准|通过",
    "Q4_capacity": "投产|量产|定点|获批|新产品|新线|产能|中标|合同",
    "Q5_competitive": "破产|退出|禁令|制裁|反倾销|补贴|关税|准入|政策"
  },
  "p0_events": [
    "立案调查","ST风险","*ST","退市风险","全部质押","重组失败","破产"
  ],
  "api": {
    "cninfo_base_url": "http://www.cninfo.com.cn/new/fulltextSearch/full",
    "cninfo_interval_ms": 1000,
    "cninfo_max_retries": 2,
    "baostock_interval_ms": 500
  },
  "schedule": {
    "daily_trigger": "15:30",
    "skip_holidays": true,
    "holidays_file": "每日荐股/运营记录/holidays_2026.csv"
  }
}
```

---

## 四、接口契约

### 4.1 输入接口：各数据源 → 采集层

| 数据源 | 接口类型 | 输入格式 | 输出格式 |
|:------|:--------|:--------|:--------|
| cninfo API | HTTP GET | stockName + dateRange | JSON公告数组 |
| baostock[14] | Python桥接 | stockCode + action | CSV/JSON |
| 东财[11] | 已有PS封装 | stockCode | JSON研报数组 |
| china-stock-mcp | MCP调用 | symbol | Markdown/JSON |
| WebFetch | HTTP (Phase 2) | URL | HTML→文本提取 |

### 4.2 输出接口：采集层 → 消费层

**输出路径**：`重点股票/消息面数据/<YYYY-MM-DD>_events.json`

**JSON Schema 核心字段**：

| 字段 | 类型 | 必填 | 说明 |
|:-----|:-----|:----:|:-----|
| event_id | string | ✅ | 全局唯一ID PIGEON_<date>_<code>_<seq> |
| code | string | ✅ | 股票代码 6位 |
| name | string | ✅ | 股票名称 |
| category | enum | ✅ | Layer1: 业绩/并购重组/股东行为/经营事件/监管合规/行业政策 |
| subtype | string | ✅ | Layer2子类 |
| title | string | ✅ | 原始标题 |
| source | string | ✅ | 数据源标识 |
| source_type | enum | ✅ | primary/backup/cache |
| reliability | enum | ✅ | verified/single_source/unverified |
| quantifiable | bool | ✅ | 是否包含可量化变量 |
| direction | int | ✅ | +1/-1/0 |
| impact_score | float | ✅ | 0-10 综合影响分 |
| probability | float | ✅ | 0-1 事件确定性 |
| structured_fields | object | ❌ | 结构化提取字段 |
| raw_summary | string | ✅ | 原文摘要(≤200字) |
| expiry_date | string | ❌ | 事件影响过期日 |
| keywords | string[] | ✅ | 匹配关键词列表 |

### 4.3 消费方接口约定

| 消费方 | 使用方式 | 读取字段 |
|:------|:--------|:--------|
| 腰子-催化剂追踪 | 每日读取events.json, 更新催化剂状态 | category/subtype/direction/impact_score |
| 山猫-宏观简报 | 筛选category=行业政策, 纳入简报 | title/raw_summary |
| 青山-事件数据库 | 归档events_db.json, T+N回填实际收益 | event_id/direction/impact_score |
| 流金-风控 | 监控P0事件, 触发告警 | category=监管合规 + p0标记 |

---

## 五、代码分级

| 文件 | 等级 | 理由 | 审查要求 |
|:-----|:----:|:-----|:--------|
| pigeon_collector.ps1 | **L1** | 策略输入编排，涉及评分数据上游 | 情墨复审+新安全量+Golden Master |
| pigeon_cninfo.ps1 | **L0** | 纯数据API封装，无业务逻辑 | 红结自查+新安常规 |
| pigeon_filter.ps1 | **L1** | 过滤规则影响评分输入，策略相关 | 情墨复审+新安全量 |
| pigeon_output.ps1 | **L0** | JSON序列化+缓存写入 | 红结自查+新安常规 |
| pigeon_config.json | **L0** | 配置文件，无逻辑 | 红结自查 |

---

## 六、与现有系统的集成

### 6.1 不影响现有管线

信鸽采集是**新增独立管线**，不修改现有每日荐股/深度分析/后评估的任何代码。仅在数据输入侧新增一个数据源。

### 6.2 集成点

| 集成点 | 方式 | 影响 |
|:------|:-----|:----|
| 现有调度框架 | 千光在Task Scheduler新增15:30触发 | 无影响 |
| baostock[14]桥接 | 复用Invoke-BaostockFallback, 新增action参数 | L0变更 |
| 东财[11]研报 | 复用现有封装, 无修改 | 无影响 |
| 缓存层[C] | 新增缓存目录 消息面数据/cache/ | 无影响 |
| 版本管理 | version_supervisor.ps1 新增信鸽模块 | L0变更 |

### 6.3 数据源编号扩展

| 编号 | 来源 | 用途 |
|:----:|:-----|:-----|
| [16] | cninfo JSON API | 公司公告(主源) |
| [17] | china-stock-mcp | 新闻/公告(备源) |

> 玉夜需更新数据源全景(01-数据源全景.md)和API频率限制表(07-API频率限制速查表.md)

---

## 七、风险与回退

### 7.1 已知风险

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:----:|:----:|:-----|
| cninfo API反爬升级 | 中 | 主源不可用 | 自动降级→china-stock-mcp备源 |
| china-stock-mcp依赖akshare版本 | 中 | 备源不可用 | 缓存[C]兜底, TTL=24h |
| 五问法漏杀(重要消息被过滤) | 低 | 遗漏信号 | 每月审查丢弃日志, 调优关键词 |
| 五问法误杀(P0事件被过滤) | 极低 | 遗漏风险预警 | P0关键词白名单, 绕过L1-L3直达L4 |

### 7.2 回退方案

```
全部数据源不可用 → 写入告警日志 → 标注[人工] → 腰子手动查看巨潮网站
采集脚本异常 → 跳过当日采集 → 不阻塞后续管线(评分/报告正常产出)
过滤逻辑异常 → 使用 --SkipFilter 参数 → 全量输出原始消息(紧急模式)
```

---

## 八、部署计划

### Phase 1 (本周): 核心采集 + L1-L2过滤
- 红结编写 pigeon_cninfo.ps1 + pigeon_collector.ps1(Step 1-3)
- 红结编写 pigeon_filter.ps1 (L1黑名单 + L2五问法)
- 新安验证: 采集成功率≥80%, L1+L2过滤率≥60%
- 平行观察: 不入评分, 仅输出JSON供腰子人工校验

### Phase 2 (下周): 备源 + L3-L4过滤 + 行业政策
- 红结编写 china-stock-mcp备源触发逻辑
- 红结编写 L3增量性检查 + L4标签+上限
- 红结编写 WebFetch行业政策采集(周二/周五)
- 新安验证: 全四层过滤率≥85%

### Phase 3 (6月中旬): 集成 + 事后验证
- 青山接入: 事件归档 + T+N收益回填
- 腰子接入: 催化剂追踪表自动更新
- 2周平行观察后, 正式接入评分模型
- 3个月后首次事件IC实证报告

---

## 九、需求→代码核对清单

> 情墨+腰子共同勾签后才能放行至红结

| # | 需求项 | 设计覆盖 | 情墨勾 | 腰子勾 |
|:--:|:------|:-------|:-----:|:-----:|
| 1 | 每日盘后自动采集6只重点股票消息 | §三.2.1 Step 1-5 | ✅ | ✅ |
| 2 | cninfo公开API + 结构化JSON | §三.2.2 | ✅ | ✅ |
| 3 | baostock业绩预告/快报复用 | §三.2.1 Step 1 | ✅ | ✅ |
| 4 | 1+2架构(主源+备源+缓存) | §二.1 数据源方案 | ✅ | ✅ |
| 5 | L1黑名单关键词过滤 | §三.2.3 L1 | ✅ | ✅ |
| 6 | L2腰子五问法过滤 | §三.2.3 L2 | ✅ | ✅ |
| 7 | L3山猫增量性检查 | §三.2.3 L3 | ✅ | ✅ |
| 8 | L4标签+上限+去重 | §三.2.3 L4 | ✅ | ✅ |
| 9 | 每只股票每日≤5条输出 | §三.2.3 L4 | ✅ | ✅ |
| 10 | P0事件不受上限限制 | §三.2.3 L4 + §三.3 p0_events | ✅ | ✅ |
| 11 | 结构化JSON,对接催化剂追踪表 | §四.2 JSON Schema | ✅ | ✅ |
| 12 | 事后T+N验证数据归档 | §四.3 青山消费 | ✅ | ✅ |
| 13 | 不影响现有管线,独立运行 | §六.1 | ✅ | ✅ |
| 14 | 失败降级+回退方案 | §七.2 | ✅ | ✅ |
| 15 | Phase 1平行观察不入评分 | §八 Phase 1 | ✅ | ✅ |

---

> 情墨 · 设计交付物 · pipeline_stage: complete · 提交闸门1a审查
> 关联: 阿黑外部调研报告 + 腰子全团咨询结论 + 五层漏斗方案
