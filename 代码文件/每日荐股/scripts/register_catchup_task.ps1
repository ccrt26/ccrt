<#
.SYNOPSIS
  铁律量化 · 注册/移除开机自动追赶
.DESCRIPTION
  将 catchup_launcher.ps1 注册到 Windows 启动文件夹。
  用户每次登录时自动运行，检查是否有因关机错过的定时任务。

  不同于 Task Scheduler，启动文件夹方案：
  - 不需要管理员权限
  - 登录后触发（网络已就绪、文件可访问）
  - 可通过删除快捷方式随时移除

.PARAMETER Unregister
  移除启动项。
.EXAMPLE
  .\register_catchup_task.ps1           # 注册
  .\register_catchup_task.ps1 -Unregister  # 移除
#>

param([switch]$Unregister)

$taskName = "铁律量化-开机追赶"
$catchupScript = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\代码文件\每日荐股\scripts\catchup_launcher.ps1"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "$taskName.lnk"

# ---- 移除模式 ----
if ($Unregister) {
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force
        Write-Host "已移除启动项: $shortcutPath" -ForegroundColor Green
    } else {
        Write-Host "启动项不存在，无需移除" -ForegroundColor Gray
    }
    exit 0
}

# ---- 检查脚本 ----
if (-not (Test-Path $catchupScript)) {
    Write-Host "错误: 脚本不存在 — $catchupScript" -ForegroundColor Red
    exit 1
}

# ---- 检查启动文件夹 ----
if (-not (Test-Path $startupDir)) {
    New-Item -Path $startupDir -ItemType Directory -Force | Out-Null
}

# ---- 移除旧版 ----
if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
}

# ---- 创建快捷方式 ----
$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$catchupScript`""
$shortcut.WorkingDirectory = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))"
$shortcut.WindowStyle = 7   # Minimized
$shortcut.Description = "铁律量化 · 登录时检查并追赶因关机错过的定时任务"
$shortcut.Save()

# ---- 验证 ----
if (Test-Path $shortcutPath) {
    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host "  启动项注册成功！" -ForegroundColor Green
    Write-Host "=====================================" -ForegroundColor Green
    Write-Host "  位置: $shortcutPath"
    Write-Host "  触发: 每次登录 Windows 时自动运行"
    Write-Host ""
    Write-Host "  下次登录时即生效，无需重启验证" -ForegroundColor Gray
    Write-Host "  手动测试: powershell -File `"$catchupScript`" -SkipDelay -DryRun" -ForegroundColor Gray
    Write-Host "  移除: .\register_catchup_task.ps1 -Unregister" -ForegroundColor Gray
    Write-Host "=====================================" -ForegroundColor Green
} else {
    Write-Host "创建快捷方式失败" -ForegroundColor Red
    exit 1
}
