# NL2SQL AI Backend — Teknik Dokümantasyon

**Versiyon:** 2.0.0
**API Contract:** v2.0
**Son Güncelleme:** 2026-03-26

---

## İçindekiler

1. [Genel Bakış](#1-genel-bakış)
2. [Mimari](#2-mimari)
3. [Proje Yapısı](#3-proje-yapısı)
4. [Kurulum](#4-kurulum)
5. [Ortam Değişkenleri](#5-ortam-değişkenleri)
6. [API Referansı](#6-api-referansı)
7. [LangGraph Ajan Pipeline'ı](#7-langgraph-ajan-pipelaneı)
8. [Servisler](#8-servisler)
9. [Güvenlik Katmanı](#9-güvenlik-katmanı)
10. [Performans ve Cache](#10-performans-ve-cache)
11. [SSE Streaming](#11-sse-streaming)
12. [Onboarding Akışı](#12-onboarding-akışı)
13. [Hata Kodları](#13-hata-kodları)
14. [Mimari İyileştirmeler](#14-mimari-iyileştirmeler)
15. [Test Suite ve Coverage](#15-test-suite-ve-coverage)

---

## 1. Genel Bakış

NL2SQL AI Backend, doğal dil sorularını güvenli SQL sorgularına çeviren bir FastAPI mikroservisidir. Sistem **hibrit mimari** üzerine kuruludur:

- **AI Backend** (bu servis): SQL üretir, güvenlik doğrulaması yapar ve dry-run ile gerçek veritabanında test eder. Veri döndürmez.
- **Core Backend**: Üretilen doğrulanmış SQL'i alır ve gerçek veri çekimini yapar.

Bu ayrım, AI katmanının veri erişim yetkileri olmadan çalışmasını ve güvenlik sınırlarının net tutulmasını sağlar.

**Teknoloji Yığını:**

| Katman | Teknoloji |
|---|---|
| API Framework | FastAPI 0.115+ |
| Ajan Orkestrasyon | LangGraph |
| LLM (Ana Model) | llama3.1:8b-instruct-q4_K_M (Ollama) |
| LLM (Hızlı Model) | llama3.2:3b (Ollama) |
| LLM (Alternatif) | OpenAI GPT-4o-mini |
| Vektör DB | ChromaDB (disk-persist) |
| Embedding | nomic-embed-text 768-dim / LocalHashEmbedding 256-dim |
| SQL Doğrulama | sqlglot AST + regex |
| DB Bağlantı | SQLAlchemy (multi-dialect) |
| Cache | In-memory LRU (OrderedDict + TTL) |
| Metrikler | Prometheus (prometheus-fastapi-instrumentator) |

---

## 2. Mimari

### Sistem Akışı

```
Kullanıcı / Core Backend
         │
         │  POST /api/v1/generate-sql
         ▼
┌─────────────────────────────────────────────────────┐
│                  NL2SQL AI Backend                   │
│                                                      │
│  ┌──────────┐    Cache HIT → hemen dön              │
│  │  Routes  │──► LRU Cache ──────────────────────►  │
│  └──────────┘    Cache MISS ▼                        │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │           LangGraph Agent Pipeline           │    │
│  │                                              │    │
│  │  [1] retrieve_schema                         │    │
│  │       └─► ChromaDB (nomic-embed-text RAG)    │    │
│  │                  │                           │    │
│  │  [2] generate_sql                            │    │
│  │       └─► Ollama (llama3.1:8b / llama3.2:3b)│    │
│  │           estimate_complexity() ile yönlendir│    │
│  │                  │                           │    │
│  │  [3] validate_sql                            │    │
│  │       └─► sqlglot AST + regex güvenlik       │    │
│  │           validation_error? ──► retry loop   │    │
│  │                  │                           │    │
│  │  [4] execute_sql (dry-run)                   │    │
│  │       └─► SQLAlchemy (hedef DB)              │    │
│  │           execution_error? ──► retry loop    │    │
│  │                  │                           │    │
│  │  [5] explain_sql                             │    │
│  │       └─► Ollama (Türkçe açıklama)           │    │
│  └──────────────────────────────────────────────┘    │
│                  │                                   │
│           Cache'e yaz                                │
│                  │                                   │
│          NL2SQLResponse                              │
│    { sql_query, explanation,                         │
│      is_validated, impact_rows }                     │
└─────────────────────────────────────────────────────┘
         │
         │  sql_query → Core Backend'e ilet
         ▼
    Core Backend
    (gerçek veri çekimi)
```

### LangGraph Graf Topolojisi

```
START
  │
  ▼
retrieve_schema
  │
  ├── [şema yok] ──────────────────────────────► END (SCHEMA_NOT_FOUND)
  │
  ▼
generate_sql ◄──────────────────────────────────────┐
  │                                                  │
  ▼                                                  │
validate_sql                                         │
  │                                                  │
  ├── [hata + retry < 3] ───────────────────────────┘
  │                                                  │
  ├── [hata + retry = 3] ──────────────────► END (SQL_VALIDATION_FAILED)
  │                                                  │
  ▼                                                  │
execute_sql (dry-run)                                │
  │                                                  │
  ├── [execution hatası + retry < 3] ───────────────┘
  │
  ├── [execution hatası + retry = 3] ──────► END (error)
  │
  ▼
explain_sql
  │
  ▼
END (success)
```

---

## 3. Proje Yapısı

```
ai-backend/
├── main.py                    # FastAPI uygulama giriş noktası
├── .env                       # Ortam değişkenleri (git'e commit edilmez)
├── .env.example               # Değişken şablonu — kopyala ve doldur
├── .gitignore                 # Git dışı tutulan dosyalar
├── .dockerignore              # Docker build dışı tutulan dosyalar
├── requirements.txt           # Python bağımlılıkları
├── gunicorn.conf.py           # Prodüksiyon sunucu ayarları
├── Dockerfile                 # Multi-stage container imajı (python:3.11-slim)
├── docker-compose.yml         # Yerel geliştirme + prodüksiyon compose
│
├── api/
│   ├── routes.py              # Tüm HTTP endpoint tanımları
│   └── schemas.py             # Pydantic request/response modelleri
│
├── agent/
│   ├── graph.py               # LangGraph StateGraph tanımı
│   ├── nodes.py               # 5 ajan node fonksiyonu
│   ├── prompts.py             # LLM prompt şablonları
│   └── state.py               # AgentState TypedDict
│
├── core/
│   ├── config.py              # Uygulama ayarları (Settings dataclass)
│   └── security.py            # SQL güvenlik doğrulama (sqlglot + regex)
│
├── services/
│   ├── db_inspector.py        # SQLAlchemy şema introspection + read-only exec
│   ├── llm.py                 # LLM client factory + model routing + retry
│   ├── sql_cache.py           # In-memory LRU cache (TTL destekli)
│   └── vector_store.py        # ChromaDB entegrasyonu (RAG)
│
├── tests/
│   ├── conftest.py            # Paylaşılan fixture'lar (cache temizleme dahil)
│   ├── test_nodes.py          # LangGraph node unit testleri (15 test)
│   ├── test_routes.py         # FastAPI endpoint integration testleri (14 test)
│   ├── test_schemas.py        # Pydantic model validasyon testleri (14 test)
│   ├── test_security.py       # SQL güvenlik katmanı testleri (22 test)
│   ├── test_vector_store.py   # ChromaDB servis testleri (10 test)
│   └── register_payload.json  # /onboard/register test payload örneği
│
├── _archive/                  # Kullanılmayan eski dosyalar (git'e commit edilmez)
│
└── .chroma_data/              # ChromaDB disk kalıcı depolama (otomatik oluşur)
```

---

## 4. Kurulum

### Gereksinimler

- Python 3.10+
- [Ollama](https://ollama.ai) kurulu ve çalışıyor olmalı
- Ollama modelleri indirilmiş olmalı

### Yerel Geliştirme

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. Ollama modellerini indir
ollama pull llama3.1:8b-instruct-q4_K_M
ollama pull llama3.2:3b
ollama pull nomic-embed-text   # semantic embedding için

# 3. .env dosyasını oluştur (aşağıdaki Ortam Değişkenleri bölümüne bak)
cp .env.example .env

# 4. Sunucuyu başlat (geliştirme)
uvicorn main:app --reload --host 0.0.0.0 --port 8001

# 5. Prodüksiyon
gunicorn -c gunicorn.conf.py main:app
```

### Docker

```bash
docker build -t nl2sql-ai-backend .
docker run -p 8001:8001 --env-file .env nl2sql-ai-backend
```

### Hızlı Doğrulama

```bash
# Servis sağlık kontrolü
curl http://localhost:8001/health

# Swagger UI
open http://localhost:8001/docs
```

---

## 5. Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `ollama`, `openai`, veya `auto` (OpenAI key varsa openai seçer) |
| `LLM_MODEL` | `llama3.1:8b-instruct-q4_K_M` | Ana/karmaşık sorgular için model |
| `LLM_FAST_MODEL` | `llama3.2:3b` | Basit sorgular için hızlı model |
| `LLM_BASE_URL` | `http://localhost:11434` | Ollama API adresi |
| `LLM_TEMPERATURE` | `0.0` | Üretim sıcaklığı (0 = deterministik) |
| `LLM_REQUEST_TIMEOUT` | `180` | LLM istek timeout (saniye) |
| `LLM_MAX_RETRIES` | `4` | Tenacity retry sayısı |
| `OPENAI_API_KEY` | — | OpenAI API anahtarı (opsiyonel) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model adı |
| `MAX_RETRY_COUNT` | `3` | Ajan döngüsü max retry (validation/execution) |
| `CHROMA_PERSIST_DIR` | `.chroma_data` | ChromaDB disk depolama dizini |
| `CHROMA_EMBEDDING_MODE` | `local_hash` | `local_hash` (offline) veya `nomic` (semantic) |
| `CHROMA_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding modeli |
| `SQL_CACHE_MAX_SIZE` | `500` | LRU cache maksimum giriş sayısı |
| `SQL_CACHE_TTL_SECONDS` | `86400` | Cache TTL (24 saat) |
| `ALLOWED_ORIGINS` | `*` | CORS izin verilen origin'ler (virgülle ayrılmış) |
| `DEBUG` | `false` | Debug log seviyesi |
| `OLLAMA_FALLBACK_MODELS` | — | Bellek hatası için fallback model listesi (virgülle ayrılmış) |

### Embedding Modu Seçimi

| Mod | Değer | Boyut | Avantaj | Dezavantaj |
|---|---|---|---|---|
| Yerel Hash | `local_hash` | 256-dim | Ağ bağımlılığı yok, hızlı | Semantik anlam yok |
| Ollama nomic | `nomic` | 768-dim | Gerçek semantic search | Ollama + model gerektirir |

> **Önemli:** Embedding modu değiştirirken ChromaDB collection adı mode suffix'i içerir (`nl2sql_schemas_local_hash` vs `nl2sql_schemas_nomic`). Mod değiştirilirse şemaları yeniden kaydetmek gerekir.

---

## 6. API Referansı

### Temel URL

```
http://localhost:8001/api/v1
```

### Endpoint Özeti

| Method | Path | Açıklama |
|---|---|---|
| `GET` | `/health` | Servis sağlık kontrolü |
| `GET` | `/` | Yönlendirme mesajı |
| `GET` | `/metrics` | Prometheus metrikleri (opsiyonel) |
| `POST` | `/api/v1/onboard/extract` | Adım 1: Canlı DB'den şema çıkar |
| `POST` | `/api/v1/onboard/register` | Adım 2: Zenginleştirilmiş şemayı kaydet |
| `POST` | `/api/v1/generate-sql` | Doğal dil → SQL |
| `POST` | `/api/v1/generate-sql/stream` | Doğal dil → SQL (SSE streaming) |
| `GET` | `/api/v1/cache/stats` | Cache istatistikleri |

---

### GET /health

Servis sağlık kontrolü.

**Response 200:**
```json
{
  "status": "ok",
  "service": "nl2sql-ai-backend",
  "version": "2.0.0"
}
```

---

### POST /api/v1/onboard/extract

Hedef veritabanına bağlanır, tabloları ve kolonları introspect eder. Sistem şemaları (`pg_catalog`, `information_schema`, `sys` vb.) otomatik filtrelenir.

**Request:**
```json
{
  "db_id": "adventureworks_prod",
  "db_type": "mssql",
  "connection_string": "mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server"
}
```

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `db_id` | string | Evet | Tenant veya veritabanı kimliği |
| `db_type` | string | Hayır | DB türü (bilgilendirme amaçlı, `DBInspector`'a geçilmez) |
| `connection_string` | string | Evet | SQLAlchemy bağlantı dizesi |

**Response 200:**
```json
{
  "status": "success",
  "db_id": "adventureworks_prod",
  "message": "12 tablo başarıyla okundu.",
  "tables": [
    {
      "table_name": "SalesLT.Customer",
      "columns": [
        { "name": "CustomerID", "type": "INTEGER NOT NULL" },
        { "name": "FirstName", "type": "NVARCHAR(50) NOT NULL" },
        { "name": "LastName", "type": "NVARCHAR(50) NOT NULL" },
        { "name": "EmailAddress", "type": "NVARCHAR(50)" }
      ],
      "human_description": "",
      "business_rules": ""
    }
  ]
}
```

**Response 400:** Veritabanına bağlanılamadı.

---

### POST /api/v1/onboard/register

İnsan uzmanlar tarafından zenginleştirilmiş şemayı ve few-shot örneklerini ChromaDB'ye kaydeder. `mode="upsert"` ile mevcut şemanın üzerine yazar.

**Request:**
```json
{
  "db_id": "adventureworks_prod",
  "mode": "upsert",
  "tables": [
    {
      "table_name": "SalesLT.Customer",
      "columns": [
        { "name": "CustomerID", "type": "INTEGER NOT NULL" },
        { "name": "FirstName", "type": "NVARCHAR(50) NOT NULL" },
        { "name": "LastName", "type": "NVARCHAR(50) NOT NULL" }
      ],
      "human_description": "Müşteri kayıtları. B2B müşterileri içerir.",
      "business_rules": "Aktif müşteriler için CustomerType='S'. Silinmiş kayıtlar için DeletedAt alanı dolu."
    }
  ],
  "few_shot_examples": [
    {
      "question": "Kaç müşteri var?",
      "query": "SELECT COUNT(*) AS TotalCustomers FROM SalesLT.Customer"
    },
    {
      "question": "En son kayıt olan 5 müşteriyi getir",
      "query": "SELECT TOP 5 CustomerID, FirstName, LastName FROM SalesLT.Customer ORDER BY ModifiedDate DESC"
    }
  ]
}
```

> **Not:** `few_shot_examples` alanında `query` (contract) veya `sql` (legacy) anahtarları kabul edilir. Sistem normalize eder.

**Response 200:**
```json
{
  "status": "success",
  "db_id": "adventureworks_prod",
  "message": "'adventureworks_prod' için zenginleştirilmiş şema ve örnek sorgular ChromaDB'ye başarıyla indekslendi.",
  "metrics": {
    "indexed_tables": 1,
    "indexed_few_shots": 2,
    "vector_chunks_created": 3
  }
}
```

**Response 500:** ChromaDB kayıt hatası.

---

### POST /api/v1/generate-sql

Doğal dil sorusunu LangGraph ajan döngüsüyle SQL'e çevirir ve dry-run ile doğrular.

**Request:**
```json
{
  "db_id": "adventureworks_prod",
  "connection_string": "mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server",
  "query": "En çok sipariş veren 5 müşteriyi getir",
  "dry_run_limit": 5,
  "user_id": "user-123"
}
```

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `db_id` | string | Evet | Hedef veritabanı kimliği (şema lookup ve dry-run için) |
| `connection_string` | string | Evet | SQLAlchemy bağlantı dizesi (dry-run için). Erken Pydantic validasyonundan geçer. |
| `query` | string | Evet | Doğal dil sorusu (1-2000 karakter) |
| `dry_run_limit` | integer >= 1 | Hayır | Dahili dry-run için satır limiti. Döndürülen `sql_query`'de LIMIT bulunmaz. |
| `user_id` | string | Hayır | Denetim / loglama için çağıran kimliği |

**Response 200 (başarı):**
```json
{
  "status": "success",
  "sql_query": "SELECT TOP 5 c.CustomerID, c.FirstName + ' ' + c.LastName AS CustomerName, COUNT(o.SalesOrderID) AS OrderCount FROM SalesLT.Customer c JOIN SalesLT.SalesOrderHeader o ON c.CustomerID = o.CustomerID GROUP BY c.CustomerID, c.FirstName, c.LastName ORDER BY OrderCount DESC",
  "explanation": "SalesLT.Customer ve SalesLT.SalesOrderHeader tablolarını birleştirerek her müşterinin sipariş sayısını hesaplar ve en yüksek sipariş sayısına göre sıralayarak ilk 5 müşteriyi getirir.",
  "is_validated": true,
  "impact_rows": 0,
  "error": null,
  "error_code": null
}
```

> **Hibrit Mimari Notu:** `sql_query` her zaman temizdir — `dry_run_limit=5` verilmiş olsa bile döndürülen SQL'de `TOP 5` veya `LIMIT 5` bulunmaz. Core Backend bu SQL'i kendi `LIMIT` mantığıyla çalıştırır.

**Response 200 (hata):**
```json
{
  "status": "error",
  "sql_query": null,
  "explanation": null,
  "is_validated": false,
  "impact_rows": 0,
  "error": "'adventureworks_prod' icin kayitli sema bulunamadi. Lutfen once /api/v1/onboard/extract ve /api/v1/onboard/register ile onboarding yapin.",
  "error_code": "SCHEMA_NOT_FOUND"
}
```

> **Not:** HTTP status kodu her zaman 200'dür. Hata durumu `status` ve `error_code` alanlarıyla belirlenir.

---

### POST /api/v1/generate-sql/stream

`/generate-sql` ile aynı mantık, fark olarak her LangGraph node'u tamamlandıkça `text/event-stream` formatında event yollanır.

**Request:** `/generate-sql` ile aynı.

**SSE Event Akışı:**

```
data: {"event": "progress", "node": "retrieve_schema", "message": "Şema aranıyor..."}

data: {"event": "progress", "node": "generate_sql", "message": "SQL üretiliyor...", "sql_preview": "SELECT TOP 5 c.CustomerID..."}

data: {"event": "progress", "node": "validate_sql", "message": "SQL dogrulanıyor..."}

data: {"event": "progress", "node": "execute_sql", "message": "SQL test ediliyor (dry-run)..."}

data: {"event": "progress", "node": "explain_sql", "message": "Acıklama haazırlanıyor..."}

data: {"event": "done", "status": "success", "sql_query": "SELECT TOP 5 ...", "explanation": "...", "is_validated": true, "impact_rows": 0}
```

**Cache HIT (tek event):**
```
data: {"event": "done", "cached": true, "status": "success", "sql_query": "...", ...}
```

**curl ile test:**
```bash
curl -N -X POST http://localhost:8001/api/v1/generate-sql/stream \
  -H "Content-Type: application/json" \
  -d '{"db_id":"mydb","connection_string":"...","query":"Toplam müşteri sayısı"}'
```

---

### GET /api/v1/cache/stats

**Response 200:**
```json
{
  "total_entries": 42,
  "active_entries": 38
}
```

---

## 7. LangGraph Ajan Pipeline'ı

### AgentState

Pipeline boyunca akan paylaşılan durum (`agent/state.py`):

```python
class AgentState(TypedDict):
    # Kimlik ve bağlantı
    db_id: str                                    # Tenant kimliği
    connection_string: str                        # SQLAlchemy URL

    # Kullanıcı girdisi
    question: str                                 # Doğal dil sorusu

    # Pipeline ara değerleri
    relevant_schema: str          # ChromaDB'den çekilen DDL metni
    generated_sql: str            # LLM'in ürettiği temiz SQL (LIMIT içermez)
    validation_error: str | None  # Güvenlik/execution hatası (varsa)
    explanation: str              # Türkçe açıklama
    execution_data: list[dict] | None  # Dry-run satırları (iç kullanım)
    retry_count: int              # Yeniden deneme sayacı

    # Contract v2.0
    dry_run_limit: int | None     # Dry-run satır limiti
    is_validated: bool            # Güvenlik kontrolünden geçti mi
```

---

### Node 1: retrieve_schema_node

**Dosya:** `agent/nodes.py`

ChromaDB'den `db_id`'ye göre filtrelenmiş şema DDL'ini çeker (semantic veya hash-based RAG, `top_k=10`).

**Mantık:**
- `retrieve_relevant_schema(db_id, question)` çağrılır
- Şema bulunamazsa `validation_error` set edilir ve `retry_count = MAX_RETRY_COUNT` yapılır (erken sonlandırma)
- Şema bulunursa `relevant_schema` güncellenir, `validation_error = None` yapılır

**Koşullu Yönlendirme** (`_after_retrieve`):
- Şema var → `generate_sql`
- Şema yok → `END` (SCHEMA_NOT_FOUND)

---

### Node 2: generate_sql_node

**Dosya:** `agent/nodes.py`

LLM'i kullanarak SQL üretir. Complexity routing ile doğru model seçilir.

**Model Seçimi (`estimate_complexity`):**

| Koşul | Sonuç | Model |
|---|---|---|
| `join`, `grupla`, `group`, `pivot`, `having`, `window`, `rank` içeriyor | `complex` | llama3.1:8b-instruct-q4_K_M |
| Şemada >2 tablo AND soru >8 kelime | `complex` | llama3.1:8b-instruct-q4_K_M |
| `kaç`, `count`, `toplam`, `sayı`, `liste` içeriyor AND <=2 tablo | `simple` | llama3.2:3b |
| Soru <=6 kelime | `simple` | llama3.2:3b |
| retry_count > 0 | `complex` | llama3.1:8b-instruct-q4_K_M (her zaman) |

**SQL Temizleme (`_clean_sql`):**
1. Markdown fences kaldır (` ```sql ... ``` `)
2. Paragraf ayrıştırma (blank-line separator): İlk `SELECT`/`WITH` ile başlayan paragrafı al
3. Fallback: Prose pattern — doğal dil gibi görünen satıra ulaşınca dur
4. `_looks_like_sql()` kontrolü — SQL görünmüyorsa `_fallback_sql()` kullan

**Prompt Şablonu (`SQL_GENERATION_PROMPT`):**
- Şema, dialect, önceki hata ve soru enjekte edilir
- Katı kurallar: sadece SELECT, markdown yok, şemada olmayan kolon uydurmak yasak
- Dialect-aware: MSSQL için `SELECT TOP N`, PostgreSQL/MySQL/SQLite için `LIMIT N`

---

### Node 3: validate_sql_node

**Dosya:** `agent/nodes.py` → `core/security.py`

İki katmanlı güvenlik doğrulaması.

**Katman 1 — Regex:**
```
\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|MERGE|REPLACE|EXEC|EXECUTE)\b
```

**Katman 2 — sqlglot AST:**
- T-SQL dialect ile parse eder
- `Insert`, `Update`, `Delete`, `Drop`, `Alter`, `Create` statement tiplerini engeller
- Parse edilemeyen SQL'i de engeller (LLM açıklama döndürdüyse)

**Çıktı:**
- Geçerli → `is_validated=True`, `validation_error=None`
- Geçersiz → `is_validated=False`, `validation_error=<hata mesajı>`, `retry_count++`

**Koşullu Yönlendirme** (`_after_validation`):
- Geçerli → `execute_sql`
- Geçersiz + retry < 3 → `generate_sql` (hata mesajını prompt'a ekleyerek)
- Geçersiz + retry = 3 → `END`

---

### Node 4: execute_sql_node

**Dosya:** `agent/nodes.py`

Dry-run doğrulaması: SQL'i hedef veritabanında sınırlı satırla çalıştırır.

**Dry-Run LIMIT Enjeksiyonu:**

```python
_HAS_LIMIT = re.compile(r"\bLIMIT\s+\d+\s*;?\s*$", re.IGNORECASE)
_HAS_TOP   = re.compile(r"^\s*SELECT\s+TOP\s+\d+", re.IGNORECASE)
```

| Dialect | dry_run_limit | Zaten LIMIT/TOP var | İşlem |
|---|---|---|---|
| MSSQL | 5 | Hayır | `SELECT TOP 5 ...` ekle |
| PostgreSQL | 5 | Hayır | `... LIMIT 5` ekle |
| Herhangi | 5 | Evet | Değişiklik yapma (çift enjeksiyon engeli) |
| Herhangi | None | — | Değişiklik yapma |

> **Kritik:** `generated_sql` state alanı asla değiştirilmez. Yalnızca dahili `dry_run_sql` değişkeni kullanılır. Döndürülen `sql_query` her zaman temizdir.

**Execution Error Hint (`_build_execution_error_hint`):**
- `Invalid column name 'X'` → hangi tabloda kullanıldığını bulur, LLM'e net mesaj verir
- `Invalid object name 'X'` → tablo/nesne mevcut değil mesajı
- Diğer hatalar → ilk satır, max 300 karakter

**Koşullu Yönlendirme** (`_after_execution`):
- Başarılı → `explain_sql`
- Hata + retry < 3 → `generate_sql` (hint ile)
- Hata + retry = 3 → `END`

---

### Node 5: explain_sql_node

**Dosya:** `agent/nodes.py`

LLM'i kullanarak SQL sorgusunun Türkçe açıklamasını üretir.

**Prompt Kuralları:**
- Türkçe, max 3 cümle
- Hangi tablolar, hangi filtreler, ne sonuç temsil ediyor
- "İşte açıklaması:" gibi giriş kalıpları yok

**Hata Durumu:** LLM erişilemezse fallback string döner (ajan başarısız sayılmaz).

---

## 8. Servisler

### services/db_inspector.py — DBInspector

SQLAlchemy tabanlı çoklu-dialect şema introspection ve read-only query execution.

**`get_schema()` Filtrelenen Sistem Şemaları:**

| DBMS | Filtrelenen Şemalar |
|---|---|
| MSSQL | `sys`, `information_schema`, `guest`, `db_owner`, `db_*` rolleri |
| PostgreSQL | `pg_catalog`, `pg_toast` |
| MySQL | `mysql`, `performance_schema` |
| Oracle | `ctxsys`, `dbsnmp`, `exfsys`, `mdsys`, vb. |

**Çıktı Formatı:**
```python
[
    {
        "name": "SalesLT.Customer",        # schema.table veya table
        "columns": ["CustomerID INTEGER NOT NULL", "FirstName NVARCHAR(50) NOT NULL"],
        "human_description": "",
        "business_rules": ""
    }
]
```

**`execute_read_only(sql)`:**
- PostgreSQL'de `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` dener (diğerlerinde no-op)
- SQL DAHA ÖNCE `validate_sql()` ile doğrulanmış olmalıdır
- Satırları `list[dict]` olarak döndürür

---

### services/llm.py — LLM Factory

**Provider Çözümleme (`_resolve_provider`):**
```
LLM_PROVIDER="auto" → OPENAI_API_KEY geçerli mi?
  Evet → "openai"
  Hayır → "ollama"
```

**Concurrency Koruması:**
```python
_ollama_semaphore = asyncio.Semaphore(1)
```
Eş zamanlı istekler kuyruklanır. Ollama tek thread'de çalıştığı için paralel istek "Remote end closed" hatası verir. Semaphore bunu önler.

**Retry Mekanizması (Tenacity):**
- `stop_after_attempt(LLM_MAX_RETRIES)` — varsayılan 4 deneme
- `wait_exponential(multiplier=1, min=1, max=8)` — 1s, 2s, 4s, 8s bekleme

**Bellek Hatası Fallback:**
Ollama `"model requires more system memory"` veya `"insufficient memory"` hatası verirse sıradaki küçük modele geçer:
- Varsayılan sıra: `qwen3.5:4b`, `llama3.2:3b`, `deepseek-r1:1.5b`
- `OLLAMA_FALLBACK_MODELS` env ile özelleştirilebilir

---

### services/vector_store.py — ChromaDB

**Singleton İstemci:** `chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)`

**Collection Adlandırma:**
```
nl2sql_schemas_{embedding_mode}
# Örnekler:
nl2sql_schemas_local_hash
nl2sql_schemas_nomic
```
Embedding modu değiştirilirse farklı collection kullanılır — boyut uyumsuzluğu önlenir.

**`save_schema_chunks()` Doküman Formatı:**
```
TABLE: SalesLT.Customer
COLUMNS: CustomerID INTEGER NOT NULL, FirstName NVARCHAR(50) NOT NULL
DESCRIPTION: Müşteri kayıtları. B2B müşterileri içerir.
BUSINESS RULES: Aktif müşteriler için CustomerType='S'.
```

**Few-Shot Doküman Formatı:**
```
Question: Kaç müşteri var?
SQL: SELECT COUNT(*) AS TotalCustomers FROM SalesLT.Customer
```

**`retrieve_relevant_schema()` Parametreleri:**
- `top_k=10` — en alakalı 10 chunk döner
- `where={"db_id": db_id}` — multi-tenant filtreleme
- Sonuçlar `\n\n` ile birleştirilir, prompt'a enjekte edilir

**`_table_to_text()` Çift Format Desteği:**
```python
# DBInspector'dan: list[str]
["CustomerID INTEGER NOT NULL", "FirstName NVARCHAR(50) NOT NULL"]

# RegisterSchemaRequest'ten: list[dict]
[{"name": "CustomerID", "type": "INTEGER NOT NULL"}]
```

---

### services/sql_cache.py — LRU Cache

**Key Üretimi:**
```python
key = SHA256(f"{db_id}::{question.lower().strip()}")[:16 hex chars]
```

**LRU Eviction:** `OrderedDict` ile. `move_to_end(key)` ile son kullanılan sona taşınır; limit dolunca `popitem(last=False)` ile en eski silinir.

**TTL:** Her entry için `time.time() + SQL_CACHE_TTL_SECONDS` kaydedilir. `get()` sırasında TTL kontrolü yapılır.

**Sadece başarılı sonuçlar cache'e alınır.** Hata durumları cache'e yazılmaz.

---

## 9. Güvenlik Katmanı

### SQL Doğrulama (core/security.py)

**Layer 1 — Regex (hızlı kontrol):**
Şu keyword'lerden herhangi biri varsa anında reddedilir:
`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `MERGE`, `REPLACE`, `EXEC`, `EXECUTE`

**Layer 2 — sqlglot AST (derin kontrol):**
- T-SQL dialect ile tam parse
- AST'de DML/DDL node'u varsa reddedilir
- Parse edilemeyen veya hatalı biçimlendirme reddedilir (LLM açıklama döndürdüyse)

**Blocked Statement Types:**
```python
{exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create}
```

**Pydantic Erken Validasyon:**
`NL2SQLRequest.connection_string` alanı, `make_url()` ile SQLAlchemy URL formatı olarak doğrulanır. Hatalı bağlantı dizesi ajan döngüsüne girmeden `422 Unprocessable Entity` döner.

### CORS

Prodüksiyonda `ALLOWED_ORIGINS` env değişkeniyle kısıtlanmalıdır:
```
ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com
```

### Read-Only Execution

`execute_read_only()` PostgreSQL'de session-level read-only modu dener. Diğer DB'lerde güvenlik katmanı (Layer 1+2) birincil korumadır.

---

## 10. Performans ve Cache

### Gözlemlenen Yanıt Süreleri

| Senaryo | Süre |
|---|---|
| Cache HIT | ~2s |
| llama3.2:3b (simple, başarılı) | ~18-20s |
| llama3.1:8b-instruct-q4_K_M (complex) | ~45-50s |
| 3b → 8b fallback (simple başarısız) | ~47-50s |

### Cache Etkisi

Cache HIT, LLM çağrısını ve dry-run'u tamamen atlar. Aynı soru için ~14x hızlanma sağlar.

### Concurrency

`asyncio.Semaphore(1)` ile Ollama çağrıları serileştirilir. Eş zamanlı birden fazla istek gelirse kuyruklanır. Timeout: `LLM_REQUEST_TIMEOUT=180s` (her istek için).

### Prometheus Metrikleri

`prometheus-fastapi-instrumentator` kuruluysa `/metrics` endpoint'i otomatik aktif olur. Kurulu değilse sessizce atlanır.

---

## 11. SSE Streaming

`/generate-sql/stream` endpoint'i `StreamingResponse` + LangGraph `astream(stream_mode="updates")` kombinasyonuyla çalışır.

**Event Tipleri:**

| Event | Ne Zaman | İçerik |
|---|---|---|
| `progress` | Her node tamamlandığında | `node`, `message`, (opsiyonel) `sql_preview` |
| `error` | Ajan exception fırlatırsa | `error_code`, `error` |
| `done` | Pipeline bittiğinde | `status`, `sql_query`, `explanation`, `is_validated`, `impact_rows` |

**Node Mesajları:**

| Node | Mesaj |
|---|---|
| `retrieve_schema` | "Şema aranıyor..." |
| `generate_sql` | "SQL üretiliyor..." |
| `validate_sql` | "SQL dogrulanıyor..." |
| `execute_sql` | "SQL test ediliyor (dry-run)..." |
| `explain_sql` | "Acıklama haazırlanıyor..." |

**SSE Format:**
```
data: {"event": "progress", "node": "generate_sql", "message": "SQL üretiliyor...", "sql_preview": "SELECT TOP 5..."}\n\n
```

**Cache HIT → Streaming:** Cache'ten gelen sonuç tek `done` eventi olarak SSE'ye sarılır.

---

## 12. Onboarding Akışı

Bir veritabanını sisteme dahil etmek için iki adımlı onboarding gereklidir.

### Adım 1: Şema Çıkarma

```bash
curl -X POST http://localhost:8001/api/v1/onboard/extract \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "mydb",
    "db_type": "mssql",
    "connection_string": "mssql+pyodbc://..."
  }'
```

Dönen `tables` listesini kaydet. Her tabloya `human_description` ve `business_rules` ekle.

### Adım 2: Şema Kayıt

```bash
curl -X POST http://localhost:8001/api/v1/onboard/register \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "mydb",
    "mode": "upsert",
    "tables": [
      {
        "table_name": "orders",
        "columns": [...],
        "human_description": "Satış siparişleri",
        "business_rules": "status=ACTIVE olan kayıtlar tamamlanmış siparişleri gösterir"
      }
    ],
    "few_shot_examples": [
      {
        "question": "Toplam sipariş sayısı?",
        "query": "SELECT COUNT(*) FROM orders WHERE status='"'"'ACTIVE'"'"'"
      }
    ]
  }'
```

### Şema Güncelleme

`mode="upsert"` (varsayılan) mevcut şemanın üzerine yazar. Yeniden `register` çağrısı yeterlidir.

### Onboarding Doğrulama

```bash
curl -X POST http://localhost:8001/api/v1/generate-sql \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "mydb",
    "connection_string": "...",
    "query": "Toplam kayıt sayısı",
    "dry_run_limit": 1
  }'
```

Yanıtta `is_validated: true` geliyorsa onboarding başarılıdır.

---

## 13. Hata Kodları

| Kod | Durum | Açıklama |
|---|---|---|
| `SCHEMA_NOT_FOUND` | error | `db_id` için ChromaDB'de kayıtlı şema bulunamadı. Onboarding yapılmamış. |
| `SQL_VALIDATION_FAILED` | error | Güvenlik doğrulaması başarısız (DML tespit, parse hatası) veya max retry aşıldı |
| `AGENT_ERROR` | error | LangGraph pipeline beklenmedik exception fırlattı |

**HTTP Status Kodları:**

| Kod | Endpoint | Koşul |
|---|---|---|
| `200` | Tüm POST'lar | Başarı ve iş mantığı hataları (status alanıyla ayrılır) |
| `400` | `/onboard/extract` | DB bağlantısı veya şema okuma hatası |
| `422` | Tüm POST'lar | Pydantic validasyon hatası (hatalı connection_string, eksik alan) |
| `500` | `/onboard/register` | ChromaDB kayıt hatası |

---

## 14. Mimari İyileştirmeler

Projenin geliştirme sürecinde yapılan 5 kritik mimari iyileştirme:

### İyileştirme 1: Model Routing (Complexity-Based)

**Problem:** Her sorgu için büyük model kullanılıyordu. Basit sayım sorguları için 8b model gereksiz yavaştı.

**Çözüm:** `estimate_complexity()` fonksiyonu ile kelime analizi yapılır. Basit sorgular `llama3.2:3b` (hızlı), karmaşık JOIN/GROUP sorgular `llama3.1:8b` (kaliteli) modele yönlendirilir. Retry durumunda her zaman büyük model kullanılır.

**Etki:** Basit sorgularda ~50% hız artışı (45s → 18-20s), kaliteli sorgularda doğruluk korunur.

---

### İyileştirme 2: Concurrency Koruması (Semaphore)

**Problem:** Eş zamanlı isteklerde Ollama "Remote end closed connection" hatası veriyordu.

**Çözüm:** `asyncio.Semaphore(1)` ile Ollama çağrıları serileştirilir. Eş zamanlı istekler async kuyrukta bekler.

**Etki:** Eş zamanlı kullanımda hata oranı sıfıra indi.

---

### İyileştirme 3: SQL Cache (LRU + TTL)

**Problem:** Aynı soru tekrar sorulduğunda her seferinde LLM ve dry-run çalışıyordu.

**Çözüm:** SHA256 tabanlı LRU cache. Başarılı sonuçlar 24 saat (ayarlanabilir) cache'te tutulur. Max 500 entry, LRU eviction.

**Etki:** Tekrar eden sorularda ~14x hızlanma (45s → 2-3s).

---

### İyileştirme 4: SSE Streaming

**Problem:** `/generate-sql` 45+ saniye blokluyordu. Kullanıcı hiçbir feedback almıyordu.

**Çözüm:** `/generate-sql/stream` endpoint'i LangGraph `astream()` ile her node tamamlandığında SSE eventi gönderir. İstemci gerçek zamanlı progress izleyebilir.

**Etki:** Kullanıcı ilk event'i <1 saniyede alır. UX iyileşmesi.

---

### İyileştirme 5: _clean_sql Yeniden Yazımı

**Problem:** LLM zaman zaman SQL'den sonra Türkçe açıklama yazıyordu. Eski regex `_clean_sql` multi-line SQL'i kesiyor, tek satıra düşürüyordu.

**Çözüm:** Paragraph-splitting stratejisi. Blank-line separator'a kadar olan ilk SQL bloğu alınır. Blank-line yoksa prose-pattern ile satır satır tarama. Markdown fences temizleme.

**Etki:** LLM çıktısı ne kadar karışık olursa olsun doğru SQL çıkarılır. Multi-line subquery ve CTE sorguları bozulmaz.

---

## Ek: Desteklenen Veritabanları

| Veritabanı | SQLAlchemy Driver | Dry-Run LIMIT | Test Durumu |
|---|---|---|---|
| Microsoft SQL Server | `mssql+pyodbc` | `SELECT TOP N` | Doğrulandı (AdventureWorksLT2025) |
| PostgreSQL | `postgresql+psycopg2` | `LIMIT N` | Desteklenir |
| MySQL / MariaDB | `mysql+pymysql` | `LIMIT N` | Desteklenir |
| SQLite | `sqlite:///path` | `LIMIT N` | Desteklenir |

---

## 15. Test Suite ve Coverage

### Genel Bakış

Tüm testler harici servisler (LLM, ChromaDB, gerçek DB) mock'lanarak izole şekilde çalışır. Pytest + `unittest.mock` kullanılır.

```bash
# Tüm testleri çalıştır
pytest tests/ -v

# Coverage raporu ile
pytest tests/ --cov=. --cov-report=term-missing

# Tek dosya
pytest tests/test_security.py -v
```

### Test Modülleri

| Dosya | Test Sayısı | Kapsam |
|---|---|---|
| `test_security.py` | 22 | SQL güvenlik katmanı (DML engelleme, edge case'ler) |
| `test_nodes.py` | 15 | LangGraph node'ları (validate, execute, generate) |
| `test_schemas.py` | 14 | Pydantic model validasyonları |
| `test_routes.py` | 14 | FastAPI endpoint integration testleri |
| `test_vector_store.py` | 10 | ChromaDB servis fonksiyonları |
| **Toplam** | **75** | |

### Son Coverage Raporu (2026-03-26)

```
Name                         Stmts   Miss  Cover
-------------------------------------------------
agent/graph.py                  52     24    54%
agent/nodes.py                 193     65    66%
agent/prompts.py                 3      0   100%
agent/state.py                  14      0   100%
api/routes.py                  102     34    67%
api/schemas.py                  67      0   100%
core/config.py                  34      1    97%
core/security.py                28      4    86%
main.py                         34      2    94%
services/db_inspector.py        54     43    20%
services/llm.py                107     72    33%
services/sql_cache.py           42     18    57%
services/vector_store.py       160     78    51%
-------------------------------------------------
TOTAL                         1327    348    74%
```

**75 passed — 0 failed** (Python 3.10, pytest 9.0.2)

### Coverage Notları

| Modül | Cover | Neden Düşük |
|---|---|---|
| `services/db_inspector.py` | 20% | Gerçek DB bağlantısı gerektirir; integration test kapsamı dışı |
| `services/llm.py` | 33% | Ollama/OpenAI API çağrıları; retry/fallback dalları harici bağımlılık |
| `services/vector_store.py` | 51% | ChromaDB retrieve path'i; mock'lanan kısımlar dışındaki ChromaDB API çağrıları |
| `api/routes.py` | 67% | SSE streaming endpoint (`/generate-sql/stream`) tam mock'lanmadı |
| `agent/graph.py` | 54% | LangGraph conditional edge'leri; tam pipeline integration testi gerektirir |

### Kritik Bug Fix: Cache Test İzolasyonu

Testler arasında `sql_cache` state sızıntısı tespit edildi: `TestGenerateSql` sınıfındaki ilk başarılı test cache'e yazıyor, aynı `db_id+query` kullanan sonraki testler mock agent yerine cache'ten sonuç alıyordu.

**Fix:** `conftest.py`'e `autouse=True` fixture eklendi:

```python
@pytest.fixture(autouse=True)
def clear_sql_cache():
    """Her test öncesi SQL cache'i temizle."""
    _sql_cache_module._cache.clear()
    yield
    _sql_cache_module._cache.clear()
```

Bu fix 3 yanlış geçen testi doğru başarısızlıktan kurtardı ve gerçek davranışı test etmeye başladı.

---

*Bu dokümantasyon, NL2SQL AI Backend v2.0.0 kodundan otomatik olarak çıkarılmıştır.*
