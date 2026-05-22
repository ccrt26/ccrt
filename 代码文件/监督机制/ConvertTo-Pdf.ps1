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

    # 3. 记录旧文件状态 + 删除（关键！防止 Test-Path 误判）
    $oldExists = $false
    $oldTime = [DateTime]::MinValue
    if (Test-Path $PdfFile) {
        $oldExists = $true
        try { $oldTime = (Get-Item $PdfFile).LastWriteTime } catch {}
        Remove-Item $PdfFile -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 200
    }

    # 4. 调用 Edge headless
    $argsList = @(
        "--headless", "--disable-gpu", "--no-sandbox",
        "--print-to-pdf=$PdfFile",
        "--no-pdf-header-footer",
        "--print-to-pdf-paper-size=A4"
    )
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

    # 5. 写入验证
    if (-not (Test-Path $PdfFile)) {
        if ($oldExists) {
            Write-Warning "[PDF] 写入失败（文件被锁定或路径不可写）: $PdfFile"
        } else {
            Write-Warning "[PDF] 生成失败，无输出文件: $PdfFile"
        }
        return $false
    }

    $size = (Get-Item $PdfFile).Length

    # 5a. 旧文件曾存在 → 检查时间戳变化（确保是新写入的）
    if ($oldExists) {
        $newTime = (Get-Item $PdfFile).LastWriteTime
        if ($newTime -le $oldTime) {
            Write-Warning "[PDF] 文件时间戳未更新，判定为写入失败（文件被锁定）: $PdfFile"
            Write-Warning "[PDF] 旧时间: $($oldTime.ToString('HH:mm:ss')), 新时间: $($newTime.ToString('HH:mm:ss'))"
            return $false
        }
    }

    # 5b. 大小检查
    if ($size -le $MinSize) {
        Write-Warning "[PDF] 文件过小（$size bytes），可能内容异常: $PdfFile"
        return $false
    }

    Write-Verbose "[PDF] 验证通过: $PdfFile ($([Math]::Round($size/1KB,0)) KB)"
    return $true
}

# 导出函数（dot-source 后可用）
Export-ModuleMember -Function ConvertTo-Pdf -ErrorAction SilentlyContinue
