# init_encoding.ps1 安全引入方案 — 架构设计

> 情墨 | 阶段① 设计交付物 | 2026-05-25
> pipeline_stage: complete
> finance_confirmed: true
> 腰子确认: 2026-05-25 | 纯基础设施变更，不触发全团金融咨询(§6.0适用条件不满足) | 方案C通过
> 代码等级: L1 (基础设施/策略层)

---

## 一、背景与动机

### 1.1 当前问题

`代码文件/lib/init_encoding.ps1` 于 2026-05-25 21:31 创建，提供统一的 UTF-8 编码初始化：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$OutputEncoding = [System.Text.Encoding]::UTF8
```

同日 21:51 后，一次批量操作向 ~155 个 .ps1/.psm1 文件第一行插入了：
```powershell
. "$PSScriptRoot/../lib/init_encoding.ps1"
```

**PowerShell 语法规则**：`param()` 块必须是脚本中第一个可执行语句。dot-source 是可执行语句，
放在 `param()` 之前导致解析失败。63 个带 `param()` 的脚本因此损坏。

### 1.2 受影响范围

| 类别 | 数量 | 影响 |
|:-----|:----:|:-----|
| 带 `param()` 脚本（损坏） | 63 | 无法通过 `-File` 或 `&` 调用 |
| 不带 `param()` 脚本 | ~92 | 正常（dot-source 在第一行合法） |
| .psm1 模块 | 数个 | 正常（模块无 param） |

关键受损基础设施：`pipeline_engine.ps1`、`version_supervisor.ps1`、
`run_keystock_analysis.ps1`、`generate_dashboard.ps1`、`pipeline_token.ps1` 等。

### 1.3 设计目标

- **零破坏**：所有现有脚本调用方式（`-File`、`&`、dot-source）均正常工作
- **可验证**：引入后有机检手段确保不会再次出现 `param()` 前有可执行语句
- **低维护**：新增脚本时开发者无需记忆特殊规则
- **渐进式**：可分批次引入，不要求一次性全量修改

---

## 二、方案对比

### 方案 A：$PROFILE 注入（不推荐）

将编码配置放入 PowerShell profile。所有交互式会话自动加载。

| 优点 | 缺点 |
|:-----|:-----|
| 零脚本修改 | 仅交互式会话生效；Task Scheduler / CI 不加载 profile；不可移植 |

### 方案 B：入口脚本包装器（不推荐）

创建 `entry.ps1` 包装器，设置编码后调用真实脚本。

| 优点 | 缺点 |
|:-----|:-----|
| 不改原脚本 | 所有调用点需改为包装器路径；Tool/Scheduler 配置全部需改 |

### 方案 C：param() 后置 dot-source（推荐）

按脚本类型分类处理 dot-source 位置：

- **有 `param()` 的脚本**：dot-source 放在 `param() { ... }` 的 `)` 之后的第一行
- **无 `param()` 的脚本**：dot-source 放在第一行
- **.psm1 模块**：dot-source 放在第一行

| 优点 | 缺点 |
|:-----|:-----|
| 改动最小（仅移动 dot-source 行位置）| 需逐文件检查 param() 位置 |
| 不改变调用方式 | 需机检手段防退化 |
| 与 PowerShell 语义一致 | |

**选择方案 C**。这是唯一同时满足"零破坏 + 不改变调用方式 + 可移植"的方案。

---

## 三、详细设计

### 3.1 插入位置规则

```
有 param() 的脚本：
  [comment/help header]
  [CmdletBinding()]
  param(
      ...
  )
  . "$PSScriptRoot/.../init_encoding.ps1"   ← 放在这里，param() 后第一行
  # rest of script...

无 param() 的脚本：
  . "$PSScriptRoot/.../init_encoding.ps1"   ← 放在第一行（安全）
  # rest of script...

.psm1 模块：
  . "$PSScriptRoot/.../init_encoding.ps1"   ← 放在第一行（模块无 param）
  # rest of module...
```

### 3.2 相对路径规范

dot-source 路径中的 `../` 深度取决于脚本相对于 `代码文件/lib/` 的目录深度：

| 脚本位置 | dot-source 路径 |
|:---------|:---------------|
| `代码文件/tools/xxx.ps1` | `"$PSScriptRoot/../lib/init_encoding.ps1"` |
| `代码文件/监督机制/xxx.ps1` | `"$PSScriptRoot/../lib/init_encoding.ps1"` |
| `代码文件/每日荐股/scripts/xxx.ps1` | `"$PSScriptRoot/../../lib/init_encoding.ps1"` |
| `代码文件/每日荐股/scripts/modules/xxx.ps1` | `"$PSScriptRoot/../../../lib/init_encoding.ps1"` |
| `代码文件/重点股票/xxx.ps1` | `"$PSScriptRoot/../lib/init_encoding.ps1"` |
| `代码文件/重点股票/分析逻辑/xxx.ps1` | `"$PSScriptRoot/../../lib/init_encoding.ps1"` |
| `代码文件/模拟交易/xxx.ps1` | `"$PSScriptRoot/../lib/init_encoding.ps1"` |
| `代码文件/规则红线/xxx.ps1` | `"$PSScriptRoot/../lib/init_encoding.ps1"` |

### 3.3 实施脚本设计

创建 `代码文件/lib/apply_init_encoding.ps1`（L1 级），负责：

1. 扫描 `代码文件/` 下所有 .ps1/.psm1 文件
2. 自动检测 `param()` 块位置
3. 按规则插入 dot-source 到正确位置
4. 已有 dot-source 时跳过（幂等）
5. 记录操作日志

伪代码：
```
for each .ps1/.psm1:
    content = ReadAllText(file)
    if content already has "init_encoding.ps1": skip
    
    depth = count "../" from file to "代码文件/lib/"
    
    if file has param() at top level:
        insert after closing ")" of param() block
    else:
        insert at line 1
    
    WriteAllText(file, modified_content)
```

### 3.4 验证脚本设计

创建 `代码文件/lib/verify_init_encoding.ps1`（L1 级），负责：

1. 检查所有脚本是否有 `init_encoding` dot-source
2. 检查 dot-source 是否在 `param()` 之前（违规）
3. 输出违规清单（文件路径 + 行号）
4. 集成到 pre-commit hook

---

## 四、影响评估

### 4.1 修改范围

| 文件 | 操作 | L级 |
|:-----|:-----|:---:|
| `代码文件/lib/apply_init_encoding.ps1` | 新增 | L1 |
| `代码文件/lib/verify_init_encoding.ps1` | 新增 | L1 |
| `代码文件/lib/init_encoding.ps1` | 无改动（已存在） | L0 |
| 155 个 .ps1/.psm1 文件 | 移动 dot-source 行位置 | L0 |

### 4.2 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:----:|:----:|:-----|
| param() 检测漏判 | 低 | 中 | apply 脚本用 AST 解析，不用正则 |
| 路径深度算错 | 低 | 低 | apply 脚本自动计算 `../` 深度 |
| 覆盖后脚本失效 | 极低 | 高 | git 工作区先 commit，apply 后测试 |

### 4.3 回滚方案

```bash
git checkout -- "代码文件/"
```
恢复到 apply 前状态。因 apply 后的状态就是正确状态，回滚反而回到无 init_encoding 状态，
故回滚仅用于 apply 脚本本身出错的情况。

---

## 五、不引入的变更

以下改动**明确排除**：

- ❌ 修改 `$PROFILE`（不可移植）
- ❌ 创建脚本包装器（改变调用方式）
- ❌ 改为 PowerShell 模块自动加载（过度工程）
- ❌ 修改 `param()` 为其他参数传递方式（改变接口契约）

---

## 六、需求 → 代码核对清单

| # | 需求 | 对应代码 | 验证方式 |
|:--|:-----|:--------|:--------|
| 1 | param() 后插入 dot-source | `apply_init_encoding.ps1` 的 AST 检测逻辑 | 运行后抽查 5 个带 param 脚本 |
| 2 | 无 param 脚本第一行插入 | `apply_init_encoding.ps1` 默认路径 | 运行后抽查 5 个无 param 脚本 |
| 3 | 路径深度自动计算 | `apply_init_encoding.ps1` 的 depth 计算 | 抽查不同目录深度的脚本 |
| 4 | 幂等性 | `apply_init_encoding.ps1` 的 skip 逻辑 | 连续运行两次，第二次无修改 |
| 5 | CI 退化检测 | `verify_init_encoding.ps1` + pre-commit hook | 故意放错 dot-source 后提交被拦截 |
| 6 | 所有脚本调用正常 | 回归测试套件 | 重点测试 pipeline_engine / run_keystock_analysis |

---

## 七、情墨自检（§1 红线对照）

- [x] 技术决策有理由和权衡（方案对比 §二）
- [x] 接口变更评估了影响范围（155 文件，全部 L0 级别）
- [x] 标注了 L0/L1/L2 等级
- [x] 无新增 >500 行文件
- [x] 需求 → 代码核对清单完整（§六）

> 情墨签字：________ | 日期：2026-05-25
> 腰子签字：________ | 日期：________
