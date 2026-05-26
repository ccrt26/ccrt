# 每日荐股P0-P1移植 — 红枫灰度部署记录

> **执行人**：红枫 | **日期**：2026-05-26 | **版本**：v1.0
> **关联设计**：design_daily_pick_p0p1_transplant_v1.0.md
> **关联验证**：verification_daily_pick_p0p1_stage4_20260526.md
> **闸门3前置**：G1=PASS, G2=CONDITIONAL_PASS

---

## 1. 部署环境

| 项目 | 值 |
|:-----|:---|
| Python | 3.13.13 |
| 引擎路径 | 代码文件/每日荐股/分析逻辑/engine/ |
| 数据文件 | data_full.json (1.7MB, 2026-05-25) |
| 部署时间 | 2026-05-26 08:15 UTC+8 |
| 变更等级 | L2 (风控/否决) |

## 2. 变更清单

| 文件 | 变更 | 行数 |
|:-----|:-----|:---:|
| engine/__init__.py | +INDUSTRY_BENCHMARK常量 | +18 |
| engine/scores.py | +P0a资金趋势 +P0b突破函数 +P1a锚定 | +79 |
| engine/veto.py | +C8突破性质降权/加分 | +14 |
| engine/engine.py | +Phase B2调用 +历史字段 | +51/-0 |

## 3. 灰度执行

### 3.1 前置操作
- [x] 备份 data_scored.json → data_scored_v2.9_backup.json
- [x] 备份 score_history.jsonl → score_history_v2.9_backup.jsonl

### 3.2 引擎运行结果
- 处理: 72只股票
- 通过: 41只 (56.9%)
- 否决: 31只
- 输出: data_scored.json 已更新
- 历史: 0条新记录（全部重复，评分未变化）

### 3.3 Golden Master Diff

| 维度 | 旧版(v2.9) | 新版(P0-P1) | 差异 | 判定 |
|:-----|:---------:|:----------:|:----:|:--:|
| 否决列表 | 31只 | 31只 | **0** | PASS |
| 通过评分 | 41只 | 41只 | **0** | PASS |
| Top10排序 | 41只 | 41只 | **0** | PASS |
| C8突破检测 | N/A | 4只pure_momentum | 新增 | PASS |
| C8扣分/加分 | N/A | 0只（4只均被否决） | 0 | PASS |
| IndustryBenchmark | N/A | 41/72只 | 新增 | PASS |

### 3.4 单元测试结果
- [x] INDUSTRY_BENCHMARK 31行业加载
- [x] detect_breakthrough 三场景（52周新高/MA20突破/无突破）
- [x] classify_breakthrough_nature 四分类（quality_momentum/fund_driven/pure_momentum/None）
- [x] C8 veto 三场景（pure-10/fund-3/quality+3/无突破不变）
- [x] 否决列表 V0-V7 零回归

## 4. 回滚方案

### 触发条件
1. 次日荐股报告评分异常（>10只股票评分变化>5分）
2. C8导致大量误否决（通过率<30%）
3. 报告格式损坏（gen_daily_html.ps1解析失败）

### 回滚步骤
```bash
# 步骤1: 恢复v2.9代码 (git revert)
cd 代码文件/每日荐股/分析逻辑/engine/
git checkout HEAD~1 -- __init__.py engine.py scores.py veto.py

# 步骤2: 恢复v2.9输出文件
cd 代码文件/数据/
cp data_scored_v2.9_backup.json data_scored.json
cp score_history_v2.9_backup.jsonl score_history.jsonl

# 步骤3: 重新生成报告
# 使用 gen_daily_html.ps1 重新生成
```

### RTO估算
- 代码回滚: <1分钟
- 数据恢复: <1分钟
- 报告重新生成: <5分钟
- **总RTO: <10分钟**

## 5. 监控要点（灰度期 ≥20交易日）

| 监控指标 | 正常范围 | 告警触发 | 级别 |
|:---------|:------:|:------:|:--:|
| 通过率 | 50-70% | <40% 或 >80% | P1 |
| C8触发率 | <15% | >25% | P2 |
| pure_momentum占比 | <10% | >20% | P2 |
| 评分标准差(通过股) | 与v2.9一致 | 变化>5% | P2 |
| 否决列表一致性 | V0-V7不变 | 任何V0-V7否决变化 | P0 |
| score_history.jsonl写入 | 无异常 | 写入失败/格式错误 | P1 |

## 6. 部署决策

**闸门3判定**: ✅ **PASS — 灰度上线**

理由：
- Golden Master diff 四项完全一致
- V0-V7否决零回归
- C8新增逻辑不影响通过股评分（当前数据集）
- 降级路径安全（新字段默认0）
- 回滚方案就绪，RTO <10分钟
- 备份文件完整

**灰度期**: 即日起 ≥20个交易日
**C8参数**: [L2实验性]，灰度期后流金评估IC→固化为正式阈值

---

> **红枫签字**：环境健康，灰度执行成功，Golden Master diff零回归，回滚方案就绪。
> **下一步**：腰子+青山后评估 → 闸门3最终确认 → 关闭管线
