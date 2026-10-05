# Builds CANedge Studio into a normal Windows program and installs it with Desktop + Start-menu
# shortcuts. Run once (right-click > Run with PowerShell) after changing the code.
#   needs: pip install pyinstaller pywebview asammdf numpy
$ErrorActionPreference = "Continue"   # PyInstaller logs to stderr; failures are caught via $LASTEXITCODE
$here = $PSScriptRoot
$project = (Resolve-Path "$here\..\..").Path
$csv = "$project\40_Experiments\data\csv\vw_meb_uds_pid_list.csv"
$work = Join-Path $env:TEMP "canedge_studio_build"
$install = Join-Path $env:LOCALAPPDATA "Programs\CANedge Studio"

Get-Process "CANedge Studio" -ErrorAction SilentlyContinue | Stop-Process -Force
Set-Location $here

# A private, minimal Python environment: only what the app imports. Building from the global
# Python would drag every installed package (torch, Qt, ...) into the program.
$venv = Join-Path $env:LOCALAPPDATA "canedge_studio_buildenv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
  python -m venv $venv
  & "$venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  & "$venv\Scripts\python.exe" -m pip install --quiet pyinstaller pywebview asammdf numpy
  if ($LASTEXITCODE -ne 0) { throw "Could not set up the build environment" }
}
& "$venv\Scripts\python.exe" -m PyInstaller "$here\app.py" --name "CANedge Studio" --windowed --noconfirm --clean `
  --icon "$here\icon.ico" `
  --add-data "$here\ui;ui" --add-data "${csv};." `
  --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide6 --exclude-module matplotlib `
  --exclude-module scipy --exclude-module tkinter --exclude-module IPython --exclude-module pytest `
  --workpath "$work\build" --specpath $work --distpath "$work\dist"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if (Test-Path $install) { Remove-Item $install -Recurse -Force }
Copy-Item "$work\dist\CANedge Studio" $install -Recurse

# Point the installed app at this project folder (configs + PID list live here).
$settings = Join-Path $env:APPDATA "CANedge Studio"
New-Item -ItemType Directory -Force $settings | Out-Null
$cfg = Join-Path $settings "settings.json"
$s = @{}
if (Test-Path $cfg) { (Get-Content $cfg -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $s[$_.Name] = $_.Value } }
$s["project"] = $project
$s | ConvertTo-Json | Set-Content $cfg -Encoding utf8

$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Desktop"), (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
  $lnk = $ws.CreateShortcut((Join-Path $dir "CANedge Studio.lnk"))
  $lnk.TargetPath = Join-Path $install "CANedge Studio.exe"
  $lnk.WorkingDirectory = $install
  $lnk.Description = "CANedge2 logger configs and MF4 log analysis (VW ID. Buzz thesis)"
  $lnk.Save()
}
Write-Host "Installed to $install - start it from the Desktop or Start menu: CANedge Studio"
