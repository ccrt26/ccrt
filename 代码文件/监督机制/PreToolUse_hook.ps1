# 铁律量化 · PreToolUse hook - 红线预检 + 样式合规 (静默模式)
# 仅在检查失败时输出，通过时不消耗token
# matcher: Bash(*.ps1) || Bash(*.py) || Bash(python *)

$errors = @()

# 红线合规快速预检（仅捕获失败）
$rl = & "C:\Users\34269\Documents\Claude\股票分析\代码文件\规则红线\check_redlines.ps1" -Quick 2>&1
if ($LASTEXITCODE -ne 0 -or $rl -match '\[!!\]|FAIL|ERROR|违规') {
    $errors += "红线检查: $rl"
}

# 报告样式合规检查（仅捕获失败）
$style = & "C:\Users\34269\Documents\Claude\股票分析\代码文件\规则红线\check_report_style.ps1" -Quick 2>&1
if ($LASTEXITCODE -ne 0 -or $style -match '\[!!\]|FAIL|ERROR|违规') {
    $errors += "样式检查: $style"
}

# 仅在有错误时输出
if ($errors) {
    Write-Host '[HOOK] 合规检查失败！' -ForegroundColor Red
    $errors | ForEach-Object { Write-Host $_ -ForegroundColor Red }
}
