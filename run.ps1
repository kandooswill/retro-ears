# Start retro-ears on Windows. Usage: powershell -ExecutionPolicy Bypass -File run.ps1 [-Update] [-NoBrowser]
param([switch]$Update, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) { $Py = "py"; $PyArgs = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $Py = "python"; $PyArgs = @() }
else { Write-Host "retro-ears needs Python 3.10 or newer: https://www.python.org/downloads/"; exit 1 }

& $Py @PyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Host "retro-ears needs Python 3.10 or newer."; exit 1 }

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "First run: setting up (this takes a minute)..."
    & $Py @PyArgs -m venv .venv
    & $VenvPython -m pip install --quiet --upgrade pip
}
if ($Update) { & $VenvPython -m pip install --upgrade "yt-dlp[default]" ytmusicapi }

& $VenvPython -m pip install --quiet -r requirements.txt
$AppArgs = @()
if ($NoBrowser) { $AppArgs += "--no-browser" }
& $VenvPython app.py @AppArgs
