$files = @(
    (Join-Path $PSScriptRoot "shared\pipeline-auth.ps1"),
    (Join-Path $PSScriptRoot "..\pipeline_active.json")
)
foreach ($path in $files) {
    $resolved = Resolve-Path $path -ErrorAction SilentlyContinue
    if (-not $resolved) { Write-Host "SKIP: $path"; continue }
    $content = [System.IO.File]::ReadAllText($resolved.Path, [System.Text.Encoding]::UTF8)
    $utf8bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($resolved.Path, $content, $utf8bom)
    Write-Host "BOM added: $($resolved.Path)"
}
