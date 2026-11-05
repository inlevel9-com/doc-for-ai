#Requires -Version 7.4
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
Set-Location (Split-Path $PSScriptRoot -Parent)

& $Python -c "import platform, sys; sys.exit(0 if sys.platform == 'win32' and platform.machine().lower() == 'amd64' and sys.version_info[:2] == (3, 12) else 'Windows x64 Python 3.12 is required')"

# Start clean so the bundle cannot pick up packages from the developer environment.
& $Python -m venv --clear build\venv
$BuildPython = ".\build\venv\Scripts\python.exe"
$PipOptions = @("--disable-pip-version-check")
if (Test-Path wheelhouse -PathType Container) {
    $PipOptions += @("--no-index", "--find-links", "wheelhouse")
}
& $BuildPython -m pip install @PipOptions ".[build]"

& $BuildPython -m PyInstaller scripts\docforai.spec --noconfirm --distpath dist --workpath build\pyinstaller
$Bundle = "dist\docforai"
Copy-Item LICENSE, README.md, docs\usage.txt $Bundle
Copy-Item docs $Bundle -Recurse
& $BuildPython scripts\collect-licenses.py "$Bundle\licenses"
New-Item -ItemType Directory -Force "$Bundle\tools" | Out-Null
Set-Content "$Bundle\tools\README.txt" "See docs/OFFLINE.md for optional LibreOffice support."

$Version = & $BuildPython -c "from importlib.metadata import version; print(version('docforai'))"
$Archive = "dist\docforai-v${Version}-windows-x64.zip"
Compress-Archive -Path $Bundle -DestinationPath $Archive -Force
Write-Host "Built $Archive"
