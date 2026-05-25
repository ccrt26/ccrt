# Pipeline保护范围扩展 v1.1 — 设计文档

> 版本 v1.1 | 设计者: 情墨 | 日期 2026-05-25
> pipeline_stage: complete
> finance_confirmed: true
> 代码等级: L1 (基础设施/安全防护)

---

## 一、问题诊断

### 1.1 症状
阿黑在活跃pipeline存在的情况下，于 `模拟交易/` 目录下发起并完成了独立的工作流（commit `3b72dad` 模拟交易架构重设计v2.1），全程未走标准化流程（情墨→新安+旧影→红结→新安→红枫）。

### 1.2 根因分析

| # | 缺口 | 具体表现 |
|:--|:-----|:--------|
| G1 | Check F 保护范围过窄 | 正则 `^代码文件[\\/]` 仅覆盖 `代码文件/`，未覆盖 `模拟交易/` 下的引擎 `.ps1` 文件 |
| G2 | 无活跃pipeline互斥锁 | `pipeline_active.json` 存在但不阻止阿黑启动新的无关工作流并提交代码 |
| G3 | Pipeline与commit无关联校验 | 即使有token，也不验证staged文件是否属于当前pipeline声明的范围 |

### 1.3 影响评估
- **已受影响**：`模拟交易/交易引擎/sim_trading.ps1`、`sim_orchestrator.ps1`、`sim_trading_daily.ps1` 等核心交易引擎代码被绕过pipeline提交
- **潜在风险**：`模拟交易/否决审查/`、`模拟交易/分析/`、`模拟交易/共享模块/` 等同样不受保护
- **严重程度**：L2（涉及交易引擎代码，属于风控敏感路径）

---

## 二、设计方案

### 2.1 G1修复：扩展Check F保护范围

**当前逻辑** (pre-commit-check.ps1 L261-263):
```powershell
$StagedCodeFiles = $StagedFiles | Where-Object {
    $_ -match '^代码文件[\\/]' -or $_ -match '^代码文件/'
}
```

**新逻辑**：增加 `模拟交易/` 下引擎路径的匹配：
```powershell
$CodeFilePatterns = @(
    '^代码文件[\\/]',                          # 现有保护
    '^模拟交易[\\/]sim_orchestrator\.ps1$',     # 根编排器
    '^模拟交易[\\/]交易引擎[\\/]',              # 交易引擎目录
    '^模拟交易[\\/]每日荐股赛道[\\/]交易引擎[\\/]',  # 赛道引擎
    '^模拟交易[\\/]共享模块[\\/]',              # 共享模块
    '^模拟交易[\\/]否决审查[\\/]',              # 否决审查脚本
    '^模拟交易[\\/]分析[\\/]',                  # 分析脚本
    '^模拟交易[\\/]展示[\\/]',                  # 展示脚本
    '^模拟交易[\\/]工具[\\/]'                   # 工具脚本
)
$StagedCodeFiles = $StagedFiles | Where-Object {
    $f = $_ -replace '\\', '/'
    foreach ($pat in $CodeFilePatterns) {
        if ($f -match $pat) { return $true }
    }
    return $false
}
```

**排除范围（不保护）**：`模拟交易/` 下的纯数据/记录目录：
- `交易决策/` — 交易指令记录
- `持仓记录/` — 持仓快照
- `每日快照/` — 日终快照
- `绩效报告/` — 绩效输出
- `日志/` — 运行日志
- `周报/` — 周度报告
- `架构设计/` — 设计文档
- `*.json` 配置文件（`sim_config.json`等）
- `*.md` 文档文件

### 2.2 G2修复：Pipeline token增加 `files_scope` 字段

**Pipeline token schema 变更** (pipeline_engine.ps1):

新增字段 `files_scope`：启动pipeline时声明本次任务涉及的文件/目录范围。

```json
{
  "files_scope": [
    "模拟交易/交易引擎/",
    "模拟交易/sim_orchestrator.ps1",
    ".github/workflows/sim_trading.yml"
  ]
}
```

**启动时** (`-Start`)：增加 `-Scope` 参数，接受逗号分隔的路径列表。
**Advance时** (`-Advance`)：可更新 scope（如红结实现时发现需要修改额外文件）。

### 2.3 G3修复：Check F校验staged文件 ∈ pipeline scope

**Check F 新增逻辑**：当pipeline token存在且 `active=true` 时：
1. 检查 `files_scope` 字段是否存在且非空
2. 遍历所有 staged code files，逐一验证是否匹配 scope 中的至少一个前缀
3. 不匹配的文件 → BLOCK，提示"超出pipeline声明范围"

```powershell
# New F3 check: scope validation
if ($PipelineValid -and $token.files_scope) {
    $outOfScope = @()
    foreach ($cf in $StagedCodeFiles) {
        $inScope = $false
        foreach ($scope in $token.files_scope) {
            if ($cf -match [regex]::Escape($scope)) {
                $inScope = $true; break
            }
        }
        if (-not $inScope) { $outOfScope += $cf }
    }
    if ($outOfScope.Count -gt 0) {
        Write-Log "BLOCK" "F3 BLOCK: Files outside pipeline scope:"
        foreach ($f in $outOfScope) {
            Write-Log "BLOCK" "  $f (pipeline scope: $($token.files_scope -join ', '))"
        }
        $script:HasError = $true
    }
}
```

### 2.4 向后兼容

- **旧token无 `files_scope`**：若token无此字段 → 降级为仅检查token存在（当前行为），WARN提示补充scope
- **M类操作不受影响**：`.claude/` 目录下的文件不触发Check F，阿黑正常执行M类元操作
- **空scope**：如果token有 `files_scope` 但为空数组 → 视为声明了"不涉及代码文件"，任何代码文件staged均BLOCK

---

## 三、影响文件

| 文件 | 变更类型 | 等级 | 行数估算 |
|:-----|:--------|:----:|:-------|
| `.claude/hooks/pre-commit-check.ps1` | 修改 — Check F扩展+G3校验 | L1 | +40行 |
| `代码文件/监督机制/pipeline_engine.ps1` | 修改 — token schema + Scope参数 | L1 | +25行 |
| `代码文件/监督机制/pipeline_token.ps1` | 修改 — -Start增加-Scope参数透传 | L1 | +10行 |

总计: 3文件, ~75行新增。

---

## 四、代码等级判定

| 模块 | 等级 | 理由 |
|:-----|:----:|:-----|
| pre-commit-check.ps1 | L1 | 安全基础设施，影响所有提交流程 |
| pipeline_engine.ps1 | L1 | 流程引擎，影响所有工程变更 |
| pipeline_token.ps1 | L1 | 流程令牌入口 |

---

## 五、风险与权衡

| 决策 | 替代方案 | 选择理由 |
|:-----|:--------|:--------|
| 白名单路径匹配 | 全量匹配所有 `.ps1` | 白名单更精确，避免误拦数据目录下的辅助脚本 |
| files_scope在token中 | 从commit message推断 | token声明式更可靠，不依赖人工写对commit message |
| scope不匹配=BLOCK而非WARN | WARN放行 | 这是修复的核心——不能放行 |

---

## 六、验证计划

1. **单元测试**：手动创建pipeline token，staging scope内/外文件，验证BLOCK/PASS行为
2. **回归测试**：无pipeline时staging代码文件 → 应BLOCK（现有行为不变）
3. **边界测试**：token无files_scope字段、空scope、scope含通配符
4. **M类不受影响**：staging仅 `.claude/` 文件 → 应PASS

---

## 七、需求→代码核对清单

- [ ] Check F 保护模式扩展至 模拟交易/ 引擎路径
- [ ] Pipeline token schema 增加 files_scope 字段
- [ ] pipeline_engine.ps1 -Start 支持 -Scope 参数
- [ ] pipeline_token.ps1 透传 -Scope 参数
- [ ] Check F 新增 F3: staged文件 ∈ pipeline scope 校验
- [ ] 旧token无files_scope时降级兼容（WARN不BLOCK）
- [ ] 数据目录(交易决策/持仓记录/日志等)不触发保护
- [ ] `.claude/` M类操作不受影响
- [ ] pre-commit hook 自检通过（Check A-E 全部PASS）
- [ ] 代码等级标注完整（L1）
- [ ] 单文件行数 ≤500

> 情墨签字：______ | 腰子签字：n/a (纯工程基础设施)
