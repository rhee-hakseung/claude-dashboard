# Launch dev-dashboard with the project venv (never the PATH python, which may be the Store stub).
# No Korean literals in this file: PowerShell 5.1 misreads them in .ps1 scripts.
$env:PYTHONDONTWRITEBYTECODE = "1"
# Drop Claude Code session markers if this launcher itself runs inside a Claude session;
# otherwise sessions started from the dashboard would treat themselves as child sessions.
Get-ChildItem Env: | Where-Object { $_.Name -like "CLAUDE_CODE_*" -or $_.Name -eq "CLAUDECODE" -or $_.Name -eq "CLAUDE_PID" } |
    ForEach-Object { Remove-Item ("Env:" + $_.Name) }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) {
    Write-Error "venv not found: $pyw  (run install.cmd in this folder first)"
    exit 1
}
& $pyw (Join-Path $root "app.py")
