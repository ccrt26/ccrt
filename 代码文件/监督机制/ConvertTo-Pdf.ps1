# 铁律量化 - 共享 PDF 转换函数（带文件锁检测 + 写入验证）
# 被各报告生成脚本 dot-source 加载
# 用法: . "路径\ConvertTo-Pdf.ps1"  # 然后调用 ConvertTo-Pdf

function ConvertTo-Pdf {
    <#
    .SYNOPSIS
        将 HTML 文件转换为 PDF，带写入验证和文件锁检测。
    .PARAMETER HtmlFile
        输入 HTML 文件路径
    .PARAMETER PdfFile
        输出 PDF 文件路径
    .PARAMETER MinSize
        最小合法大小（字节），默认 30000
    .PARAMETER Landscape
        是否横向布局（每日荐股报告用）
    .PARAMETER EdgePath
        Edge 可执行文件路径，自动查找
    .OUTPUTS
        [bool] 成功返回 $true，失败返回 $false
    #>
    param(
        [string]$HtmlFile,
        [string]$PdfFile,
        [int]$MinSize = 30000,
        [switch]$Landscape,
        [string]$EdgePath = ""
    )
. "$PSScriptRoot/../lib/init_encoding.ps1"

    # 1. 检查 HTML 是否存在
    if (-not (Test-Path $HtmlFile)) {
        Write-Warning "[PDF] HTML 文件不存在: $HtmlFile"
        return $false
    }

    # 2. 查找 Edge
    if (-not $EdgePath -or -not (Test-Path $EdgePath)) {
        $candidates = @(
            "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        )
        foreach ($c in $candidates) {
            if (Test-Path $c) { $EdgePath = $c; break }
        }
        if (-not $EdgePath -or -not (Test-Path $EdgePath)) {
            Write-Warning "[PDF] Edge 浏览器未找到"
            return $false
        }
    }

    $uri = "file:///$($HtmlFile.Replace('\','/'))"

    # 3. 安全覆盖写入：先写临时文件，验证通过后原子替换（红线§1.7 PDF保护）
    # 不再先删后建——Edge失败不会导致旧PDF永久丢失
    $tmpFile = "$PdfFile.tmp"
    $oldExists = $false
    if (Test-Path $PdfFile) {
        $oldExists = $true
    }
    # 清理可能残留的临时文件（上次异常中断可能遗留）
    if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue }

    # 4. 调用 Edge headless
    $argsList = @(
        "--headless=new", "--disable-gpu", "--no-sandbox",
        "--print-to-pdf=$tmpFile",
        "--no-pdf-header-footer",
        $uri
    )

    # 移除旧的 --print-to-pdf-paper-size=A4（Edge headless=new 默认A4）
    # 注意：$uri（file:///...）必须作为最后一个参数传入，否则Edge打印空白页
    if ($Landscape) {
        $argsList += "--print-to-pdf-landscape"
        $argsList += "--print-to-pdf-margin-bottom=0"
        $argsList += "--print-to-pdf-margin-top=0"
    }

    try {
        $pi = Start-Process -FilePath $EdgePath -ArgumentList $argsList -Wait -PassThru -NoNewWindow:$false
    } catch {
        Write-Warning "[PDF] Edge 调用失败: $_"
        return $false
    }

    Start-Sleep -Seconds 3

    # 5. 写入验证（对临时文件）
    if (-not (Test-Path $tmpFile)) {
        if ($oldExists) {
            Write-Warning "[PDF] 写入失败（文件被锁定或路径不可写）: $PdfFile"
        } else {
            Write-Warning "[PDF] 生成失败，无输出文件: $PdfFile"
        }
        return $false
    }

    $size = (Get-Item $tmpFile).Length

    # 5a. 大小检查
    if ($size -le $MinSize) {
        Write-Warning "[PDF] 文件过小（$size bytes），可能内容异常: $PdfFile"
        Remove-Item $tmpFile -Force -ErrorAction SilentlyContinue
        return $false
    }

    # 5b. 验证通过 → 原子替换（Move-Item 保证旧PDF仅在Edge成功后替换）
    Move-Item $tmpFile $PdfFile -Force -ErrorAction Stop
    Write-Verbose "[PDF] 验证通过: $PdfFile ($([Math]::Round($size/1KB,0)) KB)"
    return $true
}

# 导出函数（dot-source 后可用）
Export-ModuleMember -Function ConvertTo-Pdf -ErrorAction SilentlyContinue
