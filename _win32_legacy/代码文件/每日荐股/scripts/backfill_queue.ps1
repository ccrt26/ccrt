<#
.SYNOPSIS
  铁律量化 · 数据回填队列机制
.DESCRIPTION
  跟踪需要回填的数据任务，支持系统离线恢复和失败重试。

  当系统离线多天后上线时，catchup_launcher.ps1 调用本脚本
  处理积压的数据回填任务。通过调用 stock_data_fetcher.psm1
  中的获取函数完成数据拉取，结果自动写入 data_cache/ 目录。

  优先级体系：
    P1 — KLine（阻塞评分计算，最高优先级，缺失时无法完成选股）
    P2 — FundFlow / Margin / Northbound / Financial / Quote / PEPercentile（分析必需）
    P3 — Research / Sector / Other（补充数据，缺失不影响核心流程）

  队列文件：代码文件/每日荐股/data_cache/_backfill_queue.json

  使用方式：
    # 由 catchup_launcher.ps1 点源引入并调用
    . .\backfill_queue.ps1
    Invoke-BackfillQueue -MaxPriority "P2"

    # 手动添加单个任务
    Add-BackfillTask -DataType "KLine" -Key "KLine_600036_240" -MissedDate "2026-05-22"

    # 查看队列状态
    .\backfill_queue.ps1 -ShowStatus

    # 重置失败任务
    .\backfill_queue.ps1 -ResetFailed
#>

param(
    [ValidateSet("P1", "P2", "P3")]
    [string]$MaxPriority,

    [switch]$ShowStatus,

    [switch]$ResetFailed,

    [switch]$SkipStatus
)
. "$PSScriptRoot/../../lib/init_encoding.ps1"

# ============================================================
# Configuration
# ============================================================
if (-not $PSScriptRoot) {
    # 交互式 shell 中点源运行时 $PSScriptRoot 可能为空
    Write-Error "[backfill] 无法确定脚本目录（$PSScriptRoot 为空），请在脚本文件所在目录运行"
    return
}
$script:ScriptDir  = $PSScriptRoot
$script:CacheDir   = Join-Path (Split-Path $ScriptDir -Parent) "data_cache"
$script:QueueFile  = Join-Path $script:CacheDir "_backfill_queue.json"
$script:ModulePath = Join-Path $ScriptDir "stock_data_fetcher.psm1"
$script:RateLimitMs = 350  # API调用间隔

# 优先级数值映射（数字越小越优先）
$script:PriorityRank = @{ "P1" = 1; "P2" = 2; "P3" = 3 }

# 任务类型 → 默认优先级
$script:TypeDefaultPriority = @{
    "KLine"        = "P1"
    "FundFlow"     = "P2"
    "Margin"       = "P2"
    "Northbound"   = "P2"
    "Quote"        = "P2"
    "Financial"    = "P2"
    "PEPercentile" = "P2"
    "Research"     = "P3"
    "Sector"       = "P3"
}

# 确保缓存目录存在
if (-not (Test-Path $script:CacheDir)) {
    New-Item -ItemType Directory -Path $script:CacheDir -Force | Out-Null
}

# ============================================================
# 队列文件 I/O
# ============================================================
function Get-QueueContent {
    if (-not (Test-Path $script:QueueFile)) {
        return [PSCustomObject]@{ last_updated = $null; tasks = @() }
    }
    try {
        $raw = Get-Content $script:QueueFile -Encoding UTF8 -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return [PSCustomObject]@{ last_updated = $null; tasks = @() }
        }
        $queue = $raw | ConvertFrom-Json
        # 确保 tasks 总是数组
        if ($null -eq $queue.tasks) {
            $queue | Add-Member -MemberType NoteProperty -Name 'tasks' -Value @() -Force
        } elseif ($queue.tasks -isnot [array]) {
            $queue.tasks = @($queue.tasks)
        }
        # 确保 last_updated 字段存在
        if (-not (Get-Member -InputObject $queue -Name 'last_updated' -MemberType NoteProperty)) {
            $queue | Add-Member -MemberType NoteProperty -Name 'last_updated' -Value $null -Force
        }
        return $queue
    } catch {
        Write-Warning "[backfill] 队列文件损坏，创建空队列: $_"
        return [PSCustomObject]@{ last_updated = $null; tasks = @() }
    }
}

function Save-QueueContent {
    param($Queue)
    try {
        # 排序任务列表以保持可读性
        if ($Queue.tasks -and $Queue.tasks.Count -gt 0) {
            $Queue.tasks = $Queue.tasks | Sort-Object {
                "$($script:PriorityRank[$_.priority])_$($_.missed_date)_$($_.created)"
            }
        }
        $Queue | ConvertTo-Json -Depth 4 | Set-Content $script:QueueFile -Encoding UTF8
    } catch {
        Write-Warning "[backfill] 队列文件写入失败: $_"
    }
}

# ============================================================
# 任务 ID 生成（Key + 日期 => 唯一标识）
# ============================================================
function New-TaskId {
    param([string]$Key, [string]$MissedDate)
    return "${Key}_$($MissedDate -replace '-', '')"
}

# ============================================================
# 从 Key 中提取股票代码（6位数字）
# ============================================================
function Get-CodeFromKey {
    param([string]$Key)
    if ($Key -match '(\d{6})') {
        return $matches[1]
    }
    return ""
}

# ============================================================
# Add-BackfillTask
#   向回填队列添加一个数据获取任务。
#   幂等性保证：同一 Key + MissedDate 组合不会重复添加。
# ============================================================
function Add-BackfillTask {
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet("KLine", "FundFlow", "Margin", "Northbound", "Research",
                     "Quote", "Financial", "Sector", "PEPercentile")]
        [string]$DataType,

        [Parameter(Mandatory=$true)]
        [string]$Key,

        [ValidateSet("P1", "P2", "P3")]
        [string]$Priority,

        [string]$MissedDate,

        [hashtable]$Parameters = @{},

        [int]$MaxAttempts = 3
    )

    # 自动推导优先级
    if (-not $Priority) {
        $Priority = $script:TypeDefaultPriority[$DataType]
        if (-not $Priority) { $Priority = "P3" }
    }

    # 默认错过日期为今天
    if (-not $MissedDate) {
        $MissedDate = Get-Date -Format "yyyy-MM-dd"
    }

    # 提取股票代码
    $code = Get-CodeFromKey -Key $Key

    # 生成任务 ID
    $taskId = New-TaskId -Key $Key -MissedDate $MissedDate

    $queue = Get-QueueContent

    # === 幂等性检查 ===
    $existing = $queue.tasks | Where-Object { $_.id -eq $taskId }
    if ($existing) {
        switch ($existing.status) {
            "completed" {
                Write-Host "[backfill] 任务已完成, 跳过: $taskId" -ForegroundColor Gray
                return $taskId
            }
            "pending" {
                Write-Host "[backfill] 任务已在队列中, 跳过: $taskId" -ForegroundColor Gray
                return $taskId
            }
            "failed" {
                # 失败任务重新激活：重置重试计数
                Write-Host "[backfill] 重激活失败任务: $taskId" -ForegroundColor Yellow
                $existing.status       = "pending"
                $existing.attempts     = 0
                $existing.last_attempt = $null
                $existing.created      = (Get-Date).ToString("o")
                $existing.max_attempts = $MaxAttempts
                # 更新参数（调用者可能传入了不同的参数）
                if ($Parameters.Count -gt 0) {
                    $existing.parameters = $Parameters
                }
                $queue.last_updated = (Get-Date).ToString("o")
                Save-QueueContent -Queue $queue
                return $taskId
            }
        }
    }

    # === 创建新任务 ===
    $task = [PSCustomObject]@{
        id           = $taskId
        type         = $DataType
        key          = $Key
        code         = $code
        priority     = $Priority
        parameters   = $Parameters
        missed_date  = $MissedDate
        attempts     = 0
        max_attempts = $MaxAttempts
        last_attempt = $null
        created      = (Get-Date).ToString("o")
        status       = "pending"
    }

    $queue.tasks += $task
    $queue.last_updated = (Get-Date).ToString("o")
    Save-QueueContent -Queue $queue

    Write-Host "[backfill] 添加任务: $taskId [${DataType}/${Priority}] (错过日期: $MissedDate)" -ForegroundColor Cyan
    return $taskId
}

# ============================================================
# Invoke-BackfillTask (内部)
#   根据任务类型分派到 stock_data_fetcher 模块的对应函数。
#   返回 $true 表示数据获取成功（函数返回非空结果），
#   返回 $false 表示 API 调用返回空结果（可重试）。
#   抛出异常表示不可恢复的错误。
# ============================================================
function Invoke-BackfillTask {
    param($Task)

    $code = $Task.code

    # 归一化参数类型：JSON 反序列化后是 PSCustomObject，手动添加时可能是 hashtable
    # 统一转为 PSCustomObject 以便使用 .Property 语法访问
    $p = if ($Task.parameters) {
        if ($Task.parameters -is [hashtable]) {
            [PSCustomObject]$Task.parameters
        } else {
            $Task.parameters
        }
    } else {
        [PSCustomObject]@{}
    }

    try {
        switch ($Task.type) {
            "KLine" {
                $scale = if ($p.Scale) { $p.Scale } else { "240" }
                $count = if ($p.Count) { $p.Count } else { 120 }
                $result = Get-StockKLine -Code $code -Scale $scale -Count $count
                if ($null -eq $result -or @($result).Count -eq 0) { return $false }
                return $true
            }
            "FundFlow" {
                $days = if ($p.Days) { $p.Days } else { 5 }
                $result = Get-StockFundFlow -Code $code -Days $days
                if ($null -eq $result -or @($result).Count -eq 0) { return $false }
                return $true
            }
            "Margin" {
                $days = if ($p.Days) { $p.Days } else { 5 }
                $result = Get-MarginData -Code $code -Days $days
                if ($null -eq $result -or @($result).Count -eq 0) { return $false }
                return $true
            }
            "Northbound" {
                $result = Get-NorthboundHold -Code $code
                if ($null -eq $result) { return $false }
                return $true
            }
            "Research" {
                $count    = if ($p.Count) { $p.Count } else { 5 }
                $daysBack = if ($p.DaysBack) { $p.DaysBack } else { "30" }
                $result = Get-StockResearch -Code $code -Count $count -DaysBack $daysBack
                if ($null -eq $result -or @($result).Count -eq 0) { return $false }
                return $true
            }
            "Quote" {
                $result = Get-StockQuote -Code $code
                if ($null -eq $result) { return $false }
                return $true
            }
            "Financial" {
                $quarters = if ($p.Quarters) { $p.Quarters } else { 4 }
                $result = Get-StockFinancial -Code $code -Quarters $quarters
                if ($null -eq $result -or @($result).Count -eq 0) { return $false }
                return $true
            }
            "Sector" {
                $top = if ($p.Top) { $p.Top } else { 10 }
                $result = Get-SectorData -Top $top
                if ($null -eq $result -or @($result).Count -eq 0) { return $false }
                return $true
            }
            "PEPercentile" {
                $result = Get-PEPercentile -Code $code
                if ($null -eq $result) { return $false }
                return $true
            }
            default {
                Write-Warning "[backfill] 未知任务类型: $($Task.type)"
                return $false
            }
        }
    } catch {
        throw
    }
}

# ============================================================
# Invoke-BackfillQueue
#   按优先级顺序处理队列中所有待处理任务。
#   只处理优先级 >= MaxPriority 的任务（P1 最高）。
#   每个任务最多重试 max_attempts 次，任务间有 API 限速间隔。
# ============================================================
function Invoke-BackfillQueue {
    param(
        [ValidateSet("P1", "P2", "P3")]
        [string]$MaxPriority = "P2"
    )

    # 加载数据获取模块
    if (-not (Get-Module -Name "stock_data_fetcher")) {
        if (Test-Path $script:ModulePath) {
            Import-Module $script:ModulePath -Force -ErrorAction Stop
        } else {
            Write-Error "[backfill] 数据获取模块不存在: $script:ModulePath"
            return
        }
    }

    $queue   = Get-QueueContent
    $maxRank = $script:PriorityRank[$MaxPriority]

    # 筛选待处理任务（按优先级 > 创建时间排序）
    $pendingTasks = $queue.tasks | Where-Object {
        $_.status -eq "pending" -and
        $script:PriorityRank[$_.priority] -le $maxRank
    } | Sort-Object { $script:PriorityRank[$_.priority] }, created

    if ($pendingTasks.Count -eq 0) {
        if (-not $SkipStatus) {
            Write-Host "[backfill] 无待处理回填任务 (MaxPriority=$MaxPriority)" -ForegroundColor Green
        }
        return
    }

    Write-Host "`n[backfill] ===== 回填队列处理开始 =====" -ForegroundColor Cyan
    Write-Host "[backfill] 待处理: $($pendingTasks.Count) 个任务 (MaxPriority=$MaxPriority)" -ForegroundColor Cyan
    Write-Host "[backfill] 队列文件: $script:QueueFile" -ForegroundColor Gray

    $completed = 0
    $failed    = 0
    $total     = $pendingTasks.Count
    $startTime = Get-Date

    foreach ($task in $pendingTasks) {
        # 检查是否已达最大重试次数
        if ($task.attempts -ge $task.max_attempts) {
            Write-Warning "[backfill] SKIP: $($task.id) 已达最大重试($($task.max_attempts)次), 标记为失败"
            $task.status = "failed"
            $failed++
            continue
        }

        $attemptNum = $task.attempts + 1
        Write-Host ("  [{0}/{1}] {2} {3} ({4}) — 第{5}/{6}次" -f
            ($completed + $failed + 1), $total, $task.priority, $task.type,
            $task.code, $attemptNum, $task.max_attempts) -ForegroundColor Yellow

        $task.attempts++
        $task.last_attempt = (Get-Date).ToString("o")

        try {
            $success = Invoke-BackfillTask -Task $task

            if ($success) {
                $task.status       = "completed"
                $task.completed_at = (Get-Date).ToString("o")
                $completed++
                Write-Host "    => 成功" -ForegroundColor Green
            } else {
                if ($task.attempts -ge $task.max_attempts) {
                    $task.status = "failed"
                    $failed++
                    Write-Warning "    => 失败: API返回空结果(已达最大重试)"
                } else {
                    Write-Warning "    => API返回空结果, 下次调用时重试"
                }
            }
        } catch {
            Write-Warning "    => 异常: $($_.Exception.Message)"
            if ($task.attempts -ge $task.max_attempts) {
                $task.status = "failed"
                $failed++
                Write-Warning "    => 已达最大重试, 标记为失败"
            }
        }

        # API 限速间隔
        Start-Sleep -Milliseconds $script:RateLimitMs

        # 每处理一个任务就保存队列（防止中途崩溃丢失进度）
        Save-QueueContent -Queue $queue
    }

    $queue.last_updated = (Get-Date).ToString("o")
    Save-QueueContent -Queue $queue

    $elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)

    Write-Host "[backfill] ===== 回填队列处理完成 =====" -ForegroundColor Cyan
    Write-Host "[backfill] 成功: $completed / 失败: $failed / 总计: $total (耗时 ${elapsed}s)" -ForegroundColor $(if ($failed -eq 0) { "Green" } else { "Yellow" })

    if ($failed -gt 0) {
        Write-Warning "[backfill] $failed 个任务失败，将在下次调用 Invoke-BackfillQueue 时重试"
    }
}

# ============================================================
# Get-BackfillStatus
#   获取回填队列的当前状态快照。
# ============================================================
function Get-BackfillStatus {
    $queue = Get-QueueContent

    if ($queue.tasks.Count -eq 0) {
        Write-Host "[backfill] 队列为空" -ForegroundColor Green
        return [PSCustomObject]@{
            TotalTasks    = 0
            ByPriority    = @()
            ByStatus      = @()
            OldestPending = "无"
            NewestFailed  = "无"
            LastUpdated   = $queue.last_updated
        }
    }

    $byPriority = $queue.tasks | Group-Object priority | ForEach-Object {
        [PSCustomObject]@{ Priority = $_.Name; Count = $_.Count }
    } | Sort-Object { $script:PriorityRank[$_.Priority] }

    $byStatus = $queue.tasks | Group-Object status | ForEach-Object {
        [PSCustomObject]@{ Status = $_.Name; Count = $_.Count }
    } | Sort-Object Status

    $oldestPending = $queue.tasks |
        Where-Object { $_.status -eq "pending" } |
        Sort-Object created |
        Select-Object -First 1

    $newestFailed = $queue.tasks |
        Where-Object { $_.status -eq "failed" } |
        Sort-Object last_attempt -Descending |
        Select-Object -First 1

    $p1Pending = ($queue.tasks | Where-Object { $_.status -eq "pending" -and $_.priority -eq "P1" }).Count
    $p2Pending = ($queue.tasks | Where-Object { $_.status -eq "pending" -and $_.priority -eq "P2" }).Count
    $p3Pending = ($queue.tasks | Where-Object { $_.status -eq "pending" -and $_.priority -eq "P3" }).Count
    $failedCount = ($queue.tasks | Where-Object { $_.status -eq "failed" }).Count

    $summary = [PSCustomObject]@{
        TotalTasks     = $queue.tasks.Count
        PendingCount   = ($queue.tasks | Where-Object { $_.status -eq "pending" }).Count
        CompletedCount = ($queue.tasks | Where-Object { $_.status -eq "completed" }).Count
        FailedCount    = $failedCount
        P1_Pending     = $p1Pending
        P2_Pending     = $p2Pending
        P3_Pending     = $p3Pending
        ByPriority     = $byPriority
        ByStatus       = $byStatus
        OldestPending  = if ($oldestPending) {
            "$($oldestPending.id) (created: $($oldestPending.created))"
        } else { "无" }
        NewestFailed   = if ($newestFailed) {
            "$($newestFailed.id) (last: $($newestFailed.last_attempt))"
        } else { "无" }
        LastUpdated    = $queue.last_updated
        QueueFile      = $script:QueueFile
    }

    return $summary
}

# ============================================================
# Reset-FailedTasks
#   将所有标记为 "failed" 的任务重置为 "pending"。
#   用于手动干预后重新触发回填。
# ============================================================
function Reset-FailedTasks {
    $queue = Get-QueueContent

    $failedTasks = $queue.tasks | Where-Object { $_.status -eq "failed" }
    if ($failedTasks.Count -eq 0) {
        Write-Host "[backfill] 无失败任务需要重置" -ForegroundColor Green
        return
    }

    Write-Host "[backfill] 重置 $($failedTasks.Count) 个失败任务..." -ForegroundColor Cyan

    foreach ($task in $failedTasks) {
        Write-Host "  重置: $($task.id)" -ForegroundColor Yellow
        $task.status       = "pending"
        $task.attempts     = 0
        $task.last_attempt = $null
    }

    $queue.last_updated = (Get-Date).ToString("o")
    Save-QueueContent -Queue $queue

    Write-Host "[backfill] 已重置 $($failedTasks.Count) 个失败任务为待处理" -ForegroundColor Green
}

# ============================================================
# Remove-CompletedTasks
#   清理队列中已完成的任务（避免队列无限增长）。
# ============================================================
function Remove-CompletedTasks {
    param(
        [int]$OlderThanDays = 7
    )

    $queue = Get-QueueContent
    $cutoff = (Get-Date).AddDays(-$OlderThanDays)

    $before = $queue.tasks.Count
    $toRemove = $queue.tasks | Where-Object {
        $_.status -eq "completed" -and
        $_.completed_at -and
        (Get-Date $_.completed_at) -lt $cutoff
    }

    if ($toRemove.Count -eq 0) {
        Write-Host "[backfill] 无过期已完成任务 ($OlderThanDays 天前)" -ForegroundColor Green
        return
    }

    $queue.tasks = $queue.tasks | Where-Object {
        $_ -notin $toRemove
    }

    $queue.last_updated = (Get-Date).ToString("o")
    Save-QueueContent -Queue $queue

    Write-Host "[backfill] 清理: 移除 $($toRemove.Count) 个已完成任务 (队列: $before -> $($queue.tasks.Count))" -ForegroundColor Cyan
}

# ============================================================
# 导出函数（dot-source 后自动可用，无需显式导出）
#   Add-BackfillTask      — 添加回填任务到队列
#   Invoke-BackfillQueue  — 处理队列中的待处理任务
#   Get-BackfillStatus    — 查看队列状态
#   Reset-FailedTasks     — 重置失败任务为待处理
#   Remove-CompletedTasks — 清理过期已完成任务
# ============================================================

# ============================================================
# 直接调用入口（非 dot-source 模式）
# ============================================================
if ($MyInvocation.InvocationName -ne '.') {
    if ($ShowStatus) {
        $status = Get-BackfillStatus
        Write-Host "`n========== 回填队列状态 ==========" -ForegroundColor Cyan
        Write-Host "  总任务数:      $($status.TotalTasks)"
        Write-Host "  待处理:        $($status.PendingCount)"
        Write-Host "     P1(KLine):  $($status.P1_Pending)"
        Write-Host "     P2(分析):   $($status.P2_Pending)"
        Write-Host "     P3(补充):   $($status.P3_Pending)"
        Write-Host "  已完成:        $($status.CompletedCount)"
        Write-Host "  失败:          $($status.FailedCount)"
        Write-Host "  最早待处理:    $($status.OldestPending)"
        Write-Host "  最新失败:      $($status.NewestFailed)"
        Write-Host "  最后更新:      $($status.LastUpdated)"
        Write-Host "  队列文件:      $($status.QueueFile)"
        Write-Host "====================================`n"
    } elseif ($ResetFailed) {
        Reset-FailedTasks
    } else {
        # 默认行为：处理队列
        $mp = if ($MaxPriority) { $MaxPriority } else { "P2" }
        Invoke-BackfillQueue -MaxPriority $mp
    }
}
