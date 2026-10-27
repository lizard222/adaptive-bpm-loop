# Запуск прототипа для работы в браузере: контейнеры + backend + frontend.
# Запуск (из папки adaptive-bpm-loop):
#   powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
# Открывает два окна (backend и frontend — их не закрывать, пока работаете)
# и браузер на http://localhost:5173. Остановить всё: .\stop-dev.ps1
# Не "Stop": Windows PowerShell 5.1 считает ошибкой любой вывод docker в stderr
# (даже "Container Running"). Ошибки ловим явно — по $LASTEXITCODE и throw.
$ErrorActionPreference = "Continue"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)   # кириллица в SQL-файлах при передаче в psql
$root = $PSScriptRoot
Set-Location $root

function Test-Port([int]$port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Until([scriptblock]$check, [int]$seconds, [string]$what) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while (-not (& $check)) {
        if ((Get-Date) -gt $deadline) { throw "Не дождался: $what (за $seconds с)" }
        Start-Sleep -Seconds 2
    }
}

# 1. Docker Desktop
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "1/5 Docker Desktop не запущен — запускаю (до 3 минут)..."
    Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    Wait-Until { docker info *> $null; $LASTEXITCODE -eq 0 } 180 "Docker Desktop"
}
Write-Host "1/5 Docker работает"

# 2. Контейнеры: PostgreSQL, Redis, Prosody (XMPP для агентов)
docker compose up -d *> $null
if ($LASTEXITCODE -ne 0) { throw "docker compose up не удался — запустите 'docker compose up -d' вручную, чтобы увидеть ошибку" }
Wait-Until { docker compose exec -T postgres pg_isready -U abl -d abl *> $null; $LASTEXITCODE -eq 0 } 60 "PostgreSQL"
Write-Host "2/5 Контейнеры подняты"

# 3. Миграции. На новой базе Postgres накатывает db/init сам, но на уже
# существующей таблицы из новых файлов не появятся. Все файлы идемпотентны
# (IF NOT EXISTS), поэтому накатываем каждый раз.
Get-ChildItem "$root\db\init\*.sql" | Sort-Object Name | ForEach-Object {
    Get-Content $_.FullName -Raw -Encoding UTF8 |
        docker compose exec -T -e PGOPTIONS="-c client_min_messages=warning" postgres psql -q -v ON_ERROR_STOP=1 -U abl -d abl *> $null
    if ($LASTEXITCODE -ne 0) { throw "Ошибка миграции $($_.Name)" }
}
Write-Host "3/5 Схема базы актуальна"

$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }

# 4. Backend (FastAPI, порт 8000). Внутри него — фоновая проверка таймеров:
# без запущенного backend напоминания и эскалации не срабатывают.
if (Test-Port 8000) {
    Write-Host "4/5 Backend уже запущен (порт 8000)"
} else {
    Start-Process $shell -WorkingDirectory $root -ArgumentList @(
        "-NoExit", "-Command",
        "`$Host.UI.RawUI.WindowTitle = 'adaptive-bpm-loop: backend :8000'; `$env:PYTHONIOENCODING = 'utf-8'; python -m uvicorn api.main:app --port 8000"
    )
    Wait-Until { try { (Invoke-RestMethod http://localhost:8000/health -TimeoutSec 2).api -eq "ok" } catch { $false } } 60 "backend"
    Write-Host "4/5 Backend запущен: http://localhost:8000"
}

# 5. Frontend (Vite, порт 5173)
if (Test-Port 5173) {
    Write-Host "5/5 Frontend уже запущен (порт 5173)"
} else {
    Start-Process $shell -WorkingDirectory "$root\web" -ArgumentList @(
        "-NoExit", "-Command",
        "`$Host.UI.RawUI.WindowTitle = 'adaptive-bpm-loop: frontend :5173'; npm run dev"
    )
    Wait-Until { Test-Port 5173 } 60 "frontend"
    Write-Host "5/5 Frontend запущен"
}

Start-Process "http://localhost:5173"
Write-Host ""
Write-Host "Готово: http://localhost:5173  (логин = пароль: secretary, supervisor, normcontrol, student, dept_head, admin)"
Write-Host "Остановить: powershell -ExecutionPolicy Bypass -File .\stop-dev.ps1"
