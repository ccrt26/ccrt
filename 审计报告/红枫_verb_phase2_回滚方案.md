# 动词合规化 Phase 2 — 回滚方案

**日期**: 2026-05-27  
**执行者**: 红枫  
**流水线**: pipeline_20260527_verb_compliance_phase2  

---

## 回滚触发条件

以下任一情况触发回滚：

1. **包装器失效**: Calc-* 包装器输出与 Measure-* 不一致
2. **模块加载失败**: legacy.psm1 导入报错
3. **调用方异常**: 任何活跃脚本因函数未找到报错
4. **评分链路中断**: 每日荐股评分/排序结果异常

## 回滚操作

### 方案A: 就地回滚（推荐，<1分钟）

所有旧函数名保留为包装器。如发现 Measure-* 有问题：

```powershell
# 在调用方临时切回包装器
# 例: run_daily_eval.ps1 中将 Measure-ATR 改回 Calc-ATR
```

包装器已就位，无需修改定义文件。

### 方案B: Git回滚（备选，<2分钟）

```bash
git checkout HEAD~1 -- 代码文件/每日荐股/scripts/modules/
git checkout HEAD~1 -- 代码文件/每日荐股/scripts/run_daily_eval.ps1
git checkout HEAD~1 -- 代码文件/重点股票/run_keystock_analysis.ps1
git checkout HEAD~1 -- 代码文件/信鸽信息采集/pigeon_collector.ps1
```

### 方案C: 完整Git回滚（核选项）

```bash
git revert HEAD  # 创建revert commit，保留历史
```

## 回滚验证

回滚后执行：
1. `Import-Module legacy.psm1 -Force` — 确认无错误
2. `Test-AllDataSources` — 确认所有数据源正常
3. `run_daily_eval.ps1` 试运行 — 确认评分链路完整

## 回滚风险

| 风险 | 等级 | 缓解 |
|:-----|:----:|:-----|
| 包装器本身有bug | 极低 | 包装器为纯委托(1行)，不可能有逻辑错误 |
| 调用方未覆盖 | 低 | grep验证已确认所有调用方已替换 |
| Git冲突 | 极低 | 本次变更仅在当日，无其他并发修改 |

---

pipeline_stage: complete
prepared_by: 红枫
prepared_at: 2026-05-27
