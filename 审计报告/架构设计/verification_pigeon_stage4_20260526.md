# 阶段⑤ 四层验证报告 — 信鸽信息采集系统

> 验证日期: 2026-05-26 | 验证人: 新安(质量工程师)
> 被验证: 阶段④红结编码交付物
> 设计文档: design_pigeon_info_collection_v1.0.md

---

## 一、L0 基础检查

### 1.1 文件清单

| 文件 | 设计路径 | 实际路径 | 状态 |
|:-----|:--------|:--------|:----:|
| pigeon_config.json | 代码文件/信鸽信息采集/ | ✅ 一致 | OK |
| pigeon_cninfo.ps1 | 代码文件/信鸽信息采集/ | ✅ 一致 | OK |
| pigeon_filter.ps1 | 代码文件/信鸽信息采集/ | ✅ 一致 | OK |
| pigeon_output.ps1 | 代码文件/信鸽信息采集/ | ✅ 一致 | OK |
| pigeon_collector.ps1 | 代码文件/信鸽信息采集/ | ✅ 一致 | OK |

### 1.2 代码量检查

| 文件 | 设计预估 | 实际行数 | 红线500行 | 判定 |
|:-----|:------:|:------:|:------:|:----:|
| pigeon_cninfo.ps1 | ≤150 | 121 | ✅ | OK |
| pigeon_filter.ps1 | ≤250 | 342 | ✅ | WARN (超预估但未超500) |
| pigeon_output.ps1 | ≤100 | 188 | ✅ | WARN (超预估但未超500) |
| pigeon_collector.ps1 | ≤280 | 321 | ✅ | WARN (超预估但未超500) |
| pigeon_config.json | ≤60 | 66 | N/A | OK |

> WARN说明: 实际行数超出设计阶段预估，但均未触及500行红线。建议Phase 2重构时考虑pigeon_filter.ps1拆分。

### 1.3 PowerShell语法检查

| 文件 | 解析结果 |
|:-----|:------:|
| pigeon_cninfo.ps1 | ✅ PASS |
| pigeon_filter.ps1 | ✅ PASS |
| pigeon_output.ps1 | ✅ PASS |
| pigeon_collector.ps1 | ✅ PASS |

---

## 二、L1 设计符合性检查

### 2.1 需求→代码核对

| # | 需求项 | 实现文件 | 符合度 |
|:--:|:------|:--------|:-----:|
| 1 | 每日盘后自动采集6只重点股票 | pigeon_collector.ps1 | ✅ |
| 2 | cninfo公开API + 结构化JSON | pigeon_cninfo.ps1 | ✅ |
| 3 | baostock业绩预告/快报复用 | pigeon_collector.ps1::Invoke-BaostockForecast | ✅ |
| 4 | 1+2架构(主源[16]+备源[17]+缓存[C]) | pigeon_cninfo.ps1 + pigeon_output.ps1 | ✅ |
| 5 | L1黑名单关键词过滤 | pigeon_filter.ps1 L1 | ✅ |
| 6 | L2腰子五问法过滤 | pigeon_filter.ps1 L2 | ✅ |
| 7 | L3山猫增量性检查 | pigeon_filter.ps1 L3 | ✅ |
| 8 | L4标签+上限+去重 | pigeon_filter.ps1 L4 | ✅ |
| 9 | 每只股票每日≤5条输出 | pigeon_filter.ps1 L4a | ✅ |
| 10 | P0事件不受上限限制 | pigeon_filter.ps1 L4a ($p0Events) | ✅ |
| 11 | 结构化JSON输出 | pigeon_output.ps1 | ✅ |
| 12 | T+N回测预留字段(S3) | pigeon_output.ps1 events_db | ✅ |
| 13 | 不影响现有管线 | 独立目录+独立调度 | ✅ |
| 14 | 失败降级+回退方案 | exit 0/1/2 + 备源+缓存 | ✅ |
| 15 | Phase 1平行观察不入评分 | 无评分模型调用 | ✅ |

### 2.2 闸门1a优化建议落地检查

| # | 建议 | 来源 | 落地位置 | 状态 |
|:--:|:-----|:-----|:--------|:----:|
| S1 | 首次覆盖研报保留 | 山猫 | pigeon_filter.ps1 L3b `$isFirstCoverage` | ✅ |
| S2 | 去重阈值从80%→70% | 山猫 | pigeon_config.json `dedup_similarity_threshold: 0.70` | ✅ |
| S3 | events_db预留T+N回测字段 | 青山 | pigeon_output.ps1 `actual_return_T1/T3/T5` | ✅ |
| S4 | impact_score权重在config定义 | 流金 | pigeon_config.json `impact_score_weights` | ✅ |

---

## 三、L2 红线合规检查

| 红线条款 | 检查点 | 结果 |
|:--------|:------|:----:|
| §1.1 1+2架构 | 每个消息类别主+备+缓存 | ✅ |
| §1.2 关键公式 | N/A (不涉及PE计算) | — |
| §1.3 禁止编造 | 所有数据来自API，无推测 | ✅ |
| §1.7 禁止删PDF | 不涉及PDF操作 | ✅ |
| §5.4 文档同步 | 设计文档v1.0 + 本验证报告 | ✅ |
| §9.2 单文件≤500行 | 最大342行 | ✅ |

---

## 四、L3 集成验证

### 4.1 与现有管线隔离检查

| 检查项 | 结果 |
|:------|:----:|
| 不修改现有评分脚本 | ✅ |
| 不修改现有报告生成脚本 | ✅ |
| 不修改现有数据获取链路 | ✅ |
| 使用独立缓存目录 | ✅ |
| 不修改现有调度触发 | ✅ |

### 4.2 接口契约检查

| 接口 | 设计定义 | 实际实现 | 符合 |
|:-----|:--------|:--------|:----:|
| cninfo API请求格式 | HTTP GET + 参数 | Invoke-RestMethod + 参数匹配 | ✅ |
| 过滤输出JSON Schema | 设计§四.2 | pigeon_output.ps1 Export-PigeonEventJson | ✅ |
| events_db.json Schema | S3预留字段 | actual_return_T1/T3/T5 + excess_return | ✅ |

---

## 五、验证判定

| 检查层 | 等级 | 结果 |
|:------|:----:|:----:|
| L0 基础检查 | 常规 | ✅ PASS (3 WARN — 行数超预估) |
| L1 设计符合性 | 全量 | ✅ PASS (15/15需求覆盖 + 4/4优化落地) |
| L2 红线合规 | 全量 | ✅ PASS |
| L3 集成验证 | 常规 | ✅ PASS |

> 综合判定: ✅ **闸门2 PASS** → 流入阶段⑥ 红枫灰度部署

### 已知WARN项（不阻塞）

| # | WARN | 处置 |
|:--:|:-----|:-----|
| W1 | pigeon_filter.ps1 342行(预估250) | Phase 2考虑拆分为filter_rules.ps1 + filter_engine.ps1 |
| W2 | pigeon_output.ps1 188行(预估100) | 缓存逻辑较多，职能合理，暂不拆分 |
| W3 | pigeon_collector.ps1 321行(预估280) | 轻度超标，核心编排逻辑集中，暂不拆分 |

---

> 新安 · 四层验证报告 · 闸门2 PASS · 2026-05-26
