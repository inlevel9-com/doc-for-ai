#Requires -Version 7.4
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
Set-Location (Split-Path $PSScriptRoot -Parent)

& $Python -c "import platform, sys; sys.exit(0 if sys.platform == 'win32' and platform.machine().lower() == 'amd64' and sys.version_info[:2] == (3, 12) else 'Windows x64 Python 3.12 is required')"

# Download wheels for the runtime, packaging tools, and isolated build backend.
$BuildRequirements = & $Python -c "import tomllib; print(*tomllib.loads(open('pyproject.toml', encoding='utf-8').read())['build-system']['requires'], sep=chr(10))"
& $Python -m pip wheel --only-binary=:all: --wheel-dir wheelhouse ".[build]" @BuildRequirements
Write-Host "Copy wheelhouse and the source tree to the offline build machine."
