$rootDir = "c:\Users\34269\Documents\Claude\股票分析"
$simScript = Join-Path $rootDir "模拟交易\交易引擎\sim_trading.ps1"
$logFile = Join-Path $rootDir "临时报告\sim_log_20260525.txt"
& $simScript -Force 2>&1 | ForEach-Object {
    if ($_ -is [System.Management.Automation.ErrorRecord]) {
        $msg = $_.Exception.Message
        if ($msg.Length -gt 200) { $msg = $msg.Substring(0, 200) + "..." }
        Add-Content $logFile ("[ERROR] " + $msg)
        Write-Host ("[ERROR] " + $msg)
    } elseif ($_ -is [string] -and $_.Length -lt 500) {
        Add-Content $logFile $_
        Write-Host $_
    } else {
        $s = $_.ToString()
        if ($s.Length -gt 300) { $s = $s.Substring(0, 300) + "..." }
        Add-Content $logFile $s
        Write-Host $s
    }
}
Write-Host "`nLog saved to: $logFile"
