# L0 — 信鸽消息面面板启动器
# 启动 pigeon_server.py → 打开浏览器 → 窗口关闭时自动杀进程
param(
    [int]$Port = 8888
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$projectRoot = (Get-Item "$scriptDir\..\..").FullName
$serverScript = Join-Path $scriptDir "pigeon_server.py"
$pidFile = Join-Path $env:TEMP "pigeon_web_server.pid"

if (-not (Test-Path $serverScript)) {
    Write-Host "[launcher] ERROR: $serverScript not found" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# Check Python
$python = $null
try {
    $pyVer = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $python = "python"
    }
} catch {
    try {
        $pyVer = python3 --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $python = "python3"
        }
    } catch {}
}

if (-not $python) {
    Write-Host "[launcher] ERROR: Python not found. Please install Python 3." -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# Find free port
$maxAttempts = 10
$selectedPort = $Port
for ($i = 0; $i -lt $maxAttempts; $i++) {
    $testPort = $Port + $i
    $conn = $null
    try {
        $conn = [System.Net.Sockets.TcpClient]::new("127.0.0.1", $testPort)
        $conn.Close()
        Write-Host "[launcher] Port $testPort in use, trying next..."
    } catch {
        $selectedPort = $testPort
        break
    }
}

# Start server
Write-Host "[launcher] Starting pigeon server on port $selectedPort..."
$proc = Start-Process -FilePath $python `
    -ArgumentList "`"$serverScript`" --port $selectedPort" `
    -WindowStyle Minimized `
    -PassThru

$proc.Id | Set-Content -Path $pidFile
Start-Sleep -Seconds 2

if ($proc.HasExited) {
    Write-Host "[launcher] ERROR: Server failed to start (exit code: $($proc.ExitCode))" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# Open browser
$url = "http://127.0.0.1:${selectedPort}/pigeon_dashboard.html"
Write-Host "[launcher] Opening browser: $url"
Start-Process $url

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  信鸽消息面面板已启动 → $url" -ForegroundColor Green
Write-Host "  关闭此窗口将停止服务器" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "按 Enter 停止服务"

# Cleanup
Write-Host "[launcher] Stopping server..."
try {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
} catch {}
if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "[launcher] Server stopped."
