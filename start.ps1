param(
    [Parameter(Mandatory=$false)]
    [string]$Action = "menu"
)

$scriptPath = $PSScriptRoot
$pidFile = "$scriptPath\server.pid"
$port = 5001

function Get-LanIP {
    $adapters = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Manual, Dhcp | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }
    $addresses = @()
    foreach ($adapter in $adapters) {
        $addresses += $adapter.IPAddress
    }
    if ($addresses.Count -eq 0) {
        $addresses = @("localhost")
    }
    return $addresses
}

function Show-Menu {
    Clear-Host
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "  Film Price Tracker" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  [S] Start Server (Foreground)" -ForegroundColor Gray
    Write-Host "  [B] Start Server (Background)" -ForegroundColor Gray
    Write-Host "  [T] Stop Server" -ForegroundColor Gray
    Write-Host "  [C] Check Status" -ForegroundColor Gray
    Write-Host "  [Q] Quit" -ForegroundColor Gray
    Write-Host ""
    $choice = Read-Host "Enter option (S/B/T/C/Q)"
    return $choice.ToUpper()
}

function Test-Python {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-Host "[ERROR] Python not found" -ForegroundColor Red
        return $false
    }
    return $true
}

function Setup-Environment {
    Write-Host "[1/3] Virtual environment..." -NoNewline
    if (-not (Test-Path "$scriptPath\venv")) {
        python -m venv venv 2>$null
        Write-Host " Created" -ForegroundColor Green
    } else {
        Write-Host " Exists" -ForegroundColor Green
    }

    & "$scriptPath\venv\Scripts\Activate.ps1" 2>$null

    Write-Host "[2/3] Installing dependencies..." -NoNewline
    pip install -r "$scriptPath\requirements.txt" --quiet --disable-pip-version-check 2>$null
    Write-Host " Done" -ForegroundColor Green

    Write-Host "[3/3] Checking OCR..." -NoNewline
    python -c "from rapidocr_onnxruntime import RapidOCR" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " Ready" -ForegroundColor Green
    } else {
        Write-Host " Not installed" -ForegroundColor Yellow
    }
}

function Start-Server([bool]$Background = $false) {
    if (-not (Test-Python)) {
        Write-Host "Press any key to continue..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        return
    }

    if (Test-Path $pidFile) {
        $oldPid = (Get-Content $pidFile -Raw).Trim()
        if ([int]::TryParse($oldPid, [ref]$null) -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
            $lanIPs = Get-LanIP
            Write-Host ""
            Write-Host "Server already running (PID: $oldPid)" -ForegroundColor Yellow
            Write-Host "Local:    http://localhost:$port" -ForegroundColor White
            foreach ($ip in $lanIPs) {
                Write-Host "Network:  http://$ip`:$port" -ForegroundColor White
            }
            Write-Host ""
            Write-Host "Press any key to continue..."
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            return
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Setup-Environment

    $lanIPs = Get-LanIP
    Write-Host ""
    Write-Host "Starting Flask server..." -ForegroundColor Yellow

    if ($Background) {
        $process = Start-Process -FilePath "python" -ArgumentList "app.py" -WorkingDirectory $scriptPath -WindowStyle Hidden -PassThru
    } else {
        $process = Start-Process -FilePath "python" -ArgumentList "app.py" -WorkingDirectory $scriptPath -NoNewWindow -PassThru
    }

    $process.Id | Out-File -FilePath $pidFile -Encoding UTF8
    Start-Sleep -Seconds 2

    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
        Write-Host "Server started!" -ForegroundColor Green
        Write-Host "PID: $($process.Id)" -ForegroundColor White
        Write-Host "Local:    http://localhost:$port" -ForegroundColor White
        foreach ($ip in $lanIPs) {
            Write-Host "Network:  http://$ip`:$port" -ForegroundColor White
        }
        Write-Host ""
        if ($Background) {
            Write-Host "Running in background" -ForegroundColor Gray
            Write-Host "Stop: .\start.ps1 -Action stop" -ForegroundColor Gray
        } else {
            Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
        }
        Write-Host ""
        if (-not $Background) {
            Write-Host "Press any key to exit..."
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        }
    } else {
        Write-Host "Failed to start" -ForegroundColor Red
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        Write-Host ""
        Write-Host "Press any key to continue..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    }
}

function Stop-Server {
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "Stopping server..." -ForegroundColor Yellow
    Write-Host "======================================" -ForegroundColor Cyan

    if (-not (Test-Path $pidFile)) {
        Write-Host "PID file not found" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Press any key to continue..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        return
    }

    $serverPid = (Get-Content $pidFile -Raw).Trim()

    if (-not [int]::TryParse($serverPid, [ref]$null)) {
        Write-Host "Invalid PID" -ForegroundColor Red
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        Write-Host ""
        Write-Host "Press any key to continue..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        return
    }

    $process = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
    if ($process) {
        $process.Kill()
        Start-Sleep -Seconds 1
        Write-Host "Stopped (PID: $serverPid)" -ForegroundColor Green
    } else {
        Write-Host "Process not found" -ForegroundColor Yellow
    }

    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Press any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Get-Status {
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "Server Status" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host ""

    $lanIPs = Get-LanIP

    if (Test-Path $pidFile) {
        $serverPid = (Get-Content $pidFile -Raw).Trim()
        if ([int]::TryParse($serverPid, [ref]$null) -and (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) {
            Write-Host "Status:   Running" -ForegroundColor Green
            Write-Host "PID:      $serverPid" -ForegroundColor White
            Write-Host "Local:    http://localhost:$port" -ForegroundColor White
            foreach ($ip in $lanIPs) {
                Write-Host "Network:  http://$ip`:$port" -ForegroundColor White
            }
        } else {
            Write-Host "Status:   Stopped (stale PID file)" -ForegroundColor Yellow
            Remove-Item $pidFile -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "Status:   Stopped" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "Press any key to continue..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Run-Menu {
    do {
        $choice = Show-Menu
        switch ($choice) {
            "S" { Start-Server }
            "B" { Start-Server -Background $true }
            "T" { Stop-Server }
            "C" { Get-Status }
            "Q" { Write-Host "Exiting..." -ForegroundColor Gray; exit }
            default {
                Write-Host "Invalid option" -ForegroundColor Red
                Start-Sleep -Seconds 1
            }
        }
    } while ($choice -ne "Q")
}

switch ($Action.ToLower()) {
    "start"    { Start-Server }
    "start-bg" { Start-Server -Background $true }
    "stop"     { Stop-Server }
    "status"   { Get-Status }
    "menu"     { Run-Menu }
    default {
        Write-Host "Usage:" -ForegroundColor Cyan
        Write-Host "  .\start.ps1                  # Show menu" -ForegroundColor White
        Write-Host "  .\start.ps1 -Action start    # Foreground" -ForegroundColor White
        Write-Host "  .\start.ps1 -Action start-bg # Background" -ForegroundColor White
        Write-Host "  .\start.ps1 -Action stop     # Stop" -ForegroundColor White
        Write-Host "  .\start.ps1 -Action status   # Status" -ForegroundColor White
    }
}
