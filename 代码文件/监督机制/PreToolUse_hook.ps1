# 铁律量化 · PreToolUse hook - 红线预检 + 样式合规 + 白皮书对照 (静默模式)
# 仅在检查失败时输出，通过时不消耗token
# matcher: Bash(*.ps1) || Bash(*.py) || Bash(python *)

param(
    [string]$ToolInput = ""
)

$errors = @()
$BASE = "C:\Users\34269\Documents\Claude\股票分析"

# 1. 红线合规快速预检（仅捕获失败）
$rl = & "$BASE\代码文件\规则红线\check_redlines.ps1" -Quick 2>&1
if ($LASTEXITCODE -ne 0 -or $rl -match '[!!]|FAIL|ERROR|违规') {
    $errors += "红线检查: $rl"
}

# 2. 报告样式合规检查（仅捕获失败）
$style = & "$BASE\代码文件\规则红线\check_report_style.ps1" -Quick 2>&1
if ($LASTEXITCODE -ne 0 -or $style -match '[!!]|FAIL|ERROR|违规') {
    $errors += "样式检查: $style"
}

# 3. 白皮书对照检查（匹配任务→白皮书，仅对评分/报告/评估类脚本触发）
if ($ToolInput -match 'scoring_engine|gen_daily|run_daily_eval|gen_eval|keystock|gen_doc|gen_pdf') {
    $task = & "$BASE\代码文件\监督机制\task_supervisor.ps1" -Command $ToolInput 2>&1
    # task_supervisor 总是返回0，输出匹配结果；仅在返回空时视为未匹配
    if ($task -match '未匹配到已知任务模式' -and $ToolInput -match '\.(ps1|py)') {
        # 未匹配不阻断，仅在verbose模式提示
    }
}

# 4. 紧急豁免过期检查（扫描改进日志，同一规则连续豁免>=3次告警）
$improvLog = "$BASE\改进日志.md"
if (Test-Path $improvLog) {
    $logContent = Get-Content $improvLog -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($logContent) {
        $exemptPattern = '豁免.*?(§\d+\.\d+[^)]*)'
        $exemptMatches = [regex]::Matches($logContent, $exemptPattern)
        if ($exemptMatches.Count -ge 3) {
            $ruleCounts = @{}
            foreach ($m in $exemptMatches) {
                $rule = ($m.Groups[1].Value -replace '\s+', ' ').Trim()
                if (-not $ruleCounts.ContainsKey($rule)) { $ruleCounts[$rule] = 0 }
                $ruleCounts[$rule]++
            }
            $overLimit = $ruleCounts.GetEnumerator() | Where-Object { $_.Value -ge 3 }
            if ($overLimit) {
                $overLimitList = ($overLimit | ForEach-Object { "$($_.Key): $($_.Value)次" }) -join '; '
                $errors += "紧急豁免: 以下规则连续豁免>=3次，须启动规则修订 — $overLimitList"
            }
        }
    }
}

# 仅在有错误时输出
if ($errors) {
    Write-Host '[HOOK] 合规检查失败！' -ForegroundColor Red
    $errors | ForEach-Object { Write-Host $_ -ForegroundColor Red }
}
