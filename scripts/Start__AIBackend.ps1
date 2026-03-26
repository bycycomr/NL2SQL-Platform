#Requires -Version 5.1
<#
.SYNOPSIS
    NL2SQL AI Backend'i başlatır.

.PARAMETER Mode
    Çalıştırma modu: dev (varsayılan) veya prod.
    - dev:  uvicorn --reload  (hot-reload, tek worker)
    - prod: gunicorn -c gunicorn.conf.py (çok worker, production ayarları)

.PARAMETER Port
    Dinlenecek port. Varsayılan: 8000.

.PARAMETER SkipInstall
    Bağımlılık kurulumunu atla.

.EXAMPLE
    .\Start__AIBackend.ps1
    .\Start__AIBackend.ps1 -Mode prod
    .\Start__AIBackend.ps1 -Mode dev -Port 8080 -SkipInstall
#>
param(
    [ValidateSet("dev", "prod")]
    [string]$Mode = "dev",

    [int]$Port = 8000,

    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackendDir  = Join-Path $ProjectRoot "ai-backend"

# ─── Renkli çıktı yardımcıları ───────────────────────────────────────────────
function Write-Step  { param($msg) Write-Host "`n>>> $msg" -ForegroundColor Cyan   }
function Write-Ok    { param($msg) Write-Host "    [OK] $msg"  -ForegroundColor Green  }
function Write-Warn  { param($msg) Write-Host "    [!!] $msg"  -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "    [XX] $msg"  -ForegroundColor Red; exit 1 }

# ─── 1. Backend dizini ───────────────────────────────────────────────────────
Write-Step "AI Backend dizinine geçiliyor: $BackendDir"
if (-not (Test-Path $BackendDir)) {
    Write-Fail "ai-backend dizini bulunamadı: $BackendDir"
}
Set-Location $BackendDir
Write-Ok "Dizin: $(Get-Location)"

# ─── 2. Python kontrolü ──────────────────────────────────────────────────────
Write-Step "Python kontrolü"
$pythonCmd = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.") {
            $pythonCmd = $cmd
            Write-Ok "$ver ($cmd)"
            break
        }
    } catch { }
}
if (-not $pythonCmd) { Write-Fail "Python 3 bulunamadı. Lütfen Python 3.10+ yükleyin." }

# ─── 3. Sanal ortam ──────────────────────────────────────────────────────────
Write-Step "Sanal ortam (venv) kontrolü"
$VenvDir    = Join-Path $BackendDir ".venv"
$VenvPython = if ($IsWindows -or $env:OS -eq "Windows_NT") {
    Join-Path $VenvDir "Scripts\python.exe"
} else {
    Join-Path $VenvDir "bin/python"
}

if (-not (Test-Path $VenvPython)) {
    Write-Warn ".venv bulunamadı — oluşturuluyor..."
    & $pythonCmd -m venv .venv
    Write-Ok ".venv oluşturuldu"
} else {
    Write-Ok ".venv mevcut"
}

# ─── 4. Bağımlılıklar ────────────────────────────────────────────────────────
if (-not $SkipInstall) {
    Write-Step "Bağımlılıklar kuruluyor (requirements.txt)"
    $ReqFile = Join-Path $BackendDir "requirements.txt"
    if (-not (Test-Path $ReqFile)) {
        Write-Warn "requirements.txt bulunamadı — kurulum atlanıyor"
    } else {
        & $VenvPython -m pip install --quiet --upgrade pip
        & $VenvPython -m pip install --quiet -r $ReqFile
        Write-Ok "Bağımlılıklar hazır"
    }
} else {
    Write-Warn "Bağımlılık kurulumu atlandı (-SkipInstall)"
}

# ─── 5. .env dosyası ─────────────────────────────────────────────────────────
Write-Step ".env dosyası kontrolü"
$EnvFile = Join-Path $BackendDir ".env"
if (-not (Test-Path $EnvFile)) {
    $EnvExample = Join-Path $BackendDir ".env.example"
    if (Test-Path $EnvExample) {
        Write-Warn ".env bulunamadı — .env.example'dan kopyalanıyor"
        Copy-Item $EnvExample $EnvFile
        Write-Warn "Lütfen $EnvFile dosyasını düzenleyip değişkenleri ayarlayın!"
    } else {
        Write-Warn ".env ve .env.example bulunamadı — varsayılan ayarlar kullanılacak"
    }
} else {
    Write-Ok ".env mevcut"
}

# ─── 6. Çalıştır ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=========================================" -ForegroundColor Magenta
Write-Host "  NL2SQL AI Backend — MOD: $($Mode.ToUpper())" -ForegroundColor Magenta
Write-Host "  Port: $Port" -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Magenta
Write-Host ""

if ($Mode -eq "dev") {
    Write-Step "uvicorn ile geliştirme sunucusu başlatılıyor (hot-reload)..."
    Write-Host "  Docs  : http://localhost:$Port/docs" -ForegroundColor DarkCyan
    Write-Host "  Health: http://localhost:$Port/health" -ForegroundColor DarkCyan
    Write-Host ""
    & $VenvPython -m uvicorn main:app --reload --host 0.0.0.0 --port $Port
} else {
    # Gunicorn Windows'ta çalışmaz — Linux/Mac için prod modu
    $GunicornConf = Join-Path $BackendDir "gunicorn.conf.py"
    $gunicornExe  = if ($IsWindows -or $env:OS -eq "Windows_NT") {
        Join-Path $VenvDir "Scripts\gunicorn"
    } else {
        Join-Path $VenvDir "bin/gunicorn"
    }

    if ($env:OS -eq "Windows_NT" -or $IsWindows) {
        Write-Warn "Gunicorn Windows'ta desteklenmez."
        Write-Warn "Prod modu için WSL, Docker veya Linux kullanın."
        Write-Warn "Uvicorn (çok worker) ile devam ediliyor..."
        Write-Host ""
        $workers = [math]::Max(2, [Environment]::ProcessorCount / 2)
        & $VenvPython -m uvicorn main:app --host 0.0.0.0 --port $Port --workers $workers
    } else {
        Write-Step "gunicorn ile production sunucu başlatılıyor..."
        Write-Host "  Docs  : http://localhost:$Port/docs" -ForegroundColor DarkCyan
        Write-Host "  Health: http://localhost:$Port/health" -ForegroundColor DarkCyan
        Write-Host ""
        & $gunicornExe -c $GunicornConf main:app
    }
}
