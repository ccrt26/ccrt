# 铁律量化 · Write Protection Hook — v3.0 unified (shared pipeline-auth.ps1)
# 检测非流程内的代码文件直接写入，阻断并记录
# matcher: Write || Edit
# 升级说明 v2.0→v3.0: 共享验证模块 + 模拟交易/保护 + gate_1检查 + 空scope=BLOCK
# 代码等级: L1 (安全基础设施)

param(
    [string]$ToolInput = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$BASE = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$LOG_FILE = "$BASE\.claude\hooks\write_violations.log"

# Dot-source shared auth module (single source of truth)
$AuthModule = "$BASE\.claude\hooks\shared\pipeline-auth.ps1"
if (Test-Path $AuthModule) {
    . $AuthModule
} else {
    Write-Error "[HOOK] Shared auth module not found: $AuthModule"
    exit 1
}

# 1. Parse file_path from ToolInput JSON
$filePath = ""
if ($ToolInput -match '"file_path"\s*:\s*"([^"]+)"') {
    $filePath = $Matches[1]
}
if (-not $filePath) {
    exit 0
}

# 2. Resolve paths
$normalizedPath = [System.IO.Path]::GetFullPath($filePath)
$relativePath = $normalizedPath -replace [regex]::Escape("$BASE\"), ""

# 3. Ensure log directory
$logDir = Split-Path $LOG_FILE -Parent
if (-not (Test-Path $logDir)) {
    try {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    } catch {
        Write-Error "[HOOK] Cannot create log dir: $logDir"
    }
}

# 4. Run shared authorization check
$auth = Test-PipelineAuthorization -FilePath $relativePath -ProjectRoot $BASE

# 5. Record audit log
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$logStatus = if ($auth.Authorized) { "PASS" } else { "BLOCK" }
$logEntry = "$timestamp | $logStatus | executor=$($auth.Executor) | gate1=$($auth.Gate1) | $relativePath | $($auth.Reason)"
try {
    Add-Content -Path $LOG_FILE -Value $logEntry -Encoding UTF8
} catch { }

# 6. Block or pass
if ($auth.Authorized) {
    exit 0
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Red
Write-Host '  ⛔ §八违规 — 代码文件直接写入被拦截' -ForegroundColor Red
Write-Host '========================================' -ForegroundColor Red
Write-Host "  文件: $relativePath" -ForegroundColor Yellow
Write-Host "  原因: $($auth.Reason)" -ForegroundColor Yellow
Write-Host '  解决:' -ForegroundColor White
Write-Host '    1. 启动流程: .\pipeline_token.ps1 -Start -Task "任务描述"' -ForegroundColor White
Write-Host '    2. 路由给红结编码实现' -ForegroundColor White
Write-Host '    3. 或确认这是M类操作（不应在受保护目录下）' -ForegroundColor White
Write-Host "  日志: $LOG_FILE" -ForegroundColor DarkGray
Write-Host '========================================' -ForegroundColor Red
Write-Host ''
exit 1
