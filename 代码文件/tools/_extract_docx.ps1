$file = 'C:\Users\34269\Desktop\每日荐股报告优化建议--豆包.docx'
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($file)
    $entry = $zip.GetEntry('word/document.xml')
    $stream = $entry.Open()
    $reader = New-Object System.IO.StreamReader($stream)
    $xml = $reader.ReadToEnd()
    $reader.Close()
    $zip.Dispose()

    # Strip XML tags
    $text = $xml -replace '<[^>]+>', ' ' -replace '\s+', ' '
    $text = $text -replace '&lt;', '<' -replace '&gt;', '>' -replace '&amp;', '&' -replace '&quot;', '"'
    $text = $text -replace '&apos;', "'"

    # Write to text file for reading
    $outFile = 'C:\Users\34269\Documents\Claude\股票分析\临时报告\_豆包建议_提取.txt'
    $text.Trim() | Set-Content $outFile -Encoding UTF8
    Write-Host "Extracted to: $outFile"
    Write-Host "Length: $($text.Length) chars"
} catch {
    Write-Error "Failed: $_"
}
