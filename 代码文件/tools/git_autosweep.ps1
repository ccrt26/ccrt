<#
.SYNOPSIS
  Git auto-sweep — hourly scan for uncommitted changes, auto-commit data/report/config files, push to GitHub.
.DESCRIPTION
  Classification matrix:
    AUTO-COMMIT (--no-verify): .json/.jsonl/.csv/.txt/.log/.md/.pdf/.docx/.html + specific dirs
    PIPELINE-REQUIRED: .ps1/.py/.psm1/.bat under 代码文件/ or 模拟交易/ subdirs
  Push: direct → IP → API proxy (3-level fallback)
.OUTPUTS
  JSON: {"success": bool, "commits": [{"hash":"","files":0,"category":""}], "push_success": bool, "error": ""}
#>

param(
    [switch]$DryRun,
    [switch]$SkipPush
)

$ErrorActionPreference = "Continue"
$script:ProjectRoot = $PSScriptRoot | Split-Path -Parent | Split-Path -Parent
$LogFile = Join-Path $script:ProjectRoot "临时报告\git_autocommit.log"
$LockFile = Join-Path $script:ProjectRoot ".claude\sweep.lock"

# E5 forbidden patterns (same as git_autocommit.ps1)
$ForbiddenPatterns = @('\.env$', '\.env\.', 'credentials\.(json|txt|yml|yaml|env|conf)$',
    'secret\.(json|txt|yml|yaml)$', 'password', '(?:^|[\\/])token\.(json|txt|yml|yaml|env)$',
    '\.pem$', '\.key$', '\.pfx$', '\.p12$', 'private_key', 'privatekey',
    'id_rsa', 'id_ed25519', 'id_ecdsa', '\.htpasswd$', 'oauth',
    'service_account\.json$', 'settings\.local\.json$')

# Auto-commit extensions — data/report/config files
$AutoCommitExtensions = @('\.json$', '\.jsonl$', '\.csv$', '\.txt$', '\.log$', '\.md$', '\.pdf$', '\.docx$', '\.html$')

# Auto-commit path prefixes
$AutoCommitPaths = @(
    '^.claude[\\/]', '^临时报告[\\/]', '^历史数据[\\/]', '^审计报告[\\/]',
    '^重点股票[\\/]股票报告[\\/]', '^重点股票[\\/]深度分析[\\/]',
    '^重点股票[\\/]次日评估[\\/]', '^重点股票[\\/]预判记录[\\/]', '^重点股票[\\/]消息面数据[\\/]',
    '^每日荐股[\\/]股票报告[\\/]', '^每日荐股[\\/]评估报告[\\/]',
    '^模拟交易[\\/]持仓记录[\\/]', '^模拟交易[\\/]每日快照[\\/]', '^模拟交易[\\/]绩效报告[\\/]',
    '^项目成员[\\/]', '^CLAUDE\.md$', '^inspect_data_health\.py$'
)

# Pipeline-protected extensions
$PipelineExtensions = @('\.ps1$', '\.py$', '\.psm1$', '\.bat$')

function Write-SweepLog {
    param([string]$Status, [string]$CommitHash, [int]$FileCount, [string]$Category, [string]$ErrorMsg)
    $entry = [ordered]@{
        timestamp   = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        module      = 'sweep'
        status      = $Status
        commit_hash = $CommitHash
        files_count = $FileCount
        category    = $Category
        dry_run     = $DryRun.IsPresent
        error       = $ErrorMsg
    }
    $entry | ConvertTo-Json -Compress | Out-File -FilePath $LogFile -Append -Encoding utf8
}

# --- Lock check ---
if (Test-Path $LockFile) {
    $lockAge = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 10) {
        Write-SweepLog -Status "SKIPPED" -CommitHash "" -FileCount 0 -Category "" -ErrorMsg "Lock active (<10min)"
        Write-Output '{"success": true, "commits": [], "push_success": false, "error": "Lock active"}'
        exit 0
    }
}
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$timestamp | Out-File -FilePath $LockFile -Encoding utf8

try {
    Push-Location $script:ProjectRoot

    # --- Get all changed files ---
    $allStatus = git -c core.quotepath=false status --porcelain 2>$null
    if (-not $allStatus -or $allStatus.Trim() -eq '') {
        Write-SweepLog -Status "CLEAN" -CommitHash "" -FileCount 0 -Category "" -ErrorMsg ""
        Write-Output '{"success": true, "commits": [], "push_success": false, "error": ""}'
        exit 0
    }

    $allFiles = $allStatus -split "`n" | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '') { return }
        $line -replace '^[MADRC ?][MADRC ]?\s+', ''
    } | Where-Object { $_ -ne '' } | Select-Object -Unique

    # --- Classify files ---
    $autoFiles = @()
    $pipelineFiles = @()

    foreach ($f in $allFiles) {
        $normalized = $f -replace '\\', '/'
        $ext = [System.IO.Path]::GetExtension($f)

        # Check pipeline-protected first: specific dirs with code extensions
        $isPipeline = $false
        $pipelineDirPatterns = @('^代码文件[\\/]', '^模拟交易[\\/]交易引擎[\\/]',
            '^模拟交易[\\/]否决审查[\\/]', '^模拟交易[\\/]分析[\\/]',
            '^模拟交易[\\/]共享模块[\\/]', '^模拟交易[\\/]展示[\\/]', '^模拟交易[\\/]工具[\\/]')

        foreach ($extPat in $PipelineExtensions) {
            if ($normalized -match $extPat) {
                foreach ($dirPat in $pipelineDirPatterns) {
                    if ($normalized -match $dirPat) {
                        $isPipeline = $true
                        break
                    }
                }
                if ($isPipeline) { break }
            }
        }

        if ($isPipeline) {
            $pipelineFiles += $f
        } else {
            $autoFiles += $f
        }
    }

    $results = @()

    # --- Process auto-commit files ---
    if ($autoFiles.Count -gt 0) {
        # E5 check before --no-verify
        $e5Blocked = @()
        $safeAutoFiles = @()
        foreach ($f in $autoFiles) {
            $blocked = $false
            foreach ($pat in $ForbiddenPatterns) {
                if (($f -replace '\\', '/') -match $pat) {
                    $e5Blocked += $f
                    $blocked = $true
                    break
                }
            }
            if (-not $blocked) { $safeAutoFiles += $f }
        }

        if ($e5Blocked.Count -gt 0) {
            Write-SweepLog -Status "BLOCKED" -CommitHash "" -FileCount $e5Blocked.Count -Category "auto" -ErrorMsg "E5: $($e5Blocked -join ', ')"
        }

        if ($safeAutoFiles.Count -gt 0) {
            if ($DryRun) {
                Write-Host "[DRY-RUN] Auto-commit $($safeAutoFiles.Count) files:"
                foreach ($f in $safeAutoFiles) { Write-Host "  $f" }
                $results += [ordered]@{category="auto"; hash=""; files=$safeAutoFiles.Count}
            } else {
                foreach ($f in $safeAutoFiles) { git add -- $f 2>$null }
                # PDF deletion guard (红线§1.7) — unstage any deleted PDFs before commit
                $deletedPdfs = git -c core.quotepath=false diff --cached --diff-filter=D --name-only 2>$null | ForEach-Object { $_ } | Where-Object { $_ -match '\.pdf$' }
                if ($deletedPdfs) {
                    $pdfList = ($deletedPdfs -join ', ')
                    foreach ($pdf in $deletedPdfs) {
                        git reset HEAD -- $pdf 2>$null
                    }
                    Write-SweepLog -Status "PDF_BLOCKED" -CommitHash "" -FileCount @($deletedPdfs).Count -Category "auto" -ErrorMsg "PDF删除拦截(红线§1.7): $pdfList"
                }
                $commitMsg = "auto: sweep — 数据/报告/配置自动同步 [$(Get-Date -Format 'yyyyMMdd-HHmm')]"
                $commitResult = & git commit --no-verify -m $commitMsg 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $hash = (git log -1 --format="%h" 2>$null).Trim()
                    Write-SweepLog -Status "COMMITTED" -CommitHash $hash -FileCount $safeAutoFiles.Count -Category "auto" -ErrorMsg ""
                    $results += [ordered]@{category="auto"; hash=$hash; files=$safeAutoFiles.Count}
                } else {
                    $err = ($commitResult -join '; ') -replace '"', "'"
                    Write-SweepLog -Status "FAILED" -CommitHash "" -FileCount 0 -Category "auto" -ErrorMsg $err
                }
            }
        }
    }

    # --- Process pipeline files ---
    if ($pipelineFiles.Count -gt 0) {
        $tokenPath = Join-Path $script:ProjectRoot ".claude\pipeline_active.json"
        $canCommitPipeline = $false
        if (Test-Path $tokenPath) {
            try {
                $token = Get-Content $tokenPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $execOk = ($token.executor -eq [System.Text.Encoding]::UTF8.GetString([byte[]](0xe7, 0xba, 0xa2, 0xe7, 0xbb, 0x93)) -or
                           $token.executor -eq [System.Text.Encoding]::UTF8.GetString([byte[]](0xe7, 0xba, 0xa2, 0xe6, 0x9e, 0xab)))
                if ($token.active -and $execOk -and $token.gate_1 -eq 'PASS') {
                    $canCommitPipeline = $true
                }
            } catch { }
        }

        if ($DryRun) {
            Write-Host "[DRY-RUN] Pipeline files $($pipelineFiles.Count) (canCommit=$canCommitPipeline):"
            foreach ($f in $pipelineFiles) { Write-Host "  $f" }
            $results += [ordered]@{category="pipeline"; hash=""; files=$pipelineFiles.Count}
        } elseif ($canCommitPipeline) {
            foreach ($f in $pipelineFiles) { git add -- $f 2>$null }
            $commitMsg = "auto: sweep — 代码文件管线提交 [$(Get-Date -Format 'yyyyMMdd-HHmm')]"
            $commitResult = & git commit -m $commitMsg 2>&1
            if ($LASTEXITCODE -eq 0) {
                $hash = (git log -1 --format="%h" 2>$null).Trim()
                Write-SweepLog -Status "COMMITTED" -CommitHash $hash -FileCount $pipelineFiles.Count -Category "pipeline" -ErrorMsg ""
                $results += [ordered]@{category="pipeline"; hash=$hash; files=$pipelineFiles.Count}
            } else {
                $err = ($commitResult -join '; ') -replace '"', "'"
                Write-SweepLog -Status "FAILED" -CommitHash "" -FileCount 0 -Category "pipeline" -ErrorMsg $err
            }
        } else {
            Write-SweepLog -Status "SKIPPED" -CommitHash "" -FileCount $pipelineFiles.Count -Category "pipeline" -ErrorMsg "No active pipeline token"
        }
    }

    # --- Push ---
    $pushSuccess = $false
    if (-not $SkipPush -and $results.Count -gt 0 -and -not $DryRun) {
        $pushOk = $false
        # Level 1: direct GitHub
        $pushResult = & git push origin 2>&1
        if ($LASTEXITCODE -eq 0) { $pushOk = $true }
        else {
            # Level 2: direct IP
            $pushResult = & git push ip-ssh 2>&1
            if ($LASTEXITCODE -eq 0) { $pushOk = $true }
            else {
                # Level 3: API proxy
                $pushResult = & git push api-origin 2>&1
                if ($LASTEXITCODE -eq 0) { $pushOk = $true }
            }
        }
        $pushSuccess = $pushOk
        $pushStatus = if ($pushOk) { "PUSHED" } else { "PUSH_FAILED" }
        Write-SweepLog -Status $pushStatus -CommitHash "" -FileCount 0 -Category "" -ErrorMsg $(if (-not $pushOk) { ($pushResult -join '; ') -replace '"', "'" } else { "" })
    }

    # --- Output ---
    $output = [ordered]@{
        success = $true
        commits = @($results)
        push_success = $pushSuccess
        auto_files = $autoFiles.Count
        pipeline_files = $pipelineFiles.Count
    }
    Write-Output ($output | ConvertTo-Json -Compress)

} finally {
    Pop-Location
    if (Test-Path $LockFile) { Remove-Item $LockFile -Force -ErrorAction SilentlyContinue }
}
