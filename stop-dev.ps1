# Остановка прототипа: backend (8000) и frontend (5173). Контейнеры оставляет
# работать (данные в них сохраняются в любом случае); остановить и их:
#   powershell -ExecutionPolicy Bypass -File .\stop-dev.ps1 -Containers
param([switch]$Containers)
Set-Location $PSScriptRoot

foreach ($port in 8000, 5173) {
    $pids = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    if ($pids) {
        $pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
        Write-Host "Остановлен процесс на порту $port"
    } else {
        Write-Host "На порту $port ничего не запущено"
    }
}

if ($Containers) {
    docker compose stop
    Write-Host "Контейнеры остановлены (данные сохранены)"
}
