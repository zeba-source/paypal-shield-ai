[CmdletBinding()]
param(
    [switch]$NoProducer,
    [switch]$NoConsumer
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$KafkaRoot = "C:\kafka\kafka"
$Python = Join-Path $ProjectRoot "..\.venv\Scripts\python.exe"
$StateFile = Join-Path $ProjectRoot ".fintech-processes.json"

function Test-PortOpen {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-ForPort {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen $Port) { return }
        Start-Sleep -Seconds 1
    }
    throw "Timed out after $TimeoutSeconds seconds waiting for port $Port. Check the Kafka/ZooKeeper window and logs."
}

function Start-Window {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )
    $windowCommand = "`$host.UI.RawUI.WindowTitle='$Title'; Set-Location -LiteralPath '$WorkingDirectory'; $Command"
    return Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $windowCommand) -PassThru
}

if (-not (Test-Path $Python)) {
    throw "Virtual environment Python was not found at $Python"
}
if (-not $NoConsumer -and -not $NoProducer -and -not (Test-Path $KafkaRoot)) {
    throw "Kafka installation was not found at $KafkaRoot"
}

$tracked = @()
if (-not $NoConsumer -and -not $NoProducer -and -not (Test-PortOpen 2181)) {
    $zk = Start-Window "FinTech ZooKeeper" $KafkaRoot ".\bin\windows\zookeeper-server-start.bat .\config\zookeeper.properties"
    $tracked += @{ title = "FinTech ZooKeeper"; pid = $zk.Id }
} else {
    Write-Host "ZooKeeper already listening on port 2181."
}
if (-not $NoConsumer -and -not $NoProducer) { Wait-ForPort 2181 }

if (-not $NoConsumer -and -not $NoProducer -and -not (Test-PortOpen 9092)) {
    $kafkaCommand = "`$env:KAFKA_HEAP_OPTS='-Xmx1G -Xms1G'; .\bin\windows\kafka-server-start.bat .\config\server.properties"
    $kafka = Start-Window "FinTech Kafka" $KafkaRoot $kafkaCommand
    $tracked += @{ title = "FinTech Kafka"; pid = $kafka.Id }
} else {
    Write-Host "Kafka already listening on port 9092."
}
if (-not $NoConsumer -and -not $NoProducer) { Wait-ForPort 9092 }

Push-Location $ProjectRoot
try {
    & $Python setup_db.py
    if ($LASTEXITCODE -ne 0) { throw "setup_db.py failed with exit code $LASTEXITCODE" }
    if (-not $NoConsumer -and -not $NoProducer) {
        & $Python ensure_topics.py
        if ($LASTEXITCODE -ne 0) { throw "ensure_topics.py failed with exit code $LASTEXITCODE" }
    }

    $api = Start-Window "FinTech API" $ProjectRoot "& '$Python' -m uvicorn api.main:app --port 8000"
    $tracked += @{ title = "FinTech API"; pid = $api.Id }
    if (-not $NoConsumer) {
        $consumer = Start-Window "FinTech Risk Consumer" $ProjectRoot "& '$Python' -u risk_consumer.py"
        $tracked += @{ title = "FinTech Risk Consumer"; pid = $consumer.Id }
    } else { Write-Host "Risk consumer skipped." }
    $frontend = Start-Window "FinTech Frontend" (Join-Path $ProjectRoot "frontend") "npm run dev"
    $tracked += @{ title = "FinTech Frontend"; pid = $frontend.Id }
    $dashboard = Start-Window "FinTech Dashboard" $ProjectRoot "& '$Python' -m streamlit run dashboard.py --server.headless true"
    $tracked += @{ title = "FinTech Dashboard"; pid = $dashboard.Id }
    if (-not $NoProducer -and -not $NoConsumer) {
        $producer = Start-Window "FinTech Producer" $ProjectRoot "& '$Python' producer.py --delay 0.05"
        $tracked += @{ title = "FinTech Producer"; pid = $producer.Id }
    } else {
        Write-Host "Producer skipped because -NoProducer was supplied."
    }
} finally {
    Pop-Location
}

$tracked | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
Write-Host ""
Write-Host "FinTech services started."
Write-Host "Dashboard: http://localhost:8501"
Write-Host "Frontend: http://localhost:3000"
Write-Host "API docs:  http://localhost:8000/docs"
Write-Host "Stop with: .\stop_all.ps1"
