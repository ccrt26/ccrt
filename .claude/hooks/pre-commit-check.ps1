<#
.SYNOPSIS
  TieLu LiangHua Pre-Commit self-check script.
  Runs before each git commit: version consistency, garbage files, doc integrity, commit msg format.
#>

param()

$ErrorActionPreference = "Stop"

$HookDir = Split-Path -Parent $PSCommandPath
. "$HookDir\shared\pipeline-auth.ps1"
$ProjectRoot = (Resolve-Path (Join-Path $HookDir "..\..")).Path
$LogFile = Join-Path $HookDir "pre-commit.log"
$script:HasError = $false

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "WARN", "ERROR", "BLOCK")]
        [string]$Level,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "[$Level] [$Timestamp] $Message"
    Write-Host $Line
    $Line | Out-File -FilePath $LogFile -Append -Encoding utf8
}

$StartTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"=== Pre-commit check started at $StartTime ===" | Out-File -FilePath $LogFile -Append -Encoding utf8

Push-Location $ProjectRoot

try {
    $StagedOutput = git -c core.quotepath=false diff --cached --name-only 2>$null
    $StagedFiles = @()
    if ($StagedOutput) {
        $StagedFiles = $StagedOutput -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    }

    if ($StagedFiles.Count -eq 0) {
        Write-Log "PASS" "No staged files, skip check."
        exit 0
    }

    $CommitMsgFile = Join-Path $ProjectRoot ".git\COMMIT_EDITMSG"
    $CommitMessage = ""
    if (Test-Path $CommitMsgFile) {
        $CommitMessage = Get-Content $CommitMsgFile -Raw -ErrorAction SilentlyContinue
    }

    # Check A: Version Consistency
    Write-Log "PASS" "===== Check A: Version Consistency ====="
    $StagedMdPs1 = $StagedFiles | Where-Object { $_ -match '\.(md|ps1)$' }

    foreach ($File in $StagedMdPs1) {
        $FileName = Split-Path $File -Leaf
        $FileVersion = $null
        if ($FileName -match '_v(\d+\.\d+(?:\.\d+)?)') {
            $FileVersion = $matches[1]
        }
        if (-not $FileVersion) { continue }

        $FullPath = Join-Path $ProjectRoot $File
        if (-not (Test-Path $FullPath)) {
            Write-Log "WARN" "File not found: $File"
            continue
        }

        $Content = Get-Content $FullPath -Raw -ErrorAction SilentlyContinue
        if (-not $Content) {
            Write-Log "WARN" "Cannot read file: $File"
            continue
        }

        $InternalVersion = $null
        if ($Content -match '[Vv]ersion[：:]\s*v(\d+\.\d+(?:\.\d+)?)') {
            $InternalVersion = $matches[1]
        }
        elseif ($Content -match '(?:^|\n)#[^\n]*v(\d+\.\d+(?:\.\d+)?)') {
            $InternalVersion = $matches[1]
        }
        elseif ($Content -match '(?m)^.{0,200}v(\d+\.\d+(?:\.\d+)?)') {
            $InternalVersion = $matches[1]
        }

        if ($InternalVersion) {
            if ($FileVersion -ne $InternalVersion) {
                Write-Log "ERROR" "Version mismatch: $FileName -- filename v$FileVersion, internal v$InternalVersion"
                $script:HasError = $true
            }
            else {
                Write-Log "PASS" "Version match: $FileName (v$FileVersion)"
            }
        }
        else {
            Write-Log "WARN" "Filename has v$FileVersion but no internal version found: $FileName"
        }
    }

    # Check B: Garbage Files
    Write-Log "PASS" "===== Check B: Garbage Files ====="
    $GarbagePatterns = @('^null$','\.tmp$','\.temp$','^~\$','/data_cache/')
    $GarbageFiles = @()
    foreach ($f in $StagedFiles) {
        foreach ($pat in $GarbagePatterns) {
            if ($f -match $pat) { $GarbageFiles += $f; break }
        }
    }
    if ($GarbageFiles.Count -gt 0) {
        Write-Log "WARN" "Garbage files detected:"
        foreach ($gf in $GarbageFiles) { Write-Log "WARN" "  - $gf" }
    }
    else { Write-Log "PASS" "No garbage files" }

    # Check C: Document Completeness
    Write-Log "PASS" "===== Check C: Document Completeness ====="
    $StagedMd = $StagedFiles | Where-Object { $_ -match '\.md$' }
    foreach ($MdFile in $StagedMd) {
        $DocxFile = $MdFile -replace '\.md$', '.docx'
        $DocxFullPath = Join-Path $ProjectRoot $DocxFile
        if (Test-Path $DocxFullPath) {
            if ($StagedFiles -notcontains $DocxFile) {
                Write-Log "WARN" ".md modified but .docx not staged: $MdFile -> $DocxFile"
            }
            else { Write-Log "PASS" ".md and .docx synced: $MdFile" }
        }
        else { Write-Log "PASS" "No .docx counterpart, skip: $MdFile" }
    }

    # Check D: Commit Message Format
    Write-Log "PASS" "===== Check D: Commit Message Format ====="
    if ($CommitMessage) {
        $FirstLine = ($CommitMessage -split "`r`n|`n")[0].Trim()
        if ($FirstLine -match '^(feat|fix|docs|chore|refactor|test):') {
            Write-Log "PASS" "Commit message format OK: $FirstLine"
        }
        elseif ($FirstLine -eq "") { Write-Log "WARN" "Commit message is empty" }
        else {
            Write-Log "WARN" "Commit message format invalid (expected feat|fix|docs|chore|refactor|test:): $FirstLine"
        }
    }
    else { Write-Log "PASS" "Commit message unavailable (pre-commit stage, skipped)" }

    # ========================================================================
    # Check E: Token Budget Gate (Token预算门禁) — 红线 v1.13 §2.3
    # E1. Agent定义文件行数 <= 250(警告) / <= 300(阻断)
    # E2. Agent定义文件大小 <= 12KB(警告) / <= 15KB(阻断)
    # E3. Python核心脚本 print() 数量 <= 8(警告) / <= 12(阻断)
    # E4. 新增大文件(>500KB)保护声明检查
    # E5. 新增文件AI禁止读取清单检查
    # ========================================================================
    Write-Log "PASS" "===== Check E: Token Budget Gate ====="

    function Get-EffectivePrintCount {
        param([string]$FilePath)
        $lines = Get-Content -Path $FilePath -ErrorAction SilentlyContinue
        if (-not $lines) { return 0 }
        $count = 0; $inDocstring = $false
        foreach ($rawLine in $lines) {
            $trimmed = $rawLine.TrimStart()
            if ($trimmed -eq '') { continue }
            $tripleCount = ([regex]::Matches($rawLine, [regex]::Escape('"""') + '|' + [regex]::Escape("'''"))).Count
            if ($tripleCount % 2 -eq 1) { $inDocstring = -not $inDocstring; continue }
            if ($tripleCount -ge 2) { continue }
            if ($inDocstring) { continue }
            if ($trimmed -match '^#') { continue }
            $count += ([regex]::Matches($rawLine, '\bprint\s*\(')).Count
        }
        return $count
    }

    function Test-ProtectionDeclaration {
        param([string]$FilePath)
        $head = Get-Content -Path $FilePath -TotalCount 30 -ErrorAction SilentlyContinue
        if (-not $head) { return $false }
        return ($head -join "`n") -match '(?i)LARGE_FILE_PROTECTED|FILE_PROTECTED|#\s*Protected large file|@ProtectionDeclared'
    }

    # E1/E2: Agent file line count and size
    $AgentDir = Join-Path $ProjectRoot ".claude\agents"
    if (Test-Path $AgentDir) {
        $AllAgentFiles = Get-ChildItem -Path $AgentDir -Filter "*.md" -File -ErrorAction SilentlyContinue |
            Where-Object { (Split-Path $_.FullName -Parent) -eq $AgentDir }
        foreach ($af in $AllAgentFiles) {
            $lineCount = (Get-Content $af.FullName | Measure-Object -Line).Lines
            $fileSize = (Get-Item $af.FullName).Length
            if ($lineCount -gt 300) {
                Write-Log "BLOCK" "E1 BLOCK: $($af.Name) — $lineCount lines (>300)"; $script:HasError = $true
            } elseif ($lineCount -gt 250) {
                Write-Log "WARN" "E1 WARN: $($af.Name) — $lineCount lines (>250)"
            } else { Write-Log "PASS" "E1 PASS: $($af.Name) ($lineCount lines)" }
            if ($fileSize -gt 15KB) {
                Write-Log "BLOCK" "E2 BLOCK: $($af.Name) — $([math]::Round($fileSize/1KB,1))KB (>15KB)"; $script:HasError = $true
            } elseif ($fileSize -gt 12KB) {
                Write-Log "WARN" "E2 WARN: $($af.Name) — $([math]::Round($fileSize/1KB,1))KB (>12KB)"
            } else { Write-Log "PASS" "E2 PASS: $($af.Name) ($([math]::Round($fileSize/1KB,1))KB)" }
        }
    } else { Write-Log "WARN" "E1/E2: Agent directory not found" }

    # E3: Python core script print() count
    $CoreScriptDirs = @((Join-Path $ProjectRoot "代码文件\每日荐股\分析逻辑"), (Join-Path $ProjectRoot "代码文件\每日荐股\scripts"))
    $StagedPy = $StagedFiles | Where-Object { $_ -match '\.py$' }
    $PyCorePaths = @()
    foreach ($pyFile in $StagedPy) {
        $absPy = Join-Path $ProjectRoot $pyFile
        foreach ($dir in $CoreScriptDirs) {
            $resolvedDir = (Resolve-Path $dir -ErrorAction SilentlyContinue).Path
            if ($resolvedDir -and (Resolve-Path $absPy -ErrorAction SilentlyContinue).Path.StartsWith($resolvedDir, [StringComparison]::OrdinalIgnoreCase)) {
                $PyCorePaths += $absPy; break
            }
        }
    }
    $PyCorePaths = $PyCorePaths | Select-Object -Unique
    foreach ($pyPath in $PyCorePaths) {
        if (-not (Test-Path $pyPath)) { continue }
        $printCount = Get-EffectivePrintCount -FilePath $pyPath
        $relPath = Resolve-Path $pyPath -Relative
        if ($printCount -gt 12) {
            Write-Log "BLOCK" "E3 BLOCK: $relPath — $printCount print() calls (>12)"; $script:HasError = $true
        } elseif ($printCount -gt 8) {
            Write-Log "WARN" "E3 WARN: $relPath — $printCount print() calls (>8)"
        } else { Write-Log "PASS" "E3 PASS: $relPath ($printCount print() calls)" }
    }

    # E4: New large file protection declaration
    $NewFiles = @()
    $newFileOutput = git -c core.quotepath=false diff --cached --diff-filter=A --name-only 2>$null
    if ($newFileOutput) { $NewFiles = $newFileOutput -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" } }
    foreach ($nf in $NewFiles) {
        $absNf = Join-Path $ProjectRoot $nf
        if (-not (Test-Path $absNf)) { continue }
        $nfSize = (Get-Item $absNf).Length
        if ($nfSize -gt 500KB) {
            if (-not (Test-ProtectionDeclaration -FilePath $absNf)) {
                Write-Log "WARN" "E4 WARN: New large file lacks protection declaration: $nf ($([math]::Round($nfSize/1KB,1))KB)"
            } else { Write-Log "PASS" "E4 PASS: $nf — protected" }
        }
    }

    # E5: 新增AI禁止读取文件
    $ForbiddenPatterns = @('\.env$','\.env\.','credentials\.(json|txt|yml|yaml|env|conf)$','secret\.(json|txt|yml|yaml)$','password','(?:^|[\\/])token\.(json|txt|yml|yaml|env)$','\.pem$','\.key$','\.pfx$','\.p12$','private_key','privatekey','id_rsa','id_ed25519','id_ecdsa','\.htpasswd$','oauth','service_account\.json$','settings\.local\.json$')
    foreach ($nf in $NewFiles) {
        foreach ($pat in $ForbiddenPatterns) {
            if (($nf -replace '\\','/') -match $pat) {
                Write-Log "BLOCK" "E5 BLOCK: New file matches forbidden pattern '$pat': $nf"; $script:HasError = $true
                break
            }
        }
    }
    Write-Log "PASS" "Check E complete"

    # ========================================================================
    # Check F: Code File Write Protection — v2.0 unified (shared pipeline-auth.ps1)
    # Protected paths, executor whitelist, gate_1 check, scope check — single source of truth
    # ========================================================================
    Write-Log "PASS" "===== Check F: Code File Write Protection ====="
    $StagedCodeFiles = $StagedFiles | Where-Object {
        $f = $_ -replace '\\', '/'
        foreach ($pat in $script:ProtectedPaths) {
            if ($f -match $pat) { return $true }
        }
        return $false
    }
    if ($StagedCodeFiles.Count -gt 0) {
        Write-Log "PASS" "Code files staged ($($StagedCodeFiles.Count) files):"
        foreach ($cf in $StagedCodeFiles) { Write-Log "PASS" "  - $cf" }

        $anyBlocked = $false
        foreach ($cf in $StagedCodeFiles) {
            $auth = Test-PipelineAuthorization -FilePath $cf -ProjectRoot $ProjectRoot
            if ($auth.Authorized) {
                Write-Log "PASS" "F PASS: $cf — $($auth.Reason)"
            } else {
                Write-Log "BLOCK" "F BLOCK: $cf — $($auth.Reason)"
                $script:HasError = $true
                $anyBlocked = $true
            }
        }
        if ($anyBlocked) {
            Write-Log "BLOCK" "Commit rejected. Start pipeline: .\pipeline_token.ps1 -Start -Task 'description'"
        }
    } else {
        Write-Log "PASS" "F1 PASS: No code files staged. Check F skipped."
    }
    Write-Log "PASS" "Check F complete"
}
catch {
    Write-Log "ERROR" "Script exception: $_"
    $script:HasError = $true
}
finally { Pop-Location }

$EndTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"=== Pre-commit check completed at $EndTime ===" | Out-File -FilePath $LogFile -Append -Encoding utf8

if ($script:HasError) {
    Write-Host ""
    Write-Host "[ERROR] Pre-commit check failed, blocking commit." -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "[PASS] Pre-commit check passed." -ForegroundColor Green
exit 0
