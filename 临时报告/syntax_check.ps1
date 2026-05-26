$base = "C:\Users\34269\Documents\Claude\股票分析"
$files = @(
    "$base\模拟交易\sim_orchestrator.ps1",
    "$base\模拟交易\交易引擎\sim_trading.ps1",
    "$base\模拟交易\每日荐股赛道\交易引擎\sim_trading_daily.ps1"
)
$allPass = $true
foreach ($f in $files) {
    $tokens = $null
    $errors = $null
    try {
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) {
            Write-Host "FAIL: $(Split-Path $f -Leaf) — $($errors.Count) errors"
            foreach ($e in $errors) { Write-Host "  $($e.Message)" }
            $allPass = $false
        } else {
            Write-Host "PASS: $(Split-Path $f -Leaf) ($((Get-Content $f).Count) lines)"
        }
    } catch {
        Write-Host "ERROR: $(Split-Path $f -Leaf) — $_"
        $allPass = $false
    }
}
if ($allPass) { Write-Host "ALL PASS" } else { Write-Host "SOME FAILURES" }
