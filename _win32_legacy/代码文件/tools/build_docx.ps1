# Unified MD->DOCX converter — single authoritative entry point
# Called by per-module thin wrappers
param(
    [Parameter(Mandatory=$true)] [string]$MdFile,
    [Parameter(Mandatory=$true)] [string]$DocxFile,
    [string]$Title = ""
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

$converter = Join-Path $PSScriptRoot "md_to_docx.py"
if (-not (Test-Path $MdFile)) { Write-Error "Not found: $MdFile"; exit 1 }
python $converter $MdFile $DocxFile $Title
Write-Host "Done: $DocxFile"
