# 铁律量化 · Write Protection Hook — v2.0 阻断模式
# 检测非管线内的代码文件直接写入，阻断并记录
# matcher: Write || Edit
# 升级说明 v1.0→v2.0: WARN→BLOCK(exit 1) | stdin优先 | PASS也记日志

param(
    [string]$ToolInput = ""
)

$BASE = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$CODE_DIR = "$BASE\代码文件"
$LOG_FILE = "$BASE\.claude\hooks\write_violations.log"
$PIPELINE_TOKEN = "$BASE\.claude\pipeline_active.json"

# 1. 解析 file_path
# Claude Code 通过命令行参数传递 ToolInput JSON，非 stdin
$filePath = ""
$rawInput = $ToolInput

if ($rawInput -match '"file_path"\s*:\s*"([^"]+)"') {
    $filePath = $Matches[1]
}

if (-not $filePath) {
    exit 0  # 无法解析路径，静默放行
}

# 2. 判断是否在代码文件目录下
$normalizedPath = [System.IO.Path]::GetFullPath($filePath)
$normalizedCodeDir = [System.IO.Path]::GetFullPath($CODE_DIR)

if ($normalizedPath -notlike "$normalizedCodeDir*") {
    exit 0  # 不在代码文件目录，放行（M类白名单自动生效）
}

# 3. 确保日志目录存在
$logDir = Split-Path $LOG_FILE -Parent
if (-not (Test-Path $logDir)) {
    try {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    } catch {
        # 无法创建日志目录不阻断，仅降级输出到 stderr
        Write-Error "[HOOK] Cannot create log dir: $logDir"
    }
}

$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$relativePath = $normalizedPath -replace [regex]::Escape("$BASE\"), ""

# 4. 检查管线令牌
$authorized = $false
$executor = "none"
$blockReason = "无活跃管线令牌 — 代码文件写入须走§七工程交付管线"

if (Test-Path $PIPELINE_TOKEN) {
    try {
        $token = Get-Content $PIPELINE_TOKEN -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($token.active -eq $true) {
            $executor = $token.executor
            if ($executor -eq "红结") {
                $authorized = $true
            } else {
                $blockReason = "当前管线执行者=$executor，仅有红结可写入代码文件"
            }
        } else {
            $blockReason = "管线令牌已失效(active=false)"
        }
    } catch {
        $blockReason = "管线令牌损坏无法解析: $_"
    }
}

# 5. 记录审计日志
$logStatus = if ($authorized) { "PASS" } else { "BLOCK" }
$logEntry = "$timestamp | $logStatus | executor=$executor | $relativePath"
try {
    Add-Content -Path $LOG_FILE -Value $logEntry -Encoding UTF8
} catch { }

# 6. 阻断或放行
if ($authorized) {
    exit 0
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Red
Write-Host '  ⛔ §八违规 — 代码文件直接写入被拦截' -ForegroundColor Red
Write-Host '========================================' -ForegroundColor Red
Write-Host "  文件: $relativePath" -ForegroundColor Yellow
Write-Host "  原因: $blockReason" -ForegroundColor Yellow
Write-Host '  解决:' -ForegroundColor White
Write-Host '    1. 启动管线: .\pipeline_token.ps1 -Start -Task "任务描述"' -ForegroundColor White
Write-Host '    2. 路由给红结编码实现' -ForegroundColor White
Write-Host '    3. 或确认这是M类操作（不应在代码文件/目录下）' -ForegroundColor White
Write-Host "  日志: $LOG_FILE" -ForegroundColor DarkGray
Write-Host '========================================' -ForegroundColor Red
Write-Host ''
exit 1
