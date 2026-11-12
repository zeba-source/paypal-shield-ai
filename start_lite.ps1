[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot "..\.venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Virtual environment Python was not found at $Python"
}

function Start-Window {
    param([string]$Title, [string]$WorkingDirectory, [string]$Command)
    $windowCommand = "`$host.UI.RawUI.WindowTitle='$Title'; Set-Location -LiteralPath '$WorkingDirectory'; $Command"
    return Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $windowCommand) -PassThru
}

Push-Location $ProjectRoot
try {
    & $Python setup_db.py
    if ($LASTEXITCODE -ne 0) { throw "setup_db.py failed with exit code $LASTEXITCODE" }
    $api = Start-Window "FinTech Lite API" $ProjectRoot "`$env:LITE_MODE='true'; & '$Python' -m uvicorn api.main:app --port 8000"
    $frontend = Start-Window "FinTech Lite Frontend" (Join-Path $ProjectRoot "frontend") "npm run dev"
} finally {
    Pop-Location
}

Write-Host "Lite mode started: MySQL + FastAPI + frontend only."
Write-Host "API:      http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:3000/shop"
Write-Host "Kafka, ZooKeeper, risk_consumer, producer, and Streamlit were not started."