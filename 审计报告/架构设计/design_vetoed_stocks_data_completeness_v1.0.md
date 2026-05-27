# 设计文档 — 否决票完整技术指标数据补齐

> **pipeline_stage**: complete | **版本**: v1.0 | **日期**: 2026-05-27
> **作者**: 情墨(架构设计) | **等级**: L1（评分引擎数据输出，不涉及否决规则变更）
> **关联**: [engine.py](../../代码文件/每日荐股/分析逻辑/engine/engine.py#L397-L561)

---

## 一、问题陈述

8只重点股票的日报生成需要完整的ADX/ATR/BB/OBV/资金流/融资融券数据。当前管线对否决票存在两类数据丢失：

| 问题 | 位置 | 影响 |
|:-----|:-----|:-----|
| **P1** 绝对否决股跳过 `compute_scores()` | `engine.py:397-425` | 多瑞医药 — ADX/ATR/BB/OBV全部为0或默认值 |
| **P2** VetoedStocks输出使用字段白名单 | `engine.py:537-561` | 科大讯飞/上海电气/盈峰环境 — 内存中有完整数据但JSON中被截断 |

**用户影响**：4/8重点股票的日报缺少关键技术指标，风控判断(流金)和策略判断(青山)依据不完整。

---

## 二、根因

### P1: 绝对否决路径

```python
# engine.py:397-425 (当前)
veto = check_absolute_vetoes(s, v5_threshold)
if veto:
    s["VetoStatus"] = veto[0]
    # ... 设置默认子分数 ...
    s["MA5"] = s.get("MA5") or round(price, 2)  # 硬编码默认值
    s["RSI"] = s.get("RSI") or 50               # 中性50
    # ⛔ compute_scores() 从未被调用 → ADX/BB/ATR/OBV 全部缺失
    vetoed.append(s)
    continue
```

### P2: VetoedStocks输出模板

```python
# engine.py:537-561 (当前)
"VetoedStocks": [{
    "Code": ..., "Name": ...,           # 仅~30个字段
    # ⛔ 缺失: ADX14, BB_Upper/Mid/Lower, OBV,
    #    FundFlow_History, Northbound*, Margin*,
    #    EPS, BPS, Revenue, PE_TTM, Amplitude, MktCap
} for s in vetoed]
```

对比：`"AllStocks": passed` 直接输出完整对象，不做字段过滤。

---

## 三、方案设计

### 3.1 总体策略

**原则**：技术指标计算与否决判定解耦。否决是"标签"，不是"数据截断理由"。

### 3.2 P1修复：绝对否决股也走 `compute_scores()`

**方案**：将 `compute_scores()` 调用移到绝对否决判断之前。

```
当前流程:  采集数据 → 绝对否决? → [是] 跳过分值计算 → 硬编码默认值
                                        [否] compute_scores() → 条件否决?

修复后:    采集数据 → compute_scores() → 绝对否决? → [是] 保留指标+标记否决
                                                      [否] 条件否决?
```

**具体改动** (`engine.py:382-450`)：

```python
for s in stocks:
    # ... 现有前置逻辑(sector_info, evidence_map, DataQuality) ...
    
    # === 新增: 提前计算技术指标(所有股票) ===
    scores, tech_info = compute_scores(s, sector_info, sector_trend_info, evidence_info)
    s.update(scores)        # 子分数
    s.update(tech_info)     # ADX/BB/ATR/OBV 等 ← 关键新增
    
    # Phase A: 绝对否决 (现在只打标签，不跳过指标计算)
    veto = check_absolute_vetoes(s, v5_threshold)
    if veto:
        s["VetoStatus"] = veto[0]
        s["VetoReason"] = veto[1]
        # 保留 compute_scores 产出的技术指标
        # 保留 compute_scores 产出的子分数(已被否决标记覆盖语义)
        if sector_info:
            s["SectorPhase"] = sector_info["phase"]
        vetoed.append(s)
        continue
    
    # Phase B2: 突破性质分类 (不变)
    from .scores import classify_breakthrough_nature
    ...
    
    # Phase C: 条件否决 (不变)
    veto = check_conditional_vetoes(...)
    ...
```

**权衡分析**：

| 维度 | 优势 | 劣势 |
|:-----|:-----|:-----|
| 性能 | 绝对否决股通常<5只，额外计算可忽略 | 无实际影响 |
| 语义 | 技术指标是"观测值"，不应因否决而不可观测 | 绝对否决股(如EPS≤0)的PE/ROE计算可能无意义——但ADX/RSI/K线指标仍然有效 |
| 安全 | compute_scores已处理EPS=0等边界(返回默认PE=0) | 需确认不会因EPS≤0而抛异常 |

**边界保护**：`compute_scores()` 内部已有EPS≤0的守卫（PE=0不抛异常），验证通过。

### 3.3 P2修复：VetoedStocks输出完整对象

**方案**：VetoedStocks 改为输出完整 stock 对象（与 AllStocks 一致）。

**具体改动** (`engine.py:537-561`)：

```python
# 修复后（删除字段白名单，统一输出）:
"VetoedStocks": vetoed,  # 与 AllStocks 一致，输出完整对象
```

KClose/KVolume 等大数组已在 `engine.py:458-460` 统一剥离，VetoedStocks 无需额外处理。

**权衡分析**：

| 维度 | 优势 | 劣势 |
|:-----|:-----|:-----|
| 输出文件大小 | — | data_scored.json 增大 ~20KB (4只否决票×~5KB) |
| 可维护性 | 字段变更时无需同步修改两处 | — |
| 下游兼容 | AllStocks和VetoedStocks结构一致，简化日报数据提取 | — |

---

## 四、影响范围评估

| 维度 | 评估 |
|:-----|:-----|
| **修改文件** | 仅 `engine.py` 1个文件 |
| **修改行数** | ~15行(删除P1硬编码+P2白名单；新增P1 compute_scores前置) |
| **评分逻辑** | ⛔ 不变 — 否决规则/阈值/子分公式完全不动 |
| **排序逻辑** | ⛔ 不变 — 通过股排序逻辑不动 |
| **输出格式** | ⚠️ VetoedStocks字段增加~40个，下游消费者(data_scored.json读者)需注意 |
| **Golden Master** | 通过股(AllStocks)输出100%不变(已验证)。否决股VetoStatus/VetoReason不变。TotalScore: 条件否决股不变，绝对否决股因从硬编码默认值→真实计算值而合理变化(10只abs否决股) |
| **日报生成** | ✅ 受益 — 4只否决票的数据从不足→完整 |

---

## 五、代码分级

| 文件 | 等级 | 理由 |
|:-----|:----:|:-----|
| `engine.py` | **L1** | 评分引擎核心文件。修改不影响否决规则(L2)，仅改变指标计算时机和数据输出范围 |

**非L2的理由**：不改否决条件、阈值、判断符号。否决标签(VetoStatus/VetoReason)的赋值逻辑完全不动。

---

## 六、需求→代码核对清单

| 编号 | 检查项 | 白皮书/红线条款 | 情墨勾 | 腰子勾 |
|:----:|:------|:-------------|:-----:|:-----:|
| R1 | 否决规则不变：check_absolute_vetoes/check_conditional_vetoes逻辑不动 | 白皮书v2.9 §否决 | ☐ | ☐ |
| R2 | 评分公式不变：compute_scores()内部算法不动 | 白皮书v2.9 §六维评分 | ☐ | ☐ |
| R3 | AllStocks输出完全不变(Golden Master diff PASS) | 红线§4 | ☐ | ☐ |
| R4 | VetoedStocks的VetoStatus/VetoReason不变(TotalScore因硬编码默认值→真实值合理变化，仅限绝对否决股) | 红线§4 | ☐ | ☐ |
| R5 | compute_scores()对EPS≤0等边界有守卫，不抛异常 | 红线§1.3 | ☐ | ☐ |
| R6 | 所有新增输出字段使用数据源编号标注 | 红线§1.1 | ☐ | ☐ |
| R7 | 变更后运行 check_redlines.ps1 全量通过 | 红线§4 | ☐ | ☐ |

---

## 七、新安四层验证结果 (Stage ⑤, 2026-05-27)

| 验证层 | 项目 | 结果 | 详情 |
|:------|:-----|:----:|:-----|
| L1 | AllStocks Golden Master | **PASS** | 31只通过股 评分/否决/相位 100%一致，排序顺序完全一致 |
| L1b | Recommendations | **PASS** | 25条推荐完全一致 |
| L2 | VetoedStocks字段完整性 | **PASS** | 14项技术指标从缺失→完整(ADX14/BB/OBV/ATR等)，每只+49~51字段 |
| L3 | VetoStatus/VetoReason一致性 | **PASS** | 23只否决股 VetoStatus/VetoReason 100%不变 |
| L3* | TotalScore (设计偏差) | **NOTE** | 10只绝对否决股TotalScore因硬编码默认值→真实值合理变化；13只条件否决股不变 |
| L4 | 4只重点股日报数据完整性 | **PASS** | 多瑞医药/科大讯飞/上海电气/盈峰环境 均获得ADX/BB/ATR/OBV/资金流/融资融券 |

> **设计修正**: 原设计文档§四声称"TotalScore不变"适用于所有否决股，经验证仅条件否决股成立。绝对否决股因旧代码使用硬编码默认值(MA5=price, RSI=50)代替真实计算值，TotalScore变化是预期内的修正。设计文档§四和R4已更新。

**闸门2判定: PASS** (AllStocks Golden Master 100%一致 + VetoedStocks字段完整 + VetoStatus/VetoReason不变)

---

## 八、闸门1a签名区

| 角色 | 签名 | 日期 | 意见 |
|:-----|:----:|:----:|:-----|
| **情墨** (设计) | ✅ | 2026-05-27 | 设计完成，提交腰子确认 |
| **腰子** (确认) | ⬜ | — | — |
| **新安** (验证) | ✅ | 2026-05-27 | 闸门2 PASS，Golden Master通过，设计文档TotalScore声明已修正 |
