# 架构设计: pipeline_token.ps1 v1.1 — 阶段顺序校验 + E类检测 + 实时写入
> 设计人: 情墨 | 日期: 2026-05-25 | 触发: 旧影审计 FAIL-01~06

## 一、新增模块

### 1.1 Assert-StageOrder
- 位置: `pipeline_token.ps1` 新增函数
- 功能: `-Advance` 时校验新阶段 ≥ 当前阶段 (禁止回退)
- 输入: current stage (int), target stage (int)
- 输出: PASS (继续) / FAIL (exit 1 + 错误信息)
- 触发: 所有 -Advance 调用

### 1.2 Assert-DesignDocExists
- 位置: `pipeline_token.ps1` 新增函数
- 功能: Stage 2 (新安+旧影审查) 推进前检查情墨设计文档是否存在
- 检查路径: `审计报告/架构设计/design_*.md`
- 输出: PASS (至少1个匹配) / FAIL (exit 1)

### 1.3 Write-PipelineHistory
- 位置: `pipeline_token.ps1` 新增函数 (替代当前 -Complete 中的批量写入)
- 功能: 每阶段推进时实时写入 `pipeline_history/` JSON
- 不再等到 -Complete 才归档

## 二、变更范围

| 函数 | 改动类型 | 说明 |
|:-----|:--------|:-----|
| Assert-StageOrder | 新增 | 阶段顺序校验 |
| Assert-DesignDocExists | 新增 | 设计文档存在性检查 |
| Write-PipelineHistory | 新增 | 实时写入历史 |
| -Advance 逻辑 | 修改 | 集成 Assert-StageOrder + Write-PipelineHistory |
| -Complete 逻辑 | 修改 | 实时写入已在 -Advance 完成，仅标记完成 |

## 三、数据流
```
-Advance -To "新安+旧影"
  ↓
Assert-StageOrder(current=1, target=2) → PASS
  ↓
Assert-DesignDocExists → PASS (design_*.md exists)
  ↓
Write-PipelineHistory → pipeline_history/pipeline_{ts}.json (即时)
  ↓
Update pipeline_active.json → stage=2, executor="新安+旧影"
```

## 四、接口契约 (不变)
- CLI 接口: 无变化 (-Start/-Advance/-Complete/-Status 参数不变)
- TOKEN_FILE 路径: 不变
- HISTORY_DIR 路径: 不变
- $STAGES 数组: 不变

## 五、需求→代码核对清单
- [ ] Assert-StageOrder 函数 → pipeline_token.ps1
- [ ] Assert-DesignDocExists 函数 → pipeline_token.ps1
- [ ] Write-PipelineHistory 函数 → pipeline_token.ps1
- [ ] -Advance 修改 (集成三函数) → pipeline_token.ps1
- [ ] -Complete 修改 (简化为仅标记完成) → pipeline_token.ps1

> 情墨签字: 情墨 ✅ | 代码等级: L1 (策略/基础设施)
