<#
.SYNOPSIS
  Document verification script
.DESCRIPTION
  Verifies: 1) MD version matches filename, 2) DOCX exists and non-empty, 3) DOCX integrity
.PARAMETER DocName
  Document name
.PARAMETER ExpectedVersion
  Expected version, e.g. "v1.2"
#>
param(
    [Parameter(Mandatory = $true)][string]$DocName,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [string]$BaseDir = "C:\Users\34269\Documents\Claude\股票分析\每日荐股\事后评估"
)
$errors = @(); $warnings = @()
Write-Output "============================================"
Write-Output ("  Verify: " + $DocName + " " + $ExpectedVersion)
Write-Output "============================================"
$mdFile = Join-Path $BaseDir ($DocName + "_" + $ExpectedVersion + ".md")
$docxFile = Join-Path $BaseDir ($DocName + "_" + $ExpectedVersion + ".docx")
if (Test-Path $mdFile) {
    $line = (Get-Content $mdFile -Encoding UTF8 -TotalCount 1)
    if ($line -match $ExpectedVersion) { Write-Output "  [PASS] MD version OK" }
    else { $warnings += ("MD header mismatch: " + $line) }
} else { $errors += ("MD file not found: " + $mdFile) }
if (Test-Path $docxFile) {
    $size = [math]::Round((Get-Item $docxFile).Length/1024, 1)
    if ($size -gt 2) { Write-Output ("  [PASS] DOCX exists: " + $size + " KB") }
    else { $errors += "DOCX file too small" }
    [System.Reflection.Assembly]::LoadWithPartialName("System.IO.Compression.FileSystem") | Out-Null
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($docxFile)
        $entry = $zip.GetEntry("word/document.xml")
        if ($entry -and $entry.Length -gt 100) {
            $reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
            $xml = $reader.ReadToEnd(); $reader.Dispose()
            if ($xml -match [System.Text.RegularExpressions.Regex]::Escape($ExpectedVersion)) {
                Write-Output ("  [PASS] DOCX contains version: " + $ExpectedVersion)
            } else { $warnings += "Version not found in DOCX body" }
            if ($xml -match "v1.1" -and $xml -match "v1.0") {
                Write-Output "  [PASS] DOCX version history includes v1.1, v1.0"
            } else { $warnings += "Version history incomplete in DOCX" }
        } else { $errors += "DOCX missing word/document.xml" }
        $zip.Dispose()
    } catch { $errors += ("DOCX verify failed: " + $_) }
} else { $errors += ("DOCX not found: " + $docxFile) }
$changelog = Join-Path $BaseDir ($DocName + "_CHANGELOG.md")
if (Test-Path $changelog) { Write-Output "  [PASS] CHANGELOG exists" }
else { $warnings += "CHANGELOG not found" }
Write-Output "--------------------------------------------"
if ($errors.Count -eq 0) { Write-Output "  RESULT: ALL PASS" }
else { Write-Output ("  RESULT: " + $errors.Count + " ERRORS"); foreach ($e in $errors) { Write-Output "    ERROR: $e" } }
foreach ($w in $warnings) { Write-Output "    WARN: $w" }
if ($errors.Count -gt 0) { exit 1 } else { exit 0 }