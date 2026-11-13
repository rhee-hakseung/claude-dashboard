# Build dist\claude-dashboard-<date>.zip for another PC: source + icon + installer, no .venv or caches.
# The zip holds one folder "dev-dashboard"; unzip it anywhere and run install.cmd inside it.
# No Korean literals in this file: PowerShell 5.1 misreads them in .ps1 scripts.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$stage = Join-Path $env:TEMP ("dd-build-" + [guid]::NewGuid().ToString("N"))
$pkg = Join-Path $stage "dev-dashboard"
New-Item -ItemType Directory -Force (Join-Path $pkg "tests"), (Join-Path $pkg "web") | Out-Null
try {
    $top = @("*.py", "dashboard.ico", "requirements.txt", "README.md", "LICENSE",
             "install.ps1", "install.cmd", "install.sh", "run-dashboard.ps1")
    foreach ($pat in $top) { Copy-Item (Join-Path $here $pat) $pkg }
    Copy-Item (Join-Path $here "tests\*.py") (Join-Path $pkg "tests")
    Copy-Item (Join-Path $here "web\*") (Join-Path $pkg "web")   # the web UI: html / css / js
    $dist = Join-Path $here "dist"
    New-Item -ItemType Directory -Force $dist | Out-Null
    $zip = Join-Path $dist ("claude-dashboard-" + (Get-Date -Format "yyyyMMdd") + ".zip")
    if (Test-Path $zip) { Remove-Item $zip }
    Compress-Archive -Path $pkg -DestinationPath $zip
    $n = (Get-ChildItem $pkg -Recurse -File).Count
    Write-Host ("Built {0}  ({1} files, {2:N0} KB)" -f $zip, $n, ((Get-Item $zip).Length / 1KB))
} finally {
    Remove-Item -Recurse -Force $stage
}
