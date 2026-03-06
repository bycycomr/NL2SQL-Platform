# ============================================================
# NL2SQL - AI Backend Baslat
# Kullanim: .\scripts\Start-AIBackend.ps1
# ============================================================

$RootDir    = Split-Path -Parent $PSScriptRoot
$VenvPath   = "$RootDir\.venv"
$BackendDir = "$RootDir\ai-backend"

function Write-OK($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Write-ERR($m)  { Write-Host "  [XX] $m" -ForegroundColor Red }
function Write-INFO($m) { Write-Host "  [>>] $m" -ForegroundColor Cyan }

Write-Host ""
Write-Host "=== NL2SQL AI Backend ===" -ForegroundColor Cyan

# 1. Python kontrolu
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-ERR "Python bulunamadi! https://www.python.org/downloads (3.10+)"
    exit 1
}
Write-OK "Python: $(python --version)"

# 2. Venv
if (-not (Test-Path "$VenvPath\Scripts\Activate.ps1")) {
    Write-INFO ".venv olusturuluyor..."
    python -m venv $VenvPath
}
Write-OK ".venv aktif ediliyor..."
& "$VenvPath\Scripts\Activate.ps1"

# 3. Bagimliliklar
Write-INFO "Bagimliliklar kontrol ediliyor..."
python -m pip install -r "$BackendDir\requirements.txt" -q --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Write-ERR "pip install basarisiz!"; exit 1 }
Write-OK "Bagimliliklar hazir."

# 4. .env kontrolu
if (-not (Test-Path "$RootDir\.env")) {
    Write-INFO ".env bulunamadi, .env.example kopyalaniyor..."
    Copy-Item "$RootDir\.env.example" "$RootDir\.env"
    Write-OK ".env olusturuldu: $RootDir\.env"
}

Get-Content "$RootDir\.env" | Where-Object { $_ -match "^\s*[^#].+=.+" } | ForEach-Object {
    $parts = $_ -split "=", 2
    [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
}
Write-OK ".env yuklendi."

# 5. Baslat
Write-Host ""
Write-Host "  --------------------------------------------" -ForegroundColor DarkGray
Write-OK "AI Backend : http://localhost:8000"
Write-OK "Swagger UI : http://localhost:8000/docs"
Write-OK "ReDoc      : http://localhost:8000/redoc"
Write-Host "  --------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Durdurmak icin Ctrl+C" -ForegroundColor Yellow
Write-Host ""

Set-Location $BackendDir

# Sunucu hazir olunca tarayiciyi ac
$null = Start-Job -ScriptBlock {
    $elapsed = 0
    while ($elapsed -lt 30) {
        Start-Sleep -Seconds 1
        $elapsed++
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            Start-Process "http://localhost:8000/docs"
            break
        } catch {}
    }
}

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
