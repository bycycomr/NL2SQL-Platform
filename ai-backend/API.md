# NL2SQL AI Backend — API Dokümantasyonu

**Versiyon:** 2.0.0
**Temel URL:** `http://localhost:8000`
**Swagger UI:** `/docs`
**Redoc:** `/redoc`

---

## Mimari Genel Bakış

```
Kullanıcı
    │
    ▼
Core Backend ──────────────────────────────────────────────────────────────┐
    │                                                                       │
    │  POST /api/v1/generate-sql                                            │
    ▼                                                                       │
AI Backend (Bu Servis)                                                      │
    │                                                                       │
    ├─1─► ChromaDB        → Şema RAG (şema + few-shot örnekler)            │
    ├─2─► Ollama / OpenAI → SQL Üret (LangGraph ajan döngüsü)              │
    ├─3─► SQL Doğrula     → Regex + AST (DML/DDL engelle)                  │
    ├─4─► Hedef DB        → Dry-run (LIMIT ile sözdizimi doğrula)          │
    └─5─► Yanıt           → {sql_query, is_validated, explanation}         │
                                                                            │
                           Core Backend doğrulanmış SQL ile                │
                           gerçek veriyi çeker ◄──────────────────────────┘
```

**Hibrit Mimari Prensibi:** AI Backend veri taşımaz; yalnızca doğrulanmış SQL üretir.
Gerçek veri çekimi, sayfalama ve yetkilendirme Core Backend sorumluluğundadır.

---

## Onboarding Akışı

```
Adım 1 — Extract                    Adım 2 — Zenginleştir         Adım 3 — Register
─────────────────                   ──────────────────────         ─────────────────
POST /onboard/extract          →    Domain uzmanı tabloları   →   POST /onboard/register
                                    açıklıyor, iş kuralları        (human_description,
DB'den şema otomatik çekilir        ekliyor, few-shot örnek         business_rules,
(sistem tabloları filtrelenir)       soru-SQL çiftleri yazıyor      few_shot_examples)
                                                                    ChromaDB'ye indeksler
```

---

## Endpoint Referansı

### `GET /health`

Servis sağlık kontrolü.

**Yanıt:**
```json
{
  "status": "ok",
  "service": "nl2sql-ai-backend",
  "version": "2.0.0"
}
```

---

### `POST /api/v1/onboard/extract`

Canlı veritabanından şemayı otomatik çıkarır.

**İstek:**
```json
{
  "db_id": "tenant_4582",
  "db_type": "PostgreSQL",
  "connection_string": "postgresql://user:password@db-host:5432/production_db"
}
```

| Alan | Tip | Zorunlu | Açıklama |
|------|-----|---------|----------|
| `db_id` | string | ✓ | Tenant / veritabanı kimliği |
| `db_type` | string | ✓ | DB türü (bilgilendirme amaçlı) |
| `connection_string` | string | ✓ | SQLAlchemy URL formatında bağlantı dizesi |

**Başarılı Yanıt (200):**
```json
{
  "status": "success",
  "db_id": "tenant_4582",
  "message": "3 tablo başarıyla okundu.",
  "tables": [
    {
      "table_name": "public.orders",
      "columns": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "customer_id", "type": "INTEGER"},
        {"name": "total_amount", "type": "NUMERIC NOT NULL"},
        {"name": "status", "type": "VARCHAR"}
      ],
      "human_description": "",
      "business_rules": ""
    }
  ]
}
```

**Hata Yanıtı (400):**
```json
{
  "detail": "Veritabanına bağlanılamadı veya şema okunamadı: Connection refused"
}
```

---

### `POST /api/v1/onboard/register`

İnsan tarafından zenginleştirilmiş şemayı ve few-shot örneklerini ChromaDB'ye kaydeder.

**İstek:**
```json
{
  "db_id": "tenant_4582",
  "mode": "upsert",
  "tables": [
    {
      "table_name": "public.orders",
      "columns": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "total_amount", "type": "NUMERIC"}
      ],
      "human_description": "Müşterilerin verdiği siparişleri tutan ana tablo.",
      "business_rules": "total_amount her zaman KDV dahildir. Aktif siparişler için status = 'COMPLETED' kullan."
    }
  ],
  "few_shot_examples": [
    {
      "question": "Bugün tamamlanan siparişlerin toplam tutarı nedir?",
      "query": "SELECT SUM(total_amount) FROM public.orders WHERE status = 'COMPLETED' AND DATE(order_date) = CURRENT_DATE;"
    }
  ]
}
```

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|------------|----------|
| `db_id` | string | — | Tenant kimliği |
| `mode` | string | `"upsert"` | Mevcut şemanın üzerine yaz |
| `tables` | TableSchema[] | — | Zenginleştirilmiş tablo listesi |
| `few_shot_examples` | FewShot[] | `[]` | Örnek soru-SQL çiftleri (`question` + `query`) |

**Başarılı Yanıt (200):**
```json
{
  "status": "success",
  "db_id": "tenant_4582",
  "message": "'tenant_4582' için zenginleştirilmiş şema ve örnek sorgular ChromaDB'ye başarıyla indekslendi.",
  "metrics": {
    "indexed_tables": 1,
    "indexed_few_shots": 1,
    "vector_chunks_created": 2
  }
}
```

---

### `POST /api/v1/generate-sql`

Doğal dil sorusunu SQL'e çevirir ve dry-run ile doğrular.

**İstek:**
```json
{
  "query": "Son 1 ayda en çok sipariş veren müşterileri getir.",
  "db_id": "tenant_4582",
  "connection_string": "postgresql://user:password@db-host:5432/production_db",
  "dry_run_limit": 5
}
```

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|------------|----------|
| `query` | string | — | Doğal dil sorusu (max 2000 karakter) |
| `db_id` | string | — | Hedef veritabanı kimliği |
| `connection_string` | string | — | Dry-run bağlantı dizesi |
| `dry_run_limit` | integer | `null` | Dahili test için satır limiti (min: 1). Döndürülen SQL'de bulunmaz. |
| `user_id` | string | `null` | Denetim için opsiyonel çağıran kimliği |

**Başarılı Yanıt (200):**
```json
{
  "status": "success",
  "sql_query": "SELECT customer_id, COUNT(*) as order_count FROM orders WHERE order_date >= NOW() - INTERVAL '1 month' GROUP BY customer_id ORDER BY order_count DESC;",
  "explanation": "Siparişler tablosundan son 1 aydaki verileri filtreledim ve müşteri ID'sine göre gruplayarak sipariş sayısına göre büyükten küçüğe sıraladım.",
  "is_validated": true,
  "impact_rows": 0
}
```

**Hata Yanıtı (200 — uygulama hatası):**
```json
{
  "status": "error",
  "error_code": "SQL_VALIDATION_FAILED",
  "error": "Blocked: DML/DDL keyword 'DROP' detected.",
  "is_validated": false,
  "impact_rows": 0
}
```

**Hata Kodları:**

| Kod | Açıklama |
|-----|----------|
| `SQL_VALIDATION_FAILED` | SQL güvenlik veya sözdizimi kontrolünden geçemedi |
| `SCHEMA_NOT_FOUND` | `db_id` için kayıtlı şema bulunamadı (onboarding yapılmamış) |
| `AGENT_ERROR` | Pipeline beklenmedik hatayla karşılaştı |

---

## Kurulum

### Gereksinimler

- Python 3.11+
- Ollama (yerel LLM) veya OpenAI API anahtarı
- ChromaDB (otomatik başlar)

### Yerel Geliştirme

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. Ortam değişkenlerini ayarla
cp .env.example .env
# .env dosyasını düzenle

# 3. Ollama modeli indir (Ollama kullanıyorsan)
ollama pull qwen3.5:4b

# 4. Servisi başlat
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker build -t nl2sql-ai-backend .
docker run -p 8000:8000 --env-file .env nl2sql-ai-backend
```

---

## Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `LLM_PROVIDER` | `auto` | `ollama`, `openai`, veya `auto` |
| `LLM_MODEL` | `qwen3.5:4b` | Ollama model adı |
| `LLM_BASE_URL` | `http://localhost:11434` | Ollama sunucu adresi |
| `LLM_TEMPERATURE` | `0.0` | LLM sıcaklığı (SQL için 0 önerilir) |
| `LLM_REQUEST_TIMEOUT` | `180` | LLM istek zaman aşımı (saniye) |
| `LLM_MAX_RETRIES` | `4` | LLM yeniden deneme sayısı |
| `OPENAI_API_KEY` | — | OpenAI API anahtarı (OpenAI kullanılıyorsa) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model adı |
| `MAX_RETRY_COUNT` | `3` | Ajan pipeline yeniden deneme sayısı |
| `CHROMA_PERSIST_DIR` | `.chroma_data` | ChromaDB veri dizini |
| `CHROMA_EMBEDDING_MODE` | `local_hash` | `local_hash` (offline) veya varsayılan |
| `ALLOWED_ORIGINS` | `*` | CORS izin verilen originler (virgülle ayrılmış) |
| `DEBUG` | `false` | Debug log seviyesi |

---

## Testler

```bash
# Tüm testleri çalıştır
pytest tests/ -v

# Belirli bir modül
pytest tests/test_security.py -v

# Coverage ile
pytest tests/ --cov=. --cov-report=term-missing
```

---

## LangGraph Pipeline

```
START
  │
  ▼
retrieve_schema   → ChromaDB'den db_id'ye göre filtrelenmiş şema çek
  │
  ├── Şema yok → END (SCHEMA_NOT_FOUND hatası)
  │
  ▼
generate_sql      → LLM ile SQL üret (hata varsa önceki hatayı prompt'a ekle)
  │
  ▼
validate_sql      → Regex + sqlglot AST ile DML/DDL engelle
  │
  ├── Geçersiz + retry < 3 → generate_sql (döngü)
  ├── Geçersiz + retry = 3 → END (SQL_VALIDATION_FAILED)
  │
  ▼
execute_sql       → Dry-run: LIMIT enjekte et, DB'de test et
  │
  ├── Hata + retry < 3 → generate_sql (hata ipucu ile)
  ├── Hata + retry = 3 → END
  │
  ▼
explain_sql       → LLM ile Türkçe açıklama üret
  │
  ▼
END               → {sql_query (temiz), is_validated: true, explanation}
```
