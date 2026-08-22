# Sakshi Microservices Local Windows Runner
# This script starts all four microservices in separate windows for easy local logging/debugging.

Write-Host "Stopping any existing processes on Sakshi ports (8001-8004)..." -ForegroundColor Yellow

$ports = @(8001, 8002, 8003, 8004)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conn) {
        $pid = $conn.OwningProcess
        Write-Host "Killing process PID $pid locking port $port..." -ForegroundColor Red
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
}

# Set env variables for local SQLite fallback execution
$env:DATABASE_URL = "sqlite:///./sakshi_db.db"

Write-Host "Starting Auth Service on port 8002..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "title Sakshi-Auth; .venv\Scripts\uvicorn.exe services.auth.main:app --port 8002 --reload"

Write-Host "Starting Reconciliation Service on port 8003..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "title Sakshi-Reconcile; .venv\Scripts\uvicorn.exe services.reconcile.main:app --port 8003 --reload"

Write-Host "Starting History Service on port 8004..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "title Sakshi-History; .venv\Scripts\uvicorn.exe services.history.main:app --port 8004 --reload"

Write-Host "Starting API Gateway on port 8001..." -ForegroundColor Green
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "title Sakshi-Gateway; .venv\Scripts\uvicorn.exe services.gateway.main:app --port 8001 --reload"

Write-Host "All services launched successfully!" -ForegroundColor Green
Write-Host "API Gateway & static UI is live at: http://127.0.0.1:8001" -ForegroundColor Cyan
