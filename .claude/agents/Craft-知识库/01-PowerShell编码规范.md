---
name: craft-knowledge-01
description: PowerShell编码规范 — .ps1/.psm1脚本开发模式、错误处理、API封装、JSON/CSV处理、进度显示、注释规范
metadata:
  type: knowledge
  role: Craft
  version: v1.0
  created: 2026-05-23
  knowledge_id: "01"
  title: PowerShell编码规范
  dependencies: []
  estimated_tokens_saved: 15000
---

# 01 — PowerShell编码规范

> Craft知识库 | 编号：01 | 版本：v1.0 | 2026-05-23
> 关联角色：`.claude/agents/代码工匠-Craft.md` §3.1

---

## 一、脚本入口模式

### 1.1 标准脚本模板

```powershell
<#
.SYNOPSIS
    简短描述脚本用途

.DESCRIPTION
    详细描述脚本做什么、输入输出、适用场景

.PARAMETER StockCodes
    股票代码列表，如 @("sh600000","sz000001")

.PARAMETER OutputPath
    输出文件路径，默认为当前目录下的output.json

.PARAMETER Debug
    调试开关，启用后输出详细信息

.EXAMPLE
    .\Get-StockData.ps1 -StockCodes @("sh600000") -OutputPath "data.json"

.NOTES
    作者: 铁律量化
    创建日期: 2026-05-23
    依赖: stock_data_fetcher.psm1
#>

param(
    [Parameter(Mandatory=$true)]
    [string[]]$StockCodes,

    [Parameter(Mandatory=$false)]
    [string]$OutputPath = (Join-Path $PSScriptRoot "output.json"),

    [Parameter(Mandatory=$false)]
    [switch]$Debug
)

$ErrorActionPreference = "Stop"

# 调试模式设置
if ($Debug) {
    $VerbosePreference = "Continue"
    Write-Host "[DEBUG] 调试模式已开启" -ForegroundColor Cyan
}

# === 主逻辑 ===
function Main {
    # ...
}

# === 入口 ===
try {
    Main
    exit 0
}
catch {
    Write-Error "脚本执行失败: $($_.Exception.Message)"
    exit 1
}
```

### 1.2 param() 块规则

- 必须是脚本的第一条可执行语句（注释除外）
- 必须参数用 `[Parameter(Mandatory=$true)]`
- 参数类型必须声明：`[string]` `[int]` `[string[]]` `[switch]` `[bool]`
- 有默认值的参数设 `Mandatory=$false`
- `[switch]` 参数不需要值，存在即为 `$true`

### 1.3 $ErrorActionPreference

- 脚本级：`$ErrorActionPreference = "Stop"` ——任何错误终止脚本
- 函数级（特殊场景）：`$ErrorActionPreference = "Continue"` + 手动检查 `$?` 和 `$LASTEXITCODE`
- 永远不要用 `SilentlyContinue` 除非你手动检查了所有错误——这是技术债制造器

---

## 二、函数命名与结构

### 2.1 Verb-Noun 命名规范

所有自定义函数遵循PowerShell标准动词：

| 动词 | 用途 | 示例 |
|:-----|:-----|:-----|
| `Get-` | 获取/读取数据 | `Get-StockPrice`, `Get-CacheData` |
| `Set-` | 设置/修改数据 | `Set-ConfigValue` |
| `Invoke-` | 执行操作（API调用、命令） | `Invoke-APIRetry`, `Invoke-DataPipeline` |
| `Test-` | 检查/验证（返回bool） | `Test-CacheFreshness`, `Test-APIConnection` |
| `New-` | 创建新资源（文件/对象/目录） | `New-ReportFile`, `New-LogDirectory` |
| `Convert-` | 数据格式转换 | `Convert-GbkToUtf8`, `Convert-APIResponse` |
| `Write-` | 输出信息 | `Write-Log`（项目自定义） |
| `Start-` | 启动进程/任务 | `Start-BatchFetch` |

### 2.2 函数结构模板

```powershell
<#
.SYNOPSIS
    获取股票实时行情数据

.DESCRIPTION
    通过腾讯API获取股票行情，支持批量查询（最多80只/次）。
    遵循1+2架构：腾讯主源 → 新浪备源 → 缓存兜底。

.PARAMETER StockCodes
    股票代码数组，格式 "sh600000" / "sz000001"

.PARAMETER ForceRefresh
    强制刷新，跳过缓存检测

.OUTPUTS
    PSCustomObject[] — 每只股票一个对象，包含 code/name/price/change 等字段

.EXAMPLE
    $data = Get-StockPrice -StockCodes @("sh600000","sz000001")
#>
function Get-StockPrice {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$StockCodes,

        [Parameter(Mandatory=$false)]
        [switch]$ForceRefresh
    )

    # 函数体
}
```

### 2.3 私有函数约定

- 不导出的内部函数使用 `function` 而非 `Function`（不做关键字大写）
- 不写 .SYNOPSIS 但必须在函数前用单行注释说明用途
- 放在调用它的公开函数的下面

---

## 三、错误处理

### 3.1 三层错误处理模式

```powershell
# 第1层：API/外部调用 — try/catch
try {
    $response = Invoke-WebRequest -Uri $url -TimeoutSec 10 -UseBasicParsing
} catch [System.Net.WebException] {
    Write-Log -Level "WARNING" -Message "网络超时，切换备源" -ScriptName $MyInvocation.MyCommand
    # 进入备源逻辑
} catch {
    Write-Log -Level "ERROR" -Message "未知错误: $($_.Exception.Message)" -ScriptName $MyInvocation.MyCommand
    throw
}

# 第2层：文件I/O — try/catch + finally
try {
    $data | ConvertTo-Json -Depth 5 | Out-File -FilePath $path -Encoding UTF8NoBOM
} catch {
    Write-Log -Level "ERROR" -Message "文件写入失败: $path — $($_.Exception.Message)" -ScriptName $MyInvocation.MyCommand
    throw
}

# 第3层：业务逻辑 — 手动检查 + Write-Error
if ($null -eq $cacheData -or $cacheData.Count -eq 0) {
    Write-Log -Level "WARNING" -Message "缓存为空，需重新获取" -ScriptName $MyInvocation.MyCommand
    # 继续到主API获取
}
```

### 3.2 $LASTEXITCODE 检查

```powershell
# 调用外部exe后必须检查
& python scoring_engine_v2.py --input data.json --output scores.json
if ($LASTEXITCODE -ne 0) {
    Write-Log -Level "ERROR" -Message "评分引擎异常退出，退出码: $LASTEXITCODE" -ScriptName $MyInvocation.MyCommand
    exit 1
}
```

### 3.3 $? 和 try/catch 的关系

- `$?` 只检查上一条命令的布尔成功，不检查 `$LASTEXITCODE`
- `try/catch` 捕获终止性错误（`$ErrorActionPreference = "Stop"` 时）
- 非终止性错误（如 `Write-Error`）不会被 `catch` 捕获——需要检查 `$?`
- 规则：对外调用一律用 `-ErrorAction Stop` 或 `$ErrorActionPreference = "Stop"`

---

## 四、输出约定

### 4.1 五个输出流的用途

| 流 | Cmdlet | 用途 | 是否污染管道 |
|:---|:-------|:-----|:----------:|
| Success | `Write-Output` | 管道输出，给下游脚本/命令消费 | 是（这是设计意图） |
| Host | `Write-Host` | 用户可见的进度/结果信息 | 否 |
| Verbose | `Write-Verbose` | 调试/详细步骤信息 | 否 |
| Warning | `Write-Warning` | 非致命异常提示 | 否 |
| Error | `Write-Error` | 错误但不终止脚本（谨慎用） | 否 |

### 4.2 关键规则

- **函数返回值**：用 `Write-Output` 或直接输出对象。PowerShell函数会把管道中所有未捕获的输出都作为返回值——小心 `return` 和隐性输出。
- **`return` 的真相**：`return $obj` 实际上是把 `$obj` 放到管道然后退出函数。`return` 本身不阻止其他输出。
- **防止输出污染**：不需要输出的地方用 `[void]` 或 `> $null`。如：`[void]$collection.Add($item)` 或 `$result = Get-Something`。

### 4.3 反模式

```powershell
# ❌ 错误：Write-Host 用于数据传递（下游脚本拿不到）
Write-Host $price

# ✅ 正确：Write-Output 用于数据传递
Write-Output $price
# 或直接
$price

# ❌ 错误：字符串拼接在管道函数中
$log = "价格: " + $price
Write-Host $log

# ✅ 正确：格式化
Write-Host "价格: $price"
```

---

## 五、API调用封装

### 5.1 标准API调用函数模板

```powershell
function Invoke-APIRetry {
    param(
        [string]$Uri,
        [int]$MaxRetries = 3,
        [int]$TimeoutSec = 10,
        [int]$BaseDelayMs = 1000
    )

    $attempt = 0
    do {
        $attempt++
        try {
            Write-Log -Level "DEBUG" -Message "API调用 尝试 $attempt/$MaxRetries : $Uri" -ScriptName $MyInvocation.MyCommand

            $response = Invoke-WebRequest -Uri $Uri -TimeoutSec $TimeoutSec -UseBasicParsing `
                -UserAgent "Mozilla/5.0 (compatible; TielvQuant/1.0)" `
                -ErrorAction Stop

            if ($response.StatusCode -eq 200) {
                return $response.Content
            }
        }
        catch [System.Net.WebException] {
            Write-Log -Level "WARNING" -Message "网络错误 尝试 $attempt: $($_.Exception.Message)" -ScriptName $MyInvocation.MyCommand
        }
        catch {
            Write-Log -Level "ERROR" -Message "API调用异常: $($_.Exception.Message)" -ScriptName $MyInvocation.MyCommand
            if ($attempt -ge $MaxRetries) { throw }
        }

        if ($attempt -lt $MaxRetries) {
            $delay = $BaseDelayMs * [Math]::Pow(2, $attempt - 1)  # 指数退避: 1s, 2s, 4s
            Start-Sleep -Milliseconds $delay
        }
    } while ($attempt -lt $MaxRetries)

    throw "API调用失败，已重试 $MaxRetries 次: $Uri"
}
```

### 5.2 Invoke-WebRequest vs Invoke-RestMethod

- `Invoke-WebRequest`：返回完整HTTP响应，适用：需要检查Headers/StatusCode、原始文本处理（腾讯/新浪返回非标准JSON）
- `Invoke-RestMethod`：自动解析JSON/XML，适用：标准REST API（东方财富）
- 项目腾讯/新浪API用 `Invoke-WebRequest`（返回文本需要手动解析），东方财富用 `Invoke-RestMethod`

### 5.3 频率控制

```powershell
# 全局频率控制变量
$script:LastAPICallTime = [datetime]::MinValue
$script:MinAPIIintervalMs = 300  # 腾讯/新浪 >= 300ms

function Wait-APIFrequency {
    $elapsed = ([datetime]::Now - $script:LastAPICallTime).TotalMilliseconds
    if ($elapsed -lt $script:MinAPIIintervalMs) {
        $waitMs = $script:MinAPIIintervalMs - $elapsed
        Start-Sleep -Milliseconds $waitMs
    }
    $script:LastAPICallTime = [datetime]::Now
}
```

---

## 六、JSON处理

### 6.1 读取JSON

```powershell
# 标准读取
$data = Get-Content -Path $jsonPath -Encoding UTF8 | ConvertFrom-Json

# 安全读取（文件可能不存在）
if (Test-Path $jsonPath) {
    try {
        $data = Get-Content -Path $jsonPath -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Log -Level "WARNING" -Message "JSON解析失败: $jsonPath — $($_.Exception.Message)" -ScriptName $MyInvocation.MyCommand
        $data = $null
    }
}
```

### 6.2 写入JSON

```powershell
# 标准写入 — 注意 -Depth 避免截断，UTF8NoBOM 避免BOM问题
$data | ConvertTo-Json -Depth 5 | Out-File -FilePath $jsonPath -Encoding UTF8NoBOM

# 或用 Set-Content（需要手动序列化）
$jsonString = $data | ConvertTo-Json -Depth 5 -Compress:$false
Set-Content -Path $jsonPath -Value $jsonString -Encoding UTF8NoBOM
```

### 6.3 JSON访问安全模式

```powershell
# ❌ 危险：密钥不存在会返回null但不报错
$price = $stockData.data.price

# ✅ 安全：先检查密钥存在
if ($stockData.PSObject.Properties.Name -contains 'price') {
    $price = $stockData.price
} else {
    Write-Log -Level "WARNING" -Message "JSON缺少price字段" -ScriptName $MyInvocation.MyCommand
    $price = $null
}
```

### 6.4 ConvertFrom-Json 注意事项

- 默认 `-Depth 2`：JSON超过2层嵌套会被截断。有大JSON时显式 `ConvertFrom-Json -Depth 10`
- 返回 `PSCustomObject` 而非 `Hashtable`
- 中文自动处理（UTF-8），不需要额外编码转换

---

## 七、CSV处理

### 7.1 读取CSV

```powershell
# 标准读取
$data = Import-Csv -Path $csvPath -Encoding UTF8

# 指定分隔符
$data = Import-Csv -Path $csvPath -Encoding UTF8 -Delimiter "`t"  # TSV

# 类型转换：Import-Csv所有列都是string
$data | ForEach-Object {
    $_.Price = [double]$_.Price
    $_.Volume = [long]$_.Volume
}
```

### 7.2 写入CSV

```powershell
# 标准写入
$data | Export-Csv -Path $csvPath -Encoding UTF8NoBOM -NoTypeInformation

# 追加
$data | Export-Csv -Path $csvPath -Encoding UTF8NoBOM -NoTypeInformation -Append
```

### 7.3 CSV编码陷阱

- `Export-Csv` 默认 ASCII：中文内容必须 `-Encoding UTF8NoBOM`
- `Import-Csv` 默认也能读UTF8NoBOM的文件，但显式 `-Encoding UTF8` 更安全
- Excel打开UTF8 CSV会乱码（Excel需要BOM）——用 `UTF8`（带BOM）而非 `UTF8NoBOM`

---

## 八、文件路径

### 8.1 路径构建规范

```powershell
# ✅ 基于脚本位置的相对路径
$configPath = Join-Path $PSScriptRoot "config.json"
$dataDir = Join-Path $PSScriptRoot ".." "data"

# ✅ 确保目录存在
$outputDir = Join-Path $PSScriptRoot "output"
if (-not (Test-Path $outputDir)) {
    New-Item -Path $outputDir -ItemType Directory -Force | Out-Null
}

# ❌ 硬编码绝对路径 — 绝对禁止
$configPath = "C:\Users\34269\Documents\Claude\股票分析\config.json"
```

### 8.2 $PSScriptRoot 说明

- 包含脚本文件的目录路径
- 在.psm1模块文件中也可用（`$PSScriptRoot` 指向模块文件所在目录）
- 在交互式控制台中 `$PSScriptRoot` 为空——代码不能在控制台专用路径

---

## 九、进度显示

### 9.1 Write-Progress 模式

```powershell
# 批量处理中的进度显示
$total = $stockList.Count
$current = 0
foreach ($stock in $stockList) {
    $current++
    $percent = [int](($current / $total) * 100)
    Write-Progress -Activity "获取股票行情" -Status "$current / $total — $($stock.code)" -PercentComplete $percent

    # 实际工作...

    # 频率控制
    Start-Sleep -Milliseconds 300
}
Write-Progress -Activity "获取股票行情" -Completed
```

### 9.2 进度规则

- `Write-Progress` 只在批量操作（>10次循环）中使用
- 操作完成后必须 `-Completed` 清除进度条
- `-Status` 写当前处理的对象名称，方便定位卡在哪里

---

## 十、Comment-based help

### 10.1 必须包含的关键字

每个公开函数必须写以下注释块：

```powershell
<#
.SYNOPSIS
    [一句话说明函数做什么]

.DESCRIPTION
    [详细说明，包括：输入条件、处理逻辑、输出格式、异常处理、特殊行为]

.PARAMETER Xxx
    [参数说明，每个参数单独一段]

.OUTPUTS
    [返回值的类型和结构]

.EXAMPLE
    [至少一个完整可用示例]
#>
```

### 10.2 模块级帮助

.psm1 文件顶部写模块级注释：

```powershell
<#
.SYNOPSIS
    铁律量化 数据获取模块

.DESCRIPTION
    提供股票行情、财务数据的获取功能。
    实现1+2数据源架构：腾讯API(主) → 新浪API(备) → 本地缓存(兜底)。
    导出函数：Get-StockPrice, Get-FinancialData, Test-CacheFreshness
#>
```

---

## 十一、常见陷阱与反模式

### 11.1 比较运算符

```powershell
# ❌ 错误
if ($a == $b) { ... }
if ($a != $b) { ... }

# ✅ 正确
if ($a -eq $b) { ... }
if ($a -ne $b) { ... }
if ($a -gt $b) { ... }   # >
if ($a -lt $b) { ... }   # <
if ($a -ge $b) { ... }   # >=
if ($a -le $b) { ... }   # <=
```

### 11.2 字符串展开

```powershell
# 双引号展开变量
$name = "茅台"
$msg = "股票名称: $name"    # → "股票名称: 茅台"

# 单引号不展开
$msg = '股票名称: $name'    # → "股票名称: $name"

# 属性访问在字符串中的限制
# ❌ 这不工作
$msg = "价格: $stock.Price"
# ✅ 用子表达式
$msg = "价格: $($stock.Price)"
```

### 11.3 空值检查

```powershell
# ❌ 这些在某些情况下不可靠
if ($data) { ... }           # 空数组 @() 为 $false，但 @($null) 为 $true
if ($data -eq $null) { ... } # 当 $data 是数组时行为怪异

# ✅ 可靠的方式
if ($null -eq $data) { ... }       # $null 放左边
if ($data.Count -eq 0) { ... }     # 检查空集合
if ([string]::IsNullOrEmpty($s)) { ... }  # 检查空字符串
```

### 11.4 管道输出污染

```powershell
# ❌ 隐藏的bug：函数输出了不该输出的东西
function Get-Price {
    $collection.Add($item)    # .Add() 可能返回索引值，成为函数输出
    return $result
}

# ✅ 修复：用 [void] 吞掉无用输出
function Get-Price {
    [void]$collection.Add($item)
    return $result
}
```

### 11.5 foreach vs ForEach-Object

```powershell
# foreach 语句 — 更快，可用 break/continue
foreach ($item in $collection) {
    # ...
}

# ForEach-Object — 管道中，内存友好
$collection | ForEach-Object {
    # $_ 是当前项
}
```

### 11.6 脚本模块导出控制

```powershell
# .psm1 文件结尾：明确导出函数
Export-ModuleMember -Function @(
    'Get-StockPrice',
    'Get-FinancialData',
    'Test-CacheFreshness'
)
```

---

## 十二、项目PS脚本快速参考

| 脚本 | 入口参数 | 输出 | 关键依赖 |
|:-----|:--------|:-----|:---------|
| `stock_data_fetcher.psm1` | 模块文件 | 导出 Get- 系列函数 | — |
| `gen_daily_html.ps1` | -ScoresPath -OutputPath | HTML报告 | scoring_engine |
| `gen_doc_v2.ps1` | -InputPath -OutputPath | DOCX报告 | md_to_docx.py |
| `模拟交易引擎.ps1` | -ConfigPath -DataPath | 交易记录JSON | stock_data_fetcher |
| `check_redlines.ps1` | -TargetPath | 检查报告 | — |
| `version_supervisor.ps1` | -CrossCheck | 一致性报告 | — |

---

> **文件版本**: v1.0 | **创建日期**: 2026-05-23 | **所属**: 铁律量化 · Craft知识库 · 01-PowerShell编码规范
