[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("user", "staff")]
    [string]$Role,

    [string]$Port = "auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Mpremote {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & python -m mpremote @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "mpremote failed with exit code $LASTEXITCODE"
    }
}

$filesystem = Join-Path $PSScriptRoot "$Role\filesystem"
if (-not (Test-Path -LiteralPath $filesystem -PathType Container)) {
    throw "Missing filesystem directory: $filesystem"
}

Write-Host "WARNING: this erases the badge filesystem, including badge_state.json."
$confirmation = Read-Host "Type ERASE to provision a fresh $Role badge"
if ($confirmation -cne "ERASE") {
    throw "Provisioning cancelled."
}

$cleanup = @"
import os
def remove_tree(path):
    for entry in list(os.ilistdir(path)):
        child = path.rstrip('/') + '/' + entry[0]
        if entry[1] == 0x4000:
            remove_tree(child)
            os.rmdir(child)
        else:
            os.remove(child)
remove_tree('/')
"@
Invoke-Mpremote @("connect", $Port, "exec", $cleanup)

$root = (Resolve-Path -LiteralPath $filesystem).Path
$assets = Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object {
        $_.Extension -notin @(".py", ".pyc", ".mpy", ".json") -and
        $_.FullName -notmatch "[\\/](__pycache__|tests|\.pytest_cache)[\\/]"
    } |
    Sort-Object FullName

$directories = $assets | ForEach-Object DirectoryName | Sort-Object -Unique | Sort-Object Length
foreach ($directory in $directories) {
    $relative = $directory.Substring($root.Length).TrimStart("\")
    if (-not $relative) { continue }
    $remote = ":/" + ($relative -replace "\\", "/")
    try {
        Invoke-Mpremote @("connect", $Port, "fs", "mkdir", $remote)
    } catch {
        if ($_.Exception.Message -notmatch "exist") { throw }
    }
}

foreach ($asset in $assets) {
    $relative = $asset.FullName.Substring($root.Length).TrimStart("\")
    $remote = ":/" + ($relative -replace "\\", "/")
    Write-Host "Uploading $relative"
    Invoke-Mpremote @("connect", $Port, "fs", "cp", $asset.FullName, $remote)
}

Write-Host ""
Write-Host "Assets loaded."
