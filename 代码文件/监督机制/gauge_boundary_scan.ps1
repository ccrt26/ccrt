# 旧影 Boundary Scan v1.0 — Weekly cross-reference audit
# Scans git commits touching code files vs pipeline archives vs hook logs
# Flags: violations, bypasses, blocks — generates audit report
param(
    [string]$Since = "",
    [string]$Until = "",
    [string]$OutputPath = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$BASE = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$HOOK_LOG = "$BASE\.claude\hooks\write_violations.log"
$PIPELINE_HISTORY = "$BASE\.claude\pipeline_history"
$AUDIT_DIR = "$BASE\审计报告"

# Date defaults: last 7 days
if (-not $Since) { $Since = (Get-Date).AddDays(-7).ToString('yyyy-MM-dd') }
if (-not $Until) { $Until = (Get-Date).ToString('yyyy-MM-dd') }
if (-not $OutputPath) {
    $AUDIT_DIR = Join-Path $BASE ".claude\boundary_scans"
    if (-not (Test-Path $AUDIT_DIR)) { New-Item -ItemType Directory -Path $AUDIT_DIR -Force | Out-Null }
    $OutputPath = Join-Path $AUDIT_DIR "boundary_scan_$(Get-Date -Format 'yyyyMMdd').md"
}

$report = @()
function Add-ReportLine($line) { $script:report += $line }

Add-ReportLine "# 旧影 Boundary Scan Report"
Add-ReportLine ""
Add-ReportLine "**Period**: $Since ~ $Until"
Add-ReportLine "**Generated**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Add-ReportLine ""

# ============================================================
# Phase 1: Scan git commits touching code files
# ============================================================
Add-ReportLine "## 1. Git Commits Touching Code Files"
Add-ReportLine ""

Push-Location $BASE
$gitLog = git log --since="$Since" --until="$Until" --name-only --pretty=format:"COMMIT|%H|%ai|%an|%s" -- "代码文件/*" 2>$null
Pop-Location

$commits = @()
$currentCommit = $null
foreach ($line in ($gitLog -split "`n")) {
    if ($line -match '^COMMIT\|') {
        if ($currentCommit) { $commits += $currentCommit }
        $parts = $line -split '\|'
        $currentCommit = @{
            Hash = $parts[1]
            Date = $parts[2]
            Author = $parts[3]
            Subject = ($parts[4..($parts.Count-1)] -join '|')
            Files = @()
        }
    } elseif ($line.Trim() -ne "" -and $currentCommit) {
        $currentCommit.Files += $line.Trim()
    }
}
if ($currentCommit) { $commits += $currentCommit }

if ($commits.Count -eq 0) {
    Add-ReportLine "No commits touching code files in this period."
} else {
    Add-ReportLine "| # | Date | Author | Subject | Files |"
    Add-ReportLine "|:--|:-----|:-------|:--------|:------|"
    $idx = 0
    foreach ($c in $commits) {
        $idx++
        $dateShort = $c.Date.Substring(0, 10)
        $filesShort = ($c.Files | Select-Object -First 3) -join ', '
        if ($c.Files.Count -gt 3) { $filesShort += " (+$($c.Files.Count - 3) more)" }
        Add-ReportLine "| $idx | $dateShort | $($c.Author) | $($c.Subject.Substring(0, [Math]::Min(50, $c.Subject.Length))) | $filesShort |"
    }
}
Add-ReportLine ""

# ============================================================
# Phase 2: Load pipeline archives
# ============================================================
Add-ReportLine "## 2. Pipeline Archives"
Add-ReportLine ""

$pipelines = @()
if (Test-Path $PIPELINE_HISTORY) {
    $archiveFiles = Get-ChildItem $PIPELINE_HISTORY -Filter "pipeline_*.json" | Sort-Object LastWriteTime -Descending
    foreach ($af in $archiveFiles) {
        try {
            $p = Get-Content $af.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            $pipelines += $p
        } catch { }
    }
}

if ($pipelines.Count -eq 0) {
    Add-ReportLine "No pipeline archives found."
} else {
    Add-ReportLine "| # | Task | Started | Completed | Stages |"
    Add-ReportLine "|:--|:-----|:--------|:----------|:-------|"
    $idx = 0
    foreach ($p in $pipelines) {
        $idx++
        $started = if ($p.started) { $p.started.Substring(0, 10) } else { "?" }
        $completed = if ($p.completed) { $p.completed.Substring(0, 10) } else { "?" }
        Add-ReportLine "| $idx | $($p.task) | $started | $completed | $($p.stage)/6 |"
    }
}
Add-ReportLine ""

# ============================================================
# Phase 3: Hook log analysis
# ============================================================
Add-ReportLine "## 3. Write Protection Hook Log"
Add-ReportLine ""

$hookEntries = @()
if (Test-Path $HOOK_LOG) {
    $logLines = Get-Content $HOOK_LOG -Encoding UTF8 -ErrorAction SilentlyContinue
    foreach ($logLine in $logLines) {
        if ($logLine -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (PASS|BLOCK) \| executor=(\S+) \| (.+)$') {
            $entryDate = [datetime]::Parse($matches[1])
            if ($entryDate -ge [datetime]::Parse($Since) -and $entryDate -le [datetime]::Parse($Until).AddDays(1)) {
                $hookEntries += @{
                    Date = $matches[1]
                    Status = $matches[2]
                    Executor = $matches[3]
                    File = $matches[4]
                }
            }
        }
    }
}

if ($hookEntries.Count -eq 0) {
    Add-ReportLine "No hook log entries in this period. (Hook may not be triggering — check matcher)"
} else {
    Add-ReportLine "| Date | Status | Executor | File |"
    Add-ReportLine "|:-----|:-------|:---------|:-----|"
    foreach ($e in $hookEntries) {
        Add-ReportLine "| $($e.Date) | $($e.Status) | $($e.Executor) | $($e.File) |"
    }
}
Add-ReportLine ""

# ============================================================
# Phase 4: Cross-Reference — Violation Detection
# ============================================================
Add-ReportLine "## 4. Cross-Reference — Violation Detection"
Add-ReportLine ""

$violations = @()

foreach ($c in $commits) {
    $commitDate = [datetime]::Parse($c.Date)
    $commitFileList = $c.Files | Where-Object { $_ -match '代码文件[\\/]' }
    if ($commitFileList.Count -eq 0) { continue }

    # Look for pipeline that was active during this commit window
    # Pipeline active = started before or during commit window, completed after
    $matchedPipeline = $null
    foreach ($p in $pipelines) {
        if (-not $p.started) { continue }
        $pStart = try { [datetime]::Parse($p.started) } catch { $null }
        $pEnd = try { if ($p.completed) { [datetime]::Parse($p.completed) } else { $null } } catch { $null }
        if (-not $pStart) { continue }

        # Pipeline window: started to completed (or +4h if no completion recorded)
        $pWindowEnd = if ($pEnd) { $pEnd } else { $pStart.AddHours(4) }

        if ($commitDate -ge $pStart -and $commitDate -le $pWindowEnd) {
            $matchedPipeline = $p
            break
        }
    }

    if (-not $matchedPipeline) {
        $violations += @{
            Type = "NO_PIPELINE"
            Severity = "P1"
            Commit = $c.Hash.Substring(0, 8)
            Date = $c.Date
            Files = $commitFileList
            Detail = "Code file commit without any pipeline token — likely direct write bypassing pipeline"
        }
    }
}

# Check hook BLOCK records
$blockEntries = $hookEntries | Where-Object { $_.Status -eq "BLOCK" }
if ($blockEntries.Count -gt 0) {
    foreach ($be in $blockEntries) {
        # Check if a PIPELINE was then created and commit made (indicates bypass via token creation)
        $violations += @{
            Type = "HOOK_BLOCKED"
            Severity = "P0"
            Commit = "N/A"
            Date = $be.Date
            Files = @($be.File)
            Detail = "Hook blocked a write attempt — check if workaround was used"
        }
    }
}

# Check for PASS records with non-红结 executor
$badPasses = $hookEntries | Where-Object { $_.Status -eq "PASS" -and $_.Executor -ne "红结" }
if ($badPasses.Count -gt 0) {
    foreach ($bp in $badPasses) {
        $violations += @{
            Type = "BAD_EXECUTOR"
            Severity = "P0"
            Commit = "N/A"
            Date = $bp.Date
            Files = @($bp.File)
            Detail = "Write passed with executor=$($bp.Executor) — only 红结 can write code files"
        }
    }
}

if ($violations.Count -eq 0) {
    Add-ReportLine "**✅ No violations detected.** All code file changes went through proper pipeline."
} else {
    Add-ReportLine "**⛔ $($violations.Count) violation(s) found!**"
    Add-ReportLine ""
    Add-ReportLine "| # | Severity | Type | Date | Detail |"
    Add-ReportLine "|:--|:---------|:-----|:-----|:-------|"
    $vidx = 0
    foreach ($v in $violations) {
        $vidx++
        Add-ReportLine "| $vidx | $($v.Severity) | $($v.Type) | $($v.Date) | $($v.Detail) |"
    }
    Add-ReportLine ""
    Add-ReportLine "### Violation Details"
    Add-ReportLine ""
    foreach ($v in $violations) {
        Add-ReportLine "**$($v.Type)** ($($v.Severity)) — $($v.Date)"
        Add-ReportLine "- Files: $($v.Files -join ', ')"
        Add-ReportLine "- $($v.Detail)"
        Add-ReportLine ""
    }
}
Add-ReportLine ""

# ============================================================
# Phase 5: Summary
# ============================================================
Add-ReportLine "## 5. Summary"
Add-ReportLine ""
Add-ReportLine "| Metric | Value |"
Add-ReportLine "|:-------|:------|"
Add-ReportLine "| Code file commits | $($commits.Count) |"
Add-ReportLine "| Pipeline archives | $($pipelines.Count) |"
Add-ReportLine "| Hook log entries | $($hookEntries.Count) |"
Add-ReportLine "| BLOCK records | $($blockEntries.Count) |"
Add-ReportLine "| Violations | $($violations.Count) |"
Add-ReportLine ""
Add-ReportLine "---"
Add-ReportLine "*Auto-generated by gauge_boundary_scan.ps1 v1.0*"

# Write output
try {
    $reportDir = Split-Path $OutputPath -Parent
    if (-not (Test-Path $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
    $report -join "`n" | Out-File -FilePath $OutputPath -Encoding UTF8 -Force
    Write-Host "Boundary scan report: $OutputPath" -ForegroundColor Green
} catch {
    # Fallback: write to script directory
    $fallback = Join-Path $PSScriptRoot "boundary_scan_$(Get-Date -Format 'yyyyMMdd_HHmmss').md"
    $report -join "`n" | Out-File -FilePath $fallback -Encoding UTF8 -Force
    Write-Host "Boundary scan report (fallback): $fallback" -ForegroundColor Yellow
}
Write-Host "  Commits: $($commits.Count) | Pipelines: $($pipelines.Count) | Hook entries: $($hookEntries.Count) | Violations: $($violations.Count)" -ForegroundColor $(if ($violations.Count -gt 0) { "Red" } else { "Green" })
