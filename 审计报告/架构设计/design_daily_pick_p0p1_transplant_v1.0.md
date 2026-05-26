# 每日荐股P0-P1移植 — 架构设计

> **设计人**：情墨 | **日期**：2026-05-26 | **版本**：v1.0  
> pipeline_stage: complete | **L级**：L2（涉及评分引擎 L2 风控/否决逻辑）  
> finance_confirmed: true

---

## 1. 需求摘要

将深度分析的五层优化中适用于每日批量评分的三项移植到 `scoring_engine`：

| # | 优化项 | 实现方式 | 复杂度 |
|:--|:------|:--------|:-----:|
| P0a | 资金结构维度(简化) | S_Money增加连续N日主力趋势加分 | 低 |
| P0b | 突破性质分类过滤器 | 新增C8条件否决：纯动量突破降权/否决 | 中 |
| P1a | 行业锚定参照展示 | 报告输出层增加行业基准分对比 | 低 |

---

## 2. 架构总览

```
数据层 (data_full.json)
  │  FundMainNet (当日) → P0a需要扩展到3-5日
  ↓
计算层 (scores.py + veto.py)
  │  P0a: S_Money 连续N日主力趋势 → +2~+4 分
  │  P0b: classify_breakthrough() → C8条件否决
  ↓
否决层 (veto.py)
  │  C8: 纯动量突破 → 降权(-10) 或 排除(总分为0)
  ↓
展示层 (data_scored.json → gen_daily_html.ps1)
  │  P1a: IndustryBenchmark 字段 → 报告展示
  └────────────────────────────────────────────
```

**关键约束**：
- ⛔ 不改变现有评分公式的权重分配
- ⛔ 不改变现有V0-V7否决逻辑
- ✅ P0a作为S_Money加分项（上限20分不变）
- ✅ P0b作为新增C8条件否决（非绝对否决）

---

## 3. 模块设计

### 3.1 P0a — 资金结构维度 [L1]

**目标文件**：`engine/scores.py` §S_Money 计算段落

**现有逻辑**：
```python
if fund_net > 0: money += 2
elif fund_net < -10000000: money -= 2
```

**新增逻辑**（在现有fund_net判断之后追加）：

```python
# P0a: 连续N日主力趋势 (需要 FundMainNet_3d, FundMainNet_5d)
fund_net_3d = s.get("FundMainNet_3d", 0) or 0   # 近3日累计
fund_net_5d = s.get("FundMainNet_5d", 0) or 0   # 近5日累计
fund_days_pos = s.get("FundMainNet_PosDays", 0) or 0  # 近5日中净流入天数

if fund_days_pos >= 5 and fund_net_5d > 0:
    money += 4   # 连续5日主力净流入 → 强进场
elif fund_days_pos >= 3 and fund_net_3d > 0:
    money += 2   # 连续3日主力净流入 → 进场
elif fund_days_pos <= 1 and fund_net_5d < 0:
    money -= 2   # 近5日主力以流出为主 → 警惕
```

**数据管线变更**（`batch_data_collector.ps1` 或 `fundflow.ps1`）：
- 新增采集字段：`FundMainNet_3d`, `FundMainNet_5d`, `FundMainNet_PosDays`
- 数据源：[9]东方财富个股资金流向，通过逐日累计计算

### 3.2 P0b — 突破性质分类 [L2]

**目标文件**：
- `engine/scores.py`：新增 `classify_breakthrough_nature()` 函数
- `engine/veto.py`：新增 C8 条件否决

**突破检测**（复用现有 `has_breakout` 逻辑）：

```python
def detect_breakthrough(s):
    """检测是否发生放量突破。返回 (is_breakthrough, breakout_strength)"""
    chg_pct = s.get("ChangePct", 0) or 0
    vol_ratio = s.get("VolRatio", 1) or 1
    price = s.get("Price", 0) or 0
    closes = s.get("KClose", [])
    
    # 条件1：放量突破关键位（52周新高或MA120以上+首次突破）
    is_52w_high = len(closes) >= 250 and price >= max(closes[-250:])
    above_ma120 = price > s.get("MA20", 0) * 1.05  # 简化：用MA20替代
    
    # 条件2：量价确认
    volume_surge = vol_ratio > 1.5 and chg_pct > 3
    
    if volume_surge and (is_52w_high or (above_ma120 and chg_pct > 5)):
        strength = 2 if is_52w_high else 1
        return True, strength
    return False, 0
```

**分类逻辑**：

```python
def classify_breakthrough_nature(s, scores):
    """
    返回: "quality_momentum" | "fund_driven" | "pure_momentum" | None
    
    质量+动量共振: S_Fund ≥ 8/15 且 资金正向
    资金驱动:      S_Fund < 8/15 且 资金正向
    纯动量:        S_Fund < 8/15 且 资金负向
    """
    is_bt, strength = detect_breakthrough(s)
    if not is_bt:
        return None
    
    fund_quality = scores.get("S_Fund", 0)  # 基本面评分 (0-15)
    fund_net = s.get("FundMainNet", 0) or 0
    fund_net_3d = s.get("FundMainNet_3d", 0) or 0
    
    fund_positive = fund_net > 0 and fund_net_3d > 0
    quality_pass = fund_quality >= 8  # 基本面过半
    
    if quality_pass and fund_positive:
        return "quality_momentum"
    elif not quality_pass and fund_positive:
        return "fund_driven"
    else:
        return "pure_momentum"
```

**C8条件否决**（`engine/veto.py`）：

```python
# C8: 纯动量突破 — 降权处理
breakthrough_type = s.get("_BreakthroughType")
if breakthrough_type == "pure_momentum":
    # 纯动量突破：总分-10（不直接否决，但大幅降权）
    scores["TotalScore"] = max(0, scores["TotalScore"] - 10)
    scores["_C8_Penalty"] = -10
elif breakthrough_type == "fund_driven":
    # 资金驱动突破：轻微降权
    scores["TotalScore"] = max(0, scores["TotalScore"] - 3)
    scores["_C8_Penalty"] = -3
elif breakthrough_type == "quality_momentum":
    # 质量+动量共振：加分
    scores["TotalScore"] = min(100, scores["TotalScore"] + 3)
    scores["_C8_Bonus"] = +3
```

**调用点**（`engine/engine.py` 主流程）：
- `compute_scores` → `classify_breakthrough_nature` → C8否决 → 最终排名
- 在 `check_conditional_vetoes` 之后、最终排序之前执行

### 3.3 P1a — 行业锚定参照 [L0]

**目标文件**：
- `engine/__init__.py`：新增 `INDUSTRY_BENCHMARK` 常量
- `gen_daily_html.ps1` 或报告生成：展示锚定对比

**常量定义**：

```python
# 申万一级行业基准分 (0-10)，来自腰子-知识库/05-板块轮动 §十
INDUSTRY_BENCHMARK = {
    "食品饮料": 7.0, "电子": 6.5, "医药生物": 6.0,
    "电力设备": 6.0, "计算机": 5.5, "家用电器": 5.5,
    "汽车": 5.5, "通信": 5.5, "国防军工": 5.5,
    "有色金属": 5.0, "机械设备": 5.0, "基础化工": 5.0,
    "非银金融": 5.0, "美容护理": 5.0,
    "交通运输": 4.5, "公用事业": 4.5, "农林牧渔": 4.5,
    "轻工制造": 4.5, "纺织服饰": 4.5, "建筑材料": 4.5,
    "建筑装饰": 4.5, "传媒": 4.5,
    "钢铁": 4.0, "煤炭": 4.0, "石油石化": 4.0,
    "银行": 4.0, "房地产": 4.0, "商贸零售": 4.0,
    "社会服务": 4.0, "环保": 4.0,
    "综合": 3.5,
}
```

**在 `compute_scores` 中追加**：
```python
benchmark = INDUSTRY_BENCHMARK.get(industry, 5.0)
s["IndustryBenchmark"] = benchmark
```

报告展示层（gen_daily_html.ps1）在行业评分旁显示 `(基准X.X)`。

---

## 4. 数据流

```
① batch_data_collector.ps1 (增强)
   新增采集: FundMainNet_3d, FundMainNet_5d, FundMainNet_PosDays → data_full.json
     ↓
② compute_scores (scores.py)
   P0a: S_Money 使用新字段加分
   P0b: 调用 classify_breakthrough_nature()
     ↓
③ check_conditional_vetoes (veto.py)
   新增 C8: 纯动量突破降权
     ↓
④ main → 输出 data_scored.json
   新增字段: IndustryBenchmark, _BreakthroughType, _C8_Penalty/_Bonus
     ↓
⑤ gen_daily_html.ps1
   P1a: 展示行业基准对比
```

---

## 5. 接口契约

| 接口 | 方向 | 变更 |
|:-----|:---:|:-----|
| batch_data_collector → data_full.json | 扩展 | 新增3个资金流字段 |
| data_full.json → scores.py | 扩展 | S_Money读取新字段 |
| scores.py → veto.py | 新增 | classify_breakthrough_nature → C8 |
| scores.py → data_scored.json | 扩展 | 新增_BreakthroughType等 |
| data_scored.json → HTML报告 | 扩展 | 新增IndustryBenchmark展示 |

---

## 6. 影响评估

| 受影响文件 | 类型 | 操作 | 风险 |
|:----------|:----|:----|:--:|
| `engine/scores.py` | L2 | 修改S_Money+新增classify_breakthrough | **高** — L2评分逻辑 |
| `engine/veto.py` | L2 | 新增C8条件否决 | **高** — L2否决逻辑 |
| `engine/__init__.py` | L1 | 新增INDUSTRY_BENCHMARK常量 | 低 |
| `engine/engine.py` | L1 | 主流程调用classify_breakthrough | 中 |
| `batch_data_collector.ps1` | L0 | 新增3个资金流字段采集 | 低 |
| `data_full.json schema` | L0 | 新增字段 | 低 |
| `gen_daily_html.ps1` | L1 | 展示行业锚定 | 低 |

---

## 7. Golden Master diff要求

> ⛔ L2模块变更，必须Golden Master diff验证。
> 验证范围：评分/排序/否决/相位 四项。

| 验证项 | 对比基准 | 预期差异 |
|:------|:--------|:--------|
| 评分 | v2.9 历史输出 | 个别股票因C8降权/加分 ±3~10分 |
| 排序 | v2.9 历史输出 | 纯动量突破股排名下降，质量+动量突破股上升 |
| 否决 | v2.9 历史输出 | V0-V7不变，新增C8降权(非否决) |
| 相位 | v2.9 历史输出 | 完全一致（相位逻辑不变） |

---

## 8. 需求→实现核对清单

| # | 需求 | 实现文件 | 验收标准 | 情墨 | 腰子 |
|:--|:-----|:--------|:--------|:--:|:--:|
| 1 | P0a连续N日主力趋势 | scores.py + batch_data_collector.ps1 | S_Money含3日/5日主力趋势 | ☐ | ☐ |
| 2 | P0b突破检测函数 | scores.py detect_breakthrough() | 正确识别放量突破52周新高 | ☐ | ☐ |
| 3 | P0b突破性质分类 | scores.py classify_breakthrough_nature() | 四分类输出正确 | ☐ | ☐ |
| 4 | P0b C8条件否决 | veto.py C8 | 纯动量-10/资金驱动-3/质量共振+3 | ☐ | ☐ |
| 5 | P1a行业基准常量 | __init__.py INDUSTRY_BENCHMARK | 31行业全覆盖 | ☐ | ☐ |
| 6 | P1a报告展示 | gen_daily_html.ps1 | 行业评分旁显示基准对比 | ☐ | ☐ |
| 7 | Golden Master diff | 新安执行 | 评分/排序/否决/相位 diff可解释 | ☐ | ☐ |

---

> **设计产出**：情墨 | **闸门1a待审**：腰子全团咨询
> **闸门1b待审**：新安+旧影 + 流金逐条红线复核（L2模块强制）
> **流入编码条件**：finance_confirmed=true + gate_1=PASS
