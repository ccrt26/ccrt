<#
.SYNOPSIS
  TieLu LiangHua Pre-Commit self-check script.
  Runs before each git commit: version consistency, garbage files, doc integrity, commit msg format.
#>

param()

$ErrorActionPreference = "Stop"

$HookDir = Split-Path -Parent $PSCommandPath
$ProjectRoot = Resolve-Path (Join-Path $HookDir "..\..")
$LogFile = Join-Path $HookDir "pre-commit.log"
$script:HasError = $false

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "WARN", "ERROR")]
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
    $StagedOutput = git diff --cached --name-only 2>$null
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
