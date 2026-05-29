# Pre-commit Hook 保护机制统一设计 v1.2

> 版本 v1.2 | 设计者: 情墨 | 日期 2026-05-25
> pipeline_stage: complete
> finance_confirmed: true
> 代码等级: L1 (基础设施/安全防护)
> 上层需求: 用户指出3轮补丁仍未根治阿黑跳出流程问题

---

## 一、问题诊断（情墨根因分析）

### 问题1（致命）：gate_1 检查缺失

**现状**：已提交版本（HEAD `35a02d6`）的 pre-commit-check.ps1 F2 校验条件为：
```powershell
$token.active -eq $true -and ($token.executor -eq "红结" -or $token.executor -eq "红枫")
```
**未检查 `gate_1 == "PASS"`**。

**影响**：红结/红枫拿到活跃 token 即可提交代码，即使闸门1未通过（腰子未确认、新安未审查）。这正是"设计完没给金融团队确认就能编码提交"的漏洞。

**工作区已有部分修复**：工作区 diff 显示正添加 `gate_1 -eq "PASS"` 检查 + 分诊式 BLOCK 信息，但尚未提交。

### 问题2（架构腐化）：两套保护机制规则不一致

| 维度 | pre-commit-check.ps1 | write_protection_hook.ps1 |
|:-----|:-----|:-----|
| 位置 | `.claude/hooks/` (M类) | `代码文件/监督机制/` (E类) |
| 触发时机 | git commit | Write/Edit 文件操作 |
| 保护范围 | `代码文件/` + `模拟交易/` 8条路径 | 仅 `代码文件/` |
| executor 白名单 | 红结 + 红枫 (HEAD) | 仅红结 |
| gate_1 检查 | 工作区刚加，未提交 | **无** |
| files_scope 校验 | 有 (v1.1) | **无** |

两套规则不同步 → 绕过一条即可绕过全部。write_protection_hook.ps1 自 v1.0 以来未随 pre-commit 同步升级，处于腐烂状态。

### 问题3（过程缺陷）：3 轮补丁无威胁建模

```
Round 1 (b627916): Check F 初始 — 仅保护 代码文件/
Round 2 (c708781): 扩展至 模拟交易/ + files_scope — Round 1 漏了
Round 3 (35a02d6): BOM修复 + scope修复 — Round 2 有 bug
Round 4 (工作区): 补 gate_1 检查 — Round 1-3 都漏了根因
```

根因：初始设计无威胁建模（未穷举 bypass 向量），每次都是事后发现→打补丁。

---

## 二、威胁建模（5条 bypass 向量 → 5条对策）

| # | 威胁向量 | 攻击面 | 严重度 | 对策 |
|:--|:--------|:------|:-----:|:----|
| T1 | gate_1 != PASS 但 executor=红结 → 直提代码 | pre-commit F2 | B1 | F2 增加 gate_1 == PASS 强制检查 |
| T2 | 修改 write_protection_hook.ps1 绕过编辑时阻断 | Write/Edit hook | B2 | hook 逻辑统一到共享模块，两 hook 交叉校验 |
| T3 | 修改 模拟交易/ 下 .ps1 → pre-commit 未覆盖 | pre-commit F1 | B1 | 已修复(v1.1)，但 write_protection 未同步 |
| T4 | 修改 代码文件/ 下文件 → write_protection 规则过旧放行 | Write/Edit hook | B1 | write_protection 同步升级至与 pre-commit 一致 |
| T5 | pipeline token files_scope 为空 → scope 校验跳过 | pre-commit F3 | B2 | 空 scope + 代码文件 staged → WARN→BLOCK 升级 |

---

## 三、设计方案

### 3.1 核心决策：共享验证模块

创建 `.claude/hooks/shared/pipeline-auth.py` 作为**单一真相源**，两个 hook 均 dot-source 此模块。

```
.claude/hooks/shared/pipeline-auth.py  ← 单一真相源 (M类, ~60行)
    ↑ dot-source                    ↑ dot-source
    │                               │
pre-commit-check.ps1          write_protection_hook.ps1
 (git commit 门禁)             (Write/Edit 实时阻断)
```

**选择理由**：
- 单一真相源：规则只写一次，两 hook 自动同步
- M类位置：`.claude/hooks/shared/` 属于 M类白名单，阿黑可直接维护
- 向后兼容：两个 hook 的行为变化最小化，仅抽离共享逻辑

**替代方案评估**：
- 方案B「废弃 write_protection_hook，只保留 pre-commit」：丢失实时写入阻断（防御纵深降级），不采纳
- 方案C「两个 hook 各自维护，人工同步」：已证明不可靠（当前问题2的根因），不采纳

### 3.2 共享模块接口设计

```powershell
# .claude/hooks/shared/pipeline-auth.py
# 返回 PSCustomObject: { Authorized, Reason, Executor, Gate1, ScopeMatch }

function Test-PipelineAuthorization {
    param(
        [Parameter(Mandatory=$true)]
        [string]$FilePath,              # 被操作的文件路径（相对项目根）

        [Parameter(Mandatory=$false)]
        [string[]]$AdditionalPatterns,  # 调用方可追加保护路径
    )
    # 内部逻辑:
    # 1. 匹配 CodeFilePatterns（完整列表，与 pre-commit F1 一致）
    # 2. 若非保护路径 → Authorized=$true (不拦截)
    # 3. 若是保护路径 → 检查 pipeline token:
    #    a. 文件存在且可解析
    #    b. active == $true
    #    c. executor in (红结, 红枫)
    #    d. gate_1 == PASS
    #    e. 若 files_scope 非空 → 文件在 scope 内
    # 4. 返回结果对象
}
```

**CodeFilePatterns 完整列表**（从此单一维护）：
```powershell
$script:ProtectedPaths = @(
    '^代码文件[\\/]',
    '^模拟交易[\\/]sim_orchestrator\.ps1$',
    '^模拟交易[\\/]交易引擎[\\/]',
    '^模拟交易[\\/]每日荐股赛道[\\/]交易引擎[\\/]',
    '^模拟交易[\\/]共享模块[\\/]',
    '^模拟交易[\\/]否决审查[\\/]',
    '^模拟交易[\\/]分析[\\/]',
    '^模拟交易[\\/]展示[\\/]',
    '^模拟交易[\\/]工具[\\/]'
)
```

### 3.3 各 hook 变更

#### 3.3a pre-commit-check.ps1（修改 ~30行）

```
变更点:
1. L9 顶部增加: . "$PSScriptRoot\shared\pipeline-auth.ps1"
2. Check F (L261-348) 替换为调用 Test-PipelineAuthorization:
   - L262-279 ($CodeFilePatterns + 匹配循环) → 删除，由共享模块负责
   - L286-308 (F2 token 校验) → 替换为调用共享函数，解析返回结果
   - L312-336 (F3 scope 校验) → 移至共享模块
   - L339-344 (F4 BLOCK) → 保留，基于共享函数返回的 Authorized 判断
3. 行数变化: 367 → ~290 (减少 ~77行)
```

#### 3.3b write_protection_hook.ps1（重写 ~40行）

```
变更点:
1. L28-33 (仅检查 代码文件/ 目录) → 替换为调用 Test-PipelineAuthorization
2. L55-70 (token 校验，仅红结) → 删除，由共享模块负责
3. L72-78 (日志) → 保留，基于共享函数返回结果
4. L81-98 (阻断消息) → 保留
5. 行数变化: 99 → ~60 (减少 ~39行)
```

### 3.4 T5修复：空 scope 行为升级

当前行为：token 有 `files_scope` 但为空数组 → WARN 跳过 scope 校验。
新行为：token 有 `files_scope` 但为空数组 → **BLOCK**（声明了 scope 但为空 = 声明不涉及代码文件，则任何代码文件 staged 均违规）。

---

## 四、影响文件

| 文件 | 变更类型 | 等级 | 行数 |
|:-----|:--------|:----:|:---:|
| `.claude/hooks/shared/pipeline-auth.py` | **新增** — 共享验证模块 | L1 | ~60 |
| `.claude/hooks/pre-commit-check.py` | 修改 — 抽离F2/F3至共享模块 | L1 | 367→~290 |
| `代码文件/监督机制/write_protection_hook.py` | 修改 — 同步升级至统一规则 | L1 | 99→~60 |

总计: 3文件, 净减少 ~116行（新增60 + 修改-77 + 修改-39 = -56行 + 新增60 = 净+4行）。

---

## 五、代码等级判定

| 模块 | 等级 | 理由 |
|:-----|:----:|:-----|
| pipeline-auth.ps1 | **L1** | 安全基础设施 — 所有代码文件写操作必经此验证，影响全项目提交流程 |
| pre-commit-check.ps1 | L1 | 同级别，不变 |
| write_protection_hook.ps1 | L1 | 升级至 L1 — 实时写阻断 + 新保护范围 |

> 三个模块均不涉及评分/交易/风控逻辑 → 非L2。但作为安全基础设施 → L1（情墨复审+新安全量）。

---

## 六、风险与权衡

| 决策 | 风险 | 缓解 |
|:-----|:-----|:-----|
| 共享模块放 M类路径 | 阿黑可修改共享模块绕过保护 | 防御纵深: 两 hook 交叉存在 + boundary scan 检测 hook 修改 |
| 空 scope → BLOCK | 可能阻塞合法的紧急修复 | 紧急修复应走正规流程（启动 pipeline + 声明 scope），不走捷径 |
| write_protection 增加模拟交易/保护 | 模拟交易/ 下设计文档(.md)被误拦 | CodeFilePatterns 仅匹配引擎路径，不含架构设计/目录 |

---

## 七、验证计划

| # | 场景 | 预期 |
|:--|:-----|:-----|
| V1 | 无 pipeline token + stage 代码文件/ | BLOCK |
| V2 | pipeline active + executor=红结 + gate_1=PASS | PASS |
| V3 | pipeline active + executor=红结 + gate_1=PENDING | **BLOCK** (新) |
| V4 | pipeline active + executor=红枫 + gate_1=PASS | PASS |
| V5 | pipeline active + executor=腰子 + gate_1=PASS | BLOCK (非法executor) |
| V6 | pipeline active + files_scope 包含该文件 | PASS |
| V7 | pipeline active + files_scope 不包含该文件 | BLOCK |
| V8 | pipeline active + files_scope=[] (空数组) | **BLOCK** (升级) |
| V9 | Write/Edit 模拟交易/交易引擎/*.ps1 | 触发 write_protection 阻断 |
| V10 | stage 仅 .claude/ 文件 | PASS (M类不受影响) |

---

## 八、需求→代码核对清单

- [ ] 创建 `.claude/hooks/shared/pipeline-auth.py` (~60行)
- [ ] 共享模块包含完整 CodeFilePatterns (9条路径)
- [ ] 共享模块验证逻辑: active + executor + gate_1 + files_scope
- [ ] pre-commit-check.ps1 dot-source 共享模块
- [ ] pre-commit-check.ps1 Check F 重构为调用共享函数
- [ ] pre-commit-check.ps1 保持 Check A-E 不变
- [ ] write_protection_hook.ps1 dot-source 共享模块
- [ ] write_protection_hook.ps1 保护范围同步至 9条路径
- [ ] write_protection_hook.ps1 executor白名单同步至 红结+红枫
- [ ] write_protection_hook.ps1 增加 gate_1 检查
- [ ] T5: 空 files_scope → BLOCK (非WARN)
- [ ] gate_1=PENDING → BLOCK (分诊信息含"设计阶段未完成")
- [ ] 代码等级标注完整（L1 x3）
- [ ] 单文件行数均 ≤500
- [ ] 工作区已有的分诊 BLOCK 逻辑纳入共享模块

> 情墨签字：✓ 2026-05-25 | 腰子签字：✓ 2026-05-25 (全团咨询通过: 山猫✓ 玉夜✓ 流金✓ 青山✓ — 纯工程安全基础设施，流金建议交易引擎后续升级L2复核)
