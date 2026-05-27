# L0 — 门户本地优先发布脚本
# 设计文档: 审计报告/架构设计/design_portal_local_first_workflow_20260527.md
# 用法:
#   .\portal_deploy.ps1 -Stage sync     # 同步远程
#   .\portal_deploy.ps1 -Stage preview  # 本地预览
#   .\portal_deploy.ps1 -Stage build    # 构建静态站
#   .\portal_deploy.ps1 -Stage verify   # 验证静态站
#   .\portal_deploy.ps1 -Stage deploy   # 部署上线
#   .\portal_deploy.ps1 -Stage full     # 一键完整流程

param(
    [ValidateSet("sync","preview","build","verify","deploy","full","status")]
    [string]$Stage = "status",
    [int]$PreviewPort = 8888,
    [int]$VerifyPort = 9999,
    [string]$CommitMessage = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$projectRoot = Resolve-Path "$scriptDir\..\.."
$template = Join-Path $scriptDir "portal_template.html"
$dashboard = Join-Path $scriptDir "pigeon_dashboard.html"
$generator = Join-Path $scriptDir "generate_portal.py"
$server = Join-Path $scriptDir "pigeon_server.py"
$docsDir = Join-Path $projectRoot "docs"
$staticIndex = Join-Path $docsDir "index.html"

# ----- helpers -----
function Write-Step($msg) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Write-OK($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  [ERROR] $msg" -ForegroundColor Red }

function Test-File($path, $label) {
    if (Test-Path $path) { Write-OK "$label: $path" }
    else { Write-Err "$label NOT FOUND: $path"; return $false }
    return $true
}

function Sync-TemplateToDashboard {
    if (-not (Test-Path $template)) {
        Write-Err "模板文件不存在: $template"
        return $false
    }
    Copy-Item $template $dashboard -Force
    Write-OK "模板已同步: portal_template.html → pigeon_dashboard.html"
    return $true
}

# ============================
#  STAGE: status
# ============================
function Show-Status {
    Write-Host ""
    Write-Host "=== 门户部署状态 ===" -ForegroundColor Cyan
    Write-Host ""

    # Check files
    $files = @(
        @{Path=$template; Label="设计模板"},
        @{Path=$dashboard; Label="本地预览文件"},
        @{Path=$generator; Label="构建脚本"},
        @{Path=$server; Label="本地服务器"},
        @{Path=$staticIndex; Label="静态站产物"}
    )
    foreach ($f in $files) {
        if (Test-Path $f.Path) {
            $size = (Get-Item $f.Path).Length
            $time = (Get-Item $f.Path).LastWriteTime.ToString("HH:mm:ss")
            Write-Host "  [EXISTS] $($f.Label): $($f.Path) ($([math]::Round($size/1024,1))KB, $time)" -ForegroundColor Green
        } else {
            Write-Host "  [MISSING] $($f.Label): $($f.Path)" -ForegroundColor Red
        }
    }

    # Template vs dashboard sync
    if ((Test-Path $template) -and (Test-Path $dashboard)) {
        $tHash = (Get-FileHash $template -Algorithm MD5).Hash
        $dHash = (Get-FileHash $dashboard -Algorithm MD5).Hash
        if ($tHash -eq $dHash) {
            Write-Host "  [SYNC] 模板与预览文件一致" -ForegroundColor Green
        } else {
            Write-Host "  [OUTDATED] 预览文件落后于模板，请运行 -Stage preview" -ForegroundColor Yellow
        }
    }

    # Docs content
    if (Test-Path $docsDir) {
        $deepCount = (Get-ChildItem "$docsDir\deep_analysis" -Directory -ErrorAction SilentlyContinue).Count
        $dailyCount = (Get-ChildItem "$docsDir\daily_reports" -Directory -ErrorAction SilentlyContinue).Count
        Write-Host "  [DOCS] 深度分析: $deepCount 只股票 | 日报: $dailyCount 只股票" -ForegroundColor Green
    }

    # Git status
    Write-Host ""
    Write-Host "--- Git 状态 ---" -ForegroundColor Gray
    git -C $projectRoot status --short 2>$null | Select-Object -First 15
    Write-Host ""

    Write-Host "下一步:" -ForegroundColor Cyan
    Write-Host "  .\portal_deploy.ps1 -Stage preview   → 本地动态预览" -ForegroundColor White
    Write-Host "  .\portal_deploy.ps1 -Stage full       → 一键完整发布" -ForegroundColor White
}

# ============================
#  STAGE: sync
# ============================
function Invoke-Sync {
    Write-Step "① 同步远程数据"
    Write-Host "正在 git pull ..." -ForegroundColor Yellow

    # Try direct
    $result = git -C $projectRoot pull origin master 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "git pull 成功"
        return $true
    }

    Write-Warn "直连失败，尝试代理..."
    $result = git -C $projectRoot -c http.proxy= -c https.proxy= pull origin master 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "git pull (代理) 成功"
        return $true
    }

    Write-Err "git pull 失败（网络不可达）"
    Write-Host "  可以继续本地开发，稍后再同步" -ForegroundColor Yellow
    return $false
}

# ============================
#  STAGE: preview
# ============================
function Invoke-Preview {
    Write-Step "②+③ 本地动态预览"

    # Sync template → dashboard
    if (-not (Sync-TemplateToDashboard)) { return $false }

    # Check Python
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $python) {
        Write-Err "Python 未安装"
        return $false
    }

    # Kill existing server on port
    $existing = Get-NetTCPConnection -LocalPort $PreviewPort -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warn "端口 $PreviewPort 已占用，尝试结束..."
        Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    # Start server
    Write-Host "启动本地服务器: http://127.0.0.1:${PreviewPort}/pigeon_dashboard.html" -ForegroundColor Yellow
    $proc = Start-Process -FilePath $python.Source `
        -ArgumentList "`"$server`" --port $PreviewPort" `
        -WindowStyle Minimized `
        -PassThru

    Start-Sleep -Seconds 2
    if ($proc.HasExited) {
        Write-Err "服务器启动失败 (exit code: $($proc.ExitCode))"
        return $false
    }

    # Open browser
    Start-Process "http://127.0.0.1:${PreviewPort}/pigeon_dashboard.html"
    Write-OK "本地预览已启动"
    Write-Host ""
    Write-Host "  验证清单:" -ForegroundColor Cyan
    Write-Host "  [ ] 三标签切换正常 (事件/深度分析/日报)" -ForegroundColor White
    Write-Host "  [ ] 事件数据加载 + Hero数字正确" -ForegroundColor White
    Write-Host "  [ ] 过滤功能 (股票/日期/类别/方向/搜索)" -ForegroundColor White
    Write-Host "  [ ] 点击事件卡片展开/折叠" -ForegroundColor White
    Write-Host "  [ ] 移动端响应式" -ForegroundColor White
    Write-Host "  [ ] 样式无错位" -ForegroundColor White
    Write-Host ""
    Write-Host "  验证通过后，关闭此窗口或按 Ctrl+C 停止服务器" -ForegroundColor Yellow
    Write-Host "  然后运行: .\portal_deploy.ps1 -Stage build" -ForegroundColor Cyan
}

# ============================
#  STAGE: build
# ============================
function Invoke-Build {
    Write-Step "④ 构建静态站"

    if (-not (Test-File $template "设计模板")) { return $false }
    if (-not (Test-File $generator "构建脚本")) { return $false }

    # Sync template first
    Sync-TemplateToDashboard

    # Run generator
    Write-Host "运行 generate_portal.py ..." -ForegroundColor Yellow
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $python) { Write-Err "Python 未安装"; return $false }

    $result = & $python.Source $generator 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "构建失败: $result"
        return $false
    }

    Write-Host $result
    Write-OK "静态站已生成: $staticIndex"

    # Show build stats
    if (Test-Path $staticIndex) {
        $size = [math]::Round((Get-Item $staticIndex).Length / 1024, 1)
        Write-Host "  产物大小: ${size}KB" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "  下一步: .\portal_deploy.ps1 -Stage verify" -ForegroundColor Cyan
    return $true
}

# ============================
#  STAGE: verify
# ============================
function Invoke-Verify {
    Write-Step "⑤ 本地静态验证"

    if (-not (Test-Path $staticIndex)) {
        Write-Err "静态站未构建，请先运行 -Stage build"
        return $false
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $python) { Write-Err "Python 未安装"; return $false }

    # Kill existing on verify port
    $existing = Get-NetTCPConnection -LocalPort $VerifyPort -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    Write-Host "启动静态验证服务器: http://127.0.0.1:${VerifyPort}/index.html" -ForegroundColor Yellow
    $proc = Start-Process -FilePath $python.Source `
        -ArgumentList "-m http.server $VerifyPort --directory `"$docsDir`"" `
        -WindowStyle Minimized `
        -PassThru

    Start-Sleep -Seconds 2
    if ($proc.HasExited) {
        Write-Err "验证服务器启动失败"
        return $false
    }

    Start-Process "http://127.0.0.1:${VerifyPort}/index.html"
    Write-OK "静态验证已启动"
    Write-Host ""
    Write-Host "  验证清单 (静态站):" -ForegroundColor Cyan
    Write-Host "  [ ] 首页加载正常 (事件数据内嵌)" -ForegroundColor White
    Write-Host "  [ ] 深度分析报告链接有效" -ForegroundColor White
    Write-Host "  [ ] 日报链接有效" -ForegroundColor White
    Write-Host "  [ ] 过滤/搜索功能正常 (静态API)" -ForegroundColor White
    Write-Host "  [ ] 离线可用 (无网络请求)" -ForegroundColor White
    Write-Host ""
    Write-Host "  验证通过后，关闭此窗口" -ForegroundColor Yellow
    Write-Host "  然后运行: .\portal_deploy.ps1 -Stage deploy" -ForegroundColor Cyan
}

# ============================
#  STAGE: deploy
# ============================
function Invoke-Deploy {
    Write-Step "⑥ 部署上线"

    # Pre-checks
    if (-not (Test-Path $staticIndex)) {
        Write-Err "静态站未构建，请先运行 -Stage build"
        return $false
    }

    # Show what will be deployed
    Write-Host "变更文件:" -ForegroundColor Yellow
    git -C $projectRoot diff --stat HEAD 2>$null
    Write-Host ""
    git -C $projectRoot status --short 2>$null
    Write-Host ""

    # Confirm
    $confirm = Read-Host "确认部署到 GitHub Pages? (输入 yes 确认)"
    if ($confirm -ne "yes") {
        Write-Warn "部署已取消"
        return $false
    }

    # Stage docs + template + dashboard
    Write-Host "暂存文件..." -ForegroundColor Yellow
    git -C $projectRoot add "docs/" 2>$null
    git -C $projectRoot add "代码文件/信鸽信息采集/portal_template.html" 2>$null
    git -C $projectRoot add "代码文件/信鸽信息采集/pigeon_dashboard.html" 2>$null
    git -C $projectRoot add "代码文件/信鸽信息采集/portal_deploy.ps1" 2>$null

    # Commit
    $msg = if ($CommitMessage) { $CommitMessage } else { "deploy: portal site update $(Get-Date -Format 'yyyyMMdd_HHmm')" }
    Write-Host "提交: $msg" -ForegroundColor Yellow
    git -C $projectRoot commit -m $msg 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "提交可能有警告，继续推送..."
    }

    # Push (direct first, then proxy)
    Write-Host "推送..." -ForegroundColor Yellow
    $pushResult = git -C $projectRoot -c http.proxy= -c https.proxy= push origin master 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "推送成功 (直连)"
    } else {
        Write-Warn "直连失败，尝试代理..."
        $pushResult = git -C $projectRoot push origin master 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-OK "推送成功 (代理)"
        } else {
            Write-Err "推送失败: $pushResult"
            Write-Host "请手动推送或检查网络" -ForegroundColor Yellow
            return $false
        }
    }

    Write-OK "部署完成!"
    Write-Host "  线上验证: https://ccrt26.github.io/ccrt/" -ForegroundColor Cyan
    Write-Host "  三个标签页:" -ForegroundColor White
    Write-Host "    https://ccrt26.github.io/ccrt/#events" -ForegroundColor White
    Write-Host "    https://ccrt26.github.io/ccrt/#deep" -ForegroundColor White
    Write-Host "    https://ccrt26.github.io/ccrt/#daily" -ForegroundColor White
    return $true
}

# ============================
#  STAGE: full
# ============================
function Invoke-Full {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Magenta
    Write-Host "  门户完整发布流程: sync → preview → build → verify → deploy" -ForegroundColor Magenta
    Write-Host "============================================================" -ForegroundColor Magenta

    # Step 1: Sync
    Invoke-Sync

    # Step 2+3: Preview
    Write-Host ""
    $skip = Read-Host "启动本地预览? (Enter 继续 / skip 跳过)"
    if ($skip -ne "skip") {
        Invoke-Preview
        Read-Host "预览验证完成后按 Enter 继续"
    }

    # Step 4: Build
    if (-not (Invoke-Build)) {
        Write-Err "构建失败，流程中止"
        return $false
    }

    # Step 5: Verify
    Write-Host ""
    $skip = Read-Host "启动静态验证? (Enter 继续 / skip 跳过)"
    if ($skip -ne "skip") {
        Invoke-Verify
        Read-Host "静态验证完成后按 Enter 继续"
    }

    # Step 6: Deploy
    Write-Host ""
    Invoke-Deploy
}

# ============================
#  MAIN
# ============================
switch ($Stage) {
    "status"  { Show-Status }
    "sync"    { Invoke-Sync }
    "preview" { Invoke-Preview }
    "build"   { Invoke-Build }
    "verify"  { Invoke-Verify }
    "deploy"  { Invoke-Deploy }
    "full"    { Invoke-Full }
}
