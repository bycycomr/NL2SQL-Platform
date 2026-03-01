# AI Backend – Deployment & Veritabanı Bağlantı Rehberi

Bu döküman yalnızca `ai-backend` servisini kapsar. Yerel geliştirme, Docker ile standalone çalıştırma ve hedef veritabanı bağlantılarını açıklar.

---

## İçindekiler

1. [Ön Koşullar](#1-ön-koşullar)
2. [Yerel Geliştirme (Docker olmadan)](#2-yerel-geliştirme-docker-olmadan)
3. [Docker ile Çalıştırma](#3-docker-ile-çalıştırma)
4. [Ortam Değişkenleri](#4-ortam-değişkenleri)
5. [Hedef Veritabanı Bağlantı Stringleri](#5-hedef-veritabanı-bağlantı-stringleri)
6. [API Kullanım Akışı](#6-api-kullanım-akışı)
7. [Sorun Giderme](#7-sorun-giderme)

---

## 1. Ön Koşullar

| Araç | Versiyon | Notlar |
|---|---|---|
| Python | 3.10+ | 3.11 önerilir |
| Ollama | 0.3+ | LLM sunucusu |
| Docker | 24+ | Sadece Docker ile çalıştırmak için |

**Ollama model indir (bir kez yapılır):**

```bash
ollama pull llama3.1:8b-instruct-q4_K_M
```

Ollama'nın çalıştığını doğrula:

```bash
curl http://localhost:11434/api/tags
```

---

## 2. Yerel Geliştirme (Docker olmadan)

```bash
# ai-backend klasörüne gir
cd ai-backend

# Virtual environment oluştur (ilk sefer)
python -m venv ../.venv

# Aktif et
../.venv\Scripts\activate          # Windows
# source ../.venv/bin/activate     # Linux / Mac

# Bağımlılıkları yükle
pip install -r requirements.txt

# Geliştirme sunucusunu başlat (--reload ile hot-reload)
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Sunucu başarıyla ayağa kalktığında:

```
INFO:     Uvicorn running on http://0.0.0.0:8001
INFO:     Application startup complete.
```

- **Swagger UI:** http://localhost:8001/docs
- **Health Check:** http://localhost:8001/health

> Ollama ayrı çalışıyor olmalı. Farklı bir terminalde `ollama serve` diyebilirsin.

---

## 3. Docker ile Çalıştırma

### 3.1 Dockerfile'daki Hatayı Düzelt (Zorunlu)

Mevcut `Dockerfile`'ın son satırında `app.main:app` yazıyor — bu hatalı.  
Uygulama `app/` alt klasörü olmadan kök dizinde çalışır, `main:app` olması gerekir.

`Dockerfile`'ı aç ve son `CMD` satırını değiştir:

```dockerfile
# YANLIŞ – container başlamaz:
CMD ["gunicorn", "app.main:app", ...]

# DOĞRU:
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "50", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

### 3.2 Image Build Et

```bash
# ai-backend/ klasöründen çalıştır
docker build -t nl2sql-ai-backend:latest .
```

### 3.3 Container'ı Çalıştır

```bash
docker run -d \
  --name nl2sql-ai-backend \
  -p 8001:8000 \
  -e LLM_BASE_URL=http://host.docker.internal:11434 \
  -e LLM_MODEL=llama3.1:8b-instruct-q4_K_M \
  -e CHROMA_PERSIST_DIR=/app/.chroma_data \
  -v nl2sql-chroma:/app/.chroma_data \
  nl2sql-ai-backend:latest
```

> **Not (Linux):** `host.docker.internal` Linux'ta varsayılan olarak çalışmaz.  
> Aşağıdaki şekilde çalıştır:
> ```bash
> docker run -d \
>   --add-host=host.docker.internal:host-gateway \
>   -e LLM_BASE_URL=http://host.docker.internal:11434 \
>   ...
> ```

### 3.4 Durumu Kontrol Et

```bash
docker logs nl2sql-ai-backend -f
docker inspect --format='{{.State.Health.Status}}' nl2sql-ai-backend
```

### 3.5 Durdur ve Temizle

```bash
docker stop nl2sql-ai-backend
docker rm nl2sql-ai-backend
docker volume rm nl2sql-chroma   # ChromaDB verisini de sil
```

---

## 4. Ortam Değişkenleri

Tüm değişkenler `core/config.py`'de tanımlıdır ve ortam değişkeni yoksa varsayılanı kullanır.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `LLM_MODEL` | `llama3.1:8b-instruct-q4_K_M` | Ollama model adı |
| `LLM_BASE_URL` | `http://localhost:11434` | Ollama sunucu adresi |
| `LLM_TEMPERATURE` | `0.0` | LLM sıcaklığı (0=deterministik) |
| `LLM_REQUEST_TIMEOUT` | `120` | Saniye cinsinden LLM zaman aşımı |
| `MAX_RETRY_COUNT` | `3` | SQL doğrulama başarısız olursa yeniden deneme sayısı |
| `CHROMA_PERSIST_DIR` | `.chroma_data` | ChromaDB vektör veritabanı dosya yolu |
| `DEBUG` | `false` | `true` yapılırsa DEBUG log seviyesi |

Yerel geliştirme için `ai-backend/` içinde `.env` dosyası oluşturabilirsin:

```env
LLM_MODEL=llama3.1:8b-instruct-q4_K_M
LLM_BASE_URL=http://localhost:11434
LLM_TEMPERATURE=0.0
LLM_REQUEST_TIMEOUT=120
MAX_RETRY_COUNT=3
CHROMA_PERSIST_DIR=.chroma_data
DEBUG=true
```

---

## 5. Hedef Veritabanı Bağlantı Stringleri

API isteklerinde gönderilen `connection_string` parametresi, NL2SQL sorgusunun çalıştırılacağı **hedef** veritabanını işaret eder.

### PostgreSQL

```
postgresql://kullanici:sifre@host:5432/veritabani
```

Örnek (localhost):
```
postgresql://admin:password@localhost:5432/northwind
```

Örnek (Docker ağı içinden):
```
postgresql://admin:password@postgres-container:5432/northwind
```

### Microsoft SQL Server (MSSQL)

```
mssql+pyodbc://kullanici:sifre@host:1433/veritabani?driver=ODBC+Driver+17+for+SQL+Server
```

SSL sertifikası doğrulamasını devre dışı bırakmak için:
```
mssql+pyodbc://kullanici:sifre@host:1433/veritabani?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
```

> **Gerekli kurulum:** `pyodbc` ve ODBC sürücüsü `requirements.txt`'de varsayılan olarak yok.  
> `requirements.txt`'e `pyodbc==5.1.0` ekle ve `Dockerfile`'a aşağıdaki satırları ekle:
> ```dockerfile
> RUN apt-get install -y --no-install-recommends unixodbc-dev gnupg && \
>     curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
>     curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
>     apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17
> ```

### MySQL / MariaDB

```
mysql+mysqlconnector://kullanici:sifre@host:3306/veritabani
```

> `requirements.txt`'e ekle: `mysql-connector-python==8.3.0`

### SQLite (test / geliştirme)

```
sqlite:///./yerel_dosya.db
sqlite:////mutlak/yol/veritabani.db
```

### Oracle

```
oracle+cx_oracle://kullanici:sifre@host:1521/?service_name=ORCL
```

> `requirements.txt`'e ekle: `cx_Oracle==8.3.0`

---

## 6. API Kullanım Akışı

Servis 3 endpoint içerir. Önce onboarding (şema kaydetme), sonra sorgu üretme.

### Adım 1 — Şemayı Otomatik Çıkar

Hedef veritabanına bağlanır, tablo ve kolon yapısını döner:

```bash
curl -X POST http://localhost:8001/api/v1/onboard/extract \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "northwind",
    "connection_string": "postgresql://admin:pass@localhost:5432/northwind"
  }'
```

**Yanıt:**
```json
{
  "db_id": "northwind",
  "tables": [
    {
      "name": "public.orders",
      "columns": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "customer_id", "type": "VARCHAR"},
        {"name": "order_date", "type": "DATE"},
        {"name": "freight", "type": "NUMERIC"}
      ],
      "human_description": "",
      "business_rules": ""
    }
  ],
  "few_shot_examples": []
}
```

### Adım 2 — Şemayı Zenginleştirip Kaydet

Adım 1'in yanıtını al, `human_description` ve `business_rules` alanlarını doldur, kaydet:

```bash
curl -X POST http://localhost:8001/api/v1/onboard/register \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "northwind",
    "tables": [
      {
        "name": "public.orders",
        "columns": [
          {"name": "order_id", "type": "INTEGER"},
          {"name": "customer_id", "type": "VARCHAR"},
          {"name": "order_date", "type": "DATE"},
          {"name": "freight", "type": "NUMERIC"}
        ],
        "human_description": "Müşteri siparişlerinin tutulduğu ana tablo",
        "business_rules": "İptal edilen siparişler is_cancelled=true ile işaretlenir, silinmez"
      }
    ],
    "few_shot_examples": [
      {
        "question": "Bu ay kaç sipariş verildi?",
        "sql": "SELECT COUNT(*) FROM public.orders WHERE DATE_TRUNC('month', order_date) = DATE_TRUNC('month', CURRENT_DATE)"
      }
    ]
  }'
```

**Yanıt:**
```json
{"status": "ok", "db_id": "northwind", "chunks_saved": 2}
```

### Adım 3 — SQL Üret ve Çalıştır

```bash
curl -X POST http://localhost:8001/api/v1/generate-sql \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "northwind",
    "connection_string": "postgresql://admin:pass@localhost:5432/northwind",
    "query": "Geçen ay en fazla sipariş veren 5 müşteriyi getir",
    "user_id": "user_001"
  }'
```

**Yanıt:**
```json
{
  "sql_query": "SELECT customer_id, COUNT(*) AS siparis_sayisi FROM public.orders WHERE DATE_TRUNC('month', order_date) = DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') GROUP BY customer_id ORDER BY siparis_sayisi DESC LIMIT 5",
  "explanation": "Bu sorgu geçen aya ait siparişleri filtreler. Müşteri bazında gruplama yaparak sipariş sayısını hesaplar ve en fazla sipariş verenden azına doğru sıralar, ilk 5 müşteriyi döner.",
  "data": [
    {"customer_id": "ALFKI", "siparis_sayisi": 12},
    {"customer_id": "BERGS", "siparis_sayisi": 9}
  ],
  "error": null,
  "status": "success"
}
```

---

## 7. Sorun Giderme

### `Could not import module "main"` — container başlamıyor

`Dockerfile`'daki `CMD` satırı `app.main:app` yazıyor. [§3.1](#31-dockerfiledaki-hatayı-düzelt-zorunlu)'deki düzeltmeyi uygula.

### Ollama'ya ulaşılamıyor — `Connection refused`

| Ortam | `LLM_BASE_URL` değeri |
|---|---|
| Yerel (host'ta) | `http://localhost:11434` |
| Docker (Windows/Mac) | `http://host.docker.internal:11434` |
| Docker (Linux) | `http://172.17.0.1:11434` veya `--add-host` kullan |

### ChromaDB verileri container restart'ta kayboluyor

`docker run` komutuna volume bind ekle:
```bash
-v nl2sql-chroma:/app/.chroma_data
```

### `generate-sql` — `relevant_schema boş, SQL üretilemiyor`

Önce `extract` → ardından `register` adımlarını tamamlamadan `generate-sql` çağrıldı.  
Her `db_id` için onboarding en az bir kez yapılmalıdır.

### MSSQL — `No module named 'pyodbc'`

`requirements.txt`'e `pyodbc==5.1.0` ekle, ODBC sürücüsünü `Dockerfile`'a dahil et — bkz. [§5 MSSQL bölümü](#microsoft-sql-server-mssql).

### Logları incele

```bash
# Yerel
uvicorn main:app --log-level debug

# Docker
docker logs nl2sql-ai-backend -f --tail=100
```
