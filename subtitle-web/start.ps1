param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "subtitle-web\backend"
$FrontendDir = Join-Path $ProjectRoot "subtitle-web\frontend"
$PythonEmbed = Join-Path $ProjectRoot "python_embed\python.exe"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Subtitle Translator Web Service" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $PythonEmbed)) {
    Write-Host "[ERROR] Python not found: $PythonEmbed" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] Checking backend dependencies..." -ForegroundColor Yellow
$RequiredModules = @("fastapi", "uvicorn", "aiofiles", "pydantic")
foreach ($module in $RequiredModules) {
    $installed = & $PythonEmbed -c "import $module; print('OK')" 2>$null
    if ($installed -ne "OK") {
        Write-Host "  Installing: $module" -ForegroundColor Yellow
        & "$ProjectRoot\python_embed\Scripts\pip.exe" install $module --quiet
    } else {
        Write-Host "  $module OK" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "[2/3] Starting backend (FastAPI on port 8273)..." -ForegroundColor Yellow

$backendProcess = Start-Process -FilePath $PythonEmbed -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8273", "--reload" -WorkingDirectory $BackendDir -PassThru -NoNewWindow

Write-Host "  Backend PID: $backendProcess.Id" -ForegroundColor Cyan
Write-Host "  API Docs: http://localhost:8273/docs" -ForegroundColor Cyan
Write-Host ""

Start-Sleep -Seconds 3

$frontendProcess = $null
if (-not $SkipFrontend) {
    Write-Host "[3/3] Starting frontend (Vite on port 5173)..." -ForegroundColor Yellow
    $frontendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "pnpm", "dev" -WorkingDirectory $FrontendDir -PassThru -NoNewWindow
    Write-Host "  Frontend PID: $frontendProcess.Id" -ForegroundColor Cyan
    Write-Host "  Frontend URL: http://localhost:5173" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  Services started!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
Write-Host ""

while ($true) {
    Start-Sleep -Seconds 1

    if ($backendProcess.HasExited) {
        Write-Host ""
        Write-Host "[WARN] Backend exited with code: $($backendProcess.ExitCode)" -ForegroundColor Yellow
        break
    }

    if ($frontendProcess -and $frontendProcess.HasExited) {
        Write-Host ""
        Write-Host "[WARN] Frontend exited with code: $($frontendProcess.ExitCode)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Stopping services..." -ForegroundColor Yellow
if (-not $backendProcess.HasExited) {
    Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
}
if ($frontendProcess -and -not $frontendProcess.HasExited) {
    Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Done" -ForegroundColor Green
