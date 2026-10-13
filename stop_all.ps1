$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateFile = Join-Path $ProjectRoot ".fintech-processes.json"

if (Test-Path $StateFile) {
    $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
    foreach ($entry in @($state)) {
        $process = Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping $($entry.title) (PID $($entry.pid))"
            Stop-Process -Id ([int]$entry.pid) -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
}

# Stop child interpreters whose command lines belong to this project.
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match 'risk_consumer\.py|producer\.py|uvicorn api\.main:app|streamlit run dashboard\.py'
} | ForEach-Object {
    Write-Host "Stopping Python process $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Stop the Next.js development server started by start_all.ps1.
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'next dev|next-server|frontend.*npm run dev|FinTech\\Fintech\\frontend'
} | ForEach-Object {
    Write-Host "Stopping frontend process $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Stop Kafka and ZooKeeper Java processes by their launcher command lines.
Get-CimInstance Win32_Process -Filter "Name = 'java.exe'" | Where-Object {
    $_.CommandLine -match 'kafka-server-start|kafka\.Kafka|QuorumPeerMain|zookeeper-server-start'
} | ForEach-Object {
    Write-Host "Stopping Kafka/ZooKeeper process $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Get-Process cmd -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -match 'FinTech (ZooKeeper|Kafka|API|Risk Consumer|Dashboard|Producer)'
} | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "FinTech services stopped."
