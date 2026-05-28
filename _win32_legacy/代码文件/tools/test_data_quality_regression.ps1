# P3-3: 数据质量回归测试集
# 构造已知损坏数据 → 验证 check_data_quality.ps1 能正确检出
param(
    [string]$RootDir = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"
if (-not $RootDir) { $RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }

$qcScript = Join-Path $RootDir "代码文件\tools\check_data_quality.ps1"
$testDir = Join-Path $RootDir "临时报告\regression_test"
if (-not (Test-Path $testDir)) { New-Item -ItemType Directory -Path $testDir -Force | Out-Null }

$passed = 0; $failed = 0

function Test-Case {
    param([string]$Name, [string]$Description, [ScriptBlock]$CorruptFn, [string]$ExpectFlag, [bool]$ExpectFail)
    Write-Host "`n[TEST] $Name" -ForegroundColor Cyan
    Write-Host "  $Description"

    # 从正常数据文件复制一份作为测试素材
    $srcFile = Join-Path $RootDir "代码文件\数据\data_full.json"
    if (-not (Test-Path $srcFile)) {
        # 尝试备选
        $srcFile = Join-Path $RootDir "代码文件\数据\data_scored.json"
    }
    if (-not (Test-Path $srcFile)) {
        Write-Host "  SKIP: 无可用测试数据" -ForegroundColor Yellow
        return
    }

    $testFile = Join-Path $testDir "test_$($Name -replace '[^a-zA-Z0-9]','_').json"
    Copy-Item $srcFile $testFile -Force

    try {
        # 注入损坏
        $data = Get-Content $testFile -Raw -Encoding UTF8 | ConvertFrom-Json
        & $CorruptFn $data
        $corrupted = $data | ConvertTo-Json -Depth 10 -Compress
        [System.IO.File]::WriteAllText($testFile, $corrupted, [System.Text.UTF8Encoding]::new($false))

        # 运行质检
        $result = & $qcScript -Mode daily_sim -DataFile $testFile -RootDir $RootDir 2>&1 | ConvertFrom-Json

        # 判定
        $flagOk = ($result.Flag -eq $ExpectFlag)
        $passOk = ($result.Passed -eq (-not $ExpectFail))

        if ($flagOk -and $passOk) {
            Write-Host "  PASS (Flag=$($result.Flag), Passed=$($result.Passed))" -ForegroundColor Green
            $script:passed++
        } else {
            Write-Host "  FAIL: Expected Flag=$ExpectFlag Passed=$(-not $ExpectFail), Got Flag=$($result.Flag) Passed=$($result.Passed)" -ForegroundColor Red
            $script:failed++
        }
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
        $script:failed++
    } finally {
        Remove-Item $testFile -Force -ErrorAction SilentlyContinue
    }
}

# ============================================================
# 测试用例
# ============================================================

# TC-1: null TotalScore → 应检出 ERROR + Passed=false
Test-Case "null_TotalScore" "TotalScore设为null → 应报ERROR且阻断" {
    param($d)
    if ($d.Recommendations -and $d.Recommendations.Count -gt 0) {
        $d.Recommendations[0].TotalScore = $null
    }
} -ExpectFlag "degraded" -ExpectFail $true

# TC-2: 空推荐列表 → 应检出 WARN (<20只)
Test-Case "empty_recommendations" "推荐列表清空 → 应报WARN(推荐数<20)" {
    param($d)
    $d.Recommendations = @()
} -ExpectFlag "degraded" -ExpectFail $true

# TC-3: 文件不存在 → 应报 ERROR
Test-Case "missing_file" "数据文件不存在 → 应报ERROR且Flag=cached" {
    # 特殊处理：删文件
    $fakePath = Join-Path $testDir "nonexistent.json"
    $result = & $qcScript -Mode daily_sim -DataFile $fakePath -RootDir $RootDir 2>&1 | ConvertFrom-Json
    if ($result.Flag -eq "cached" -and -not $result.Passed) {
        Write-Host "  PASS (Flag=$($result.Flag), Passed=$($result.Passed))" -ForegroundColor Green
        $script:passed++
    } else {
        Write-Host "  FAIL: Expected Flag=cached Passed=false, Got Flag=$($result.Flag) Passed=$($result.Passed)" -ForegroundColor Red
        $script:failed++
    }
    return  # skip cleanup (no file to clean)
} -ExpectFlag "cached" -ExpectFail $true

# TC-4: null关键移动平均线(MA5) → 应检出 ERROR
Test-Case "null_MA5" "MA5设为null → 应报ERROR(null值穿透)" {
    param($d)
    if ($d.Recommendations -and $d.Recommendations.Count -gt 0) {
        $d.Recommendations[0].MA5 = $null
    }
} -ExpectFlag "degraded" -ExpectFail $true

# TC-5: 正常数据 → 应全部PASS
Test-Case "normal_data" "正常数据 → 应PASS, Flag=normal" {
    param($d) {} # 不改动
} -ExpectFlag "normal" -ExpectFail $false

# ============================================================
# 汇总
# ============================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "回归测试完成: PASS=$passed FAIL=$failed" -ForegroundColor $(if($failed -eq 0){'Green'}else{'Red'})
if ($failed -eq 0) {
    Write-Host "质量检查脚本 work as expected" -ForegroundColor Green
} else {
    Write-Host "WARNING: $failed 项失败, 质检脚本行为异常" -ForegroundColor Red
}

# 清理
Remove-Item $testDir -Recurse -Force -ErrorAction SilentlyContinue
exit $failed
