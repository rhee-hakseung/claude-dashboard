# Install Claude dashboard on this PC: venv + packages + project root + desktop shortcut.
# Run from the cloned or unzipped folder (double-click install.cmd, or: powershell -ExecutionPolicy Bypass -File install.ps1).
# Safe to run again: it reuses a working .venv, updates packages, and rewrites the shortcut.
# No Korean literals in this file: PowerShell 5.1 misreads them in .ps1 scripts.
param(
    [string]$DevRoot,          # folder whose direct subfolders are your projects (default C:\dev)
    [switch]$NoShortcut,
    [string]$ShortcutPath      # default: Desktop\Claude dashboard.lnk
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONDONTWRITEBYTECODE = "1"

function Refresh-Path {
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("PATH", "User")
}

function Test-Python([string]$exe) {
    # True if $exe is a real Python >= 3.10 (the WindowsApps alias stub fails this).
    if (-not $exe -or -not (Test-Path $exe)) { return $false }
    try {
        $v = & $exe -c "import sys; print(int(sys.version_info >= (3, 10)))" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$v".Trim() -eq "1")
    } catch { return $false }
}

function Find-Python {
    $cands = @()
    foreach ($base in @("$env:LOCALAPPDATA\Programs\Python\Python3*", "$env:ProgramFiles\Python3*", "C:\Python3*")) {
        try {   # an unreadable folder must not abort the search
            $cands += Get-Item -Path (Join-Path $base "python.exe") -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
        } catch { }
    }
    foreach ($hive in @("HKCU:", "HKLM:")) {
        try {
            Get-ChildItem "$hive\SOFTWARE\Python\PythonCore" -ErrorAction SilentlyContinue |
                Sort-Object PSChildName -Descending | ForEach-Object {
                    $ip = (Get-ItemProperty (Join-Path $_.PSPath "InstallPath") -ErrorAction SilentlyContinue)
                    if ($ip -and $ip.ExecutablePath) { $cands += $ip.ExecutablePath }
                    elseif ($ip -and $ip.'(default)') { $cands += (Join-Path $ip.'(default)' "python.exe") }
                }
        } catch { }
    }
    try {
        $py = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($py) {
            $p = & $py.Source -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0) { $cands += "$p".Trim() }
        }
    } catch { }
    foreach ($c in $cands) {
        if ($c -notlike "*\WindowsApps\*" -and (Test-Python $c)) { return $c }
    }
    return $null
}

Write-Host "== Claude dashboard install ==  ($here)"

# 1) Python
Refresh-Path
$python = Find-Python
if (-not $python) {
    Write-Host "Python 3.10+ was not found."
    $ans = Read-Host "Install Python 3.13 now with winget? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
        Refresh-Path
        $python = Find-Python
    }
    if (-not $python) {
        Write-Error "Python not found. Install it (winget install -e --id Python.Python.3.13) and run this again."
        exit 1
    }
}
Write-Host "Python: $python"

# 2) venv (recreate if it was copied from another PC and no longer runs)
$venvPy = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Python $venvPy)) {
    if (Test-Path (Join-Path $here ".venv")) { Remove-Item -Recurse -Force (Join-Path $here ".venv") }
    Write-Host "Creating .venv ..."
    & $python -m venv (Join-Path $here ".venv")
    if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed"; exit 1 }
}
Write-Host "Installing packages ..."
& $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $here "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed"; exit 1 }

# 3) Project root folder
if (-not $DevRoot) {
    $DevRoot = Read-Host "Projects folder (each direct subfolder = one project) [C:\dev]"
    if (-not $DevRoot) { $DevRoot = "C:\dev" }
}
$DevRoot = $DevRoot.Trim().Trim('"')
if (-not (Test-Path -LiteralPath $DevRoot -PathType Container)) {
    Write-Error "Folder does not exist: $DevRoot"
    exit 1
}
$DevRoot = (Resolve-Path -LiteralPath $DevRoot).Path
Push-Location $here
try {
    & $venvPy -B -c "import sys, prefs; prefs.save_state(dev_root=sys.argv[1])" $DevRoot
    if ($LASTEXITCODE -ne 0) { Write-Error "could not save the projects folder"; exit 1 }
} finally { Pop-Location }
Write-Host "Projects folder: $DevRoot"

# 4) Desktop shortcut (same AppUserModelID as the app, so the taskbar shows the dashboard icon)
if (-not $NoShortcut) {
    $lnk = $ShortcutPath
    if (-not $lnk) { $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Claude dashboard.lnk" }
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $here ".venv\Scripts\pythonw.exe"
    $s.Arguments = "-B `"" + (Join-Path $here "app.py") + "`""
    $s.WorkingDirectory = $here
    $s.IconLocation = (Join-Path $here "dashboard.ico") + ",0"
    $s.Description = "Claude dashboard"
    $s.Save()
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class LnkAumid {
  [StructLayout(LayoutKind.Sequential, Pack = 4)]
  public struct PROPERTYKEY { public Guid fmtid; public uint pid; }
  [StructLayout(LayoutKind.Explicit)]
  public struct PROPVARIANT { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }
  [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPropertyStore {
    void GetCount(out uint c); void GetAt(uint i, out PROPERTYKEY k);
    void GetValue(ref PROPERTYKEY k, out PROPVARIANT v); void SetValue(ref PROPERTYKEY k, ref PROPVARIANT v);
    void Commit();
  }
  [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IPersistFile {
    void GetClassID(out Guid c); [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint m);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string f, bool r);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f); void GetCurFile(out IntPtr f);
  }
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class ShellLink {}
  public static void Set(string path, string id) {
    object link = new ShellLink();
    ((IPersistFile)link).Load(path, 2);
    PROPERTYKEY key = new PROPERTYKEY { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
    PROPVARIANT v = new PROPVARIANT { vt = 31, p = Marshal.StringToCoTaskMemUni(id) };
    IPropertyStore ps = (IPropertyStore)link;
    ps.SetValue(ref key, ref v); ps.Commit();
    ((IPersistFile)link).Save(path, true);
    Marshal.FreeCoTaskMem(v.p);
  }
}
"@
    [LnkAumid]::Set($lnk, "hakseung.ClaudeCodeDashboard")
    Write-Host "Shortcut: $lnk"
}

Write-Host ""
Write-Host "Done. Start it from the 'Claude dashboard' icon on the desktop."
Write-Host "To change the projects folder later: run install.ps1 again (or install.cmd)."
