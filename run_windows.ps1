# Playlist FLAC Manager - Windows launcher
# Usage: right-click -> "Run with PowerShell", or from a PowerShell prompt:
#   .\run_windows.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$venv = Join-Path $backend ".venv"

if (-not (Test-Path $venv)) {
    Write-Host "Creating virtual environment..."
    python -m venv $venv
}

$python = Join-Path $venv "Scripts\python.exe"
$pip = Join-Path $venv "Scripts\pip.exe"

Write-Host "Installing dependencies..."
& $pip install -q -r (Join-Path $backend "requirements.txt")

$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"
if (-not (Test-Path $envFile)) {
    Write-Host "No .env found - copying .env.example. Edit .env with your slskd/Spotify settings before importing playlists."
    Copy-Item $envExample $envFile
}

Write-Host "Starting Playlist FLAC Manager on http://127.0.0.1:8000 ..."
Push-Location $backend
try {
    Start-Process "http://127.0.0.1:8000"
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
