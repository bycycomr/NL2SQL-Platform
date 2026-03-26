# Core Backend — API Contract v1.0

**Tarih:** 2026-03-26
**İlişkili:** AI Backend API Contract v2.0

---

## Mimari Özet

```
Kullanıcı / Frontend
        │
        ▼
  Core Backend          ←→   AI Backend (NL2SQL)
        │                         │
        │                    ChromaDB (vektörler)
        │                    Ollama (LLM)
        ▼
  Core Backend DB
  (şema registry, sorgu geçmişi, bağlantılar)
```

Core Backend iki ana sorumluluğu üstlenir:

1. **Orchestration** — AI Backend'i yönetir (extract/register tetikler, zamanlar)
2. **Execution** — AI Backend'den gelen SQL'i gerçek DB'de çalıştırır, veriyi döndürür

---

## İçindekiler

1. [Veritabanı Bağlantı Yönetimi](#1-veritabanı-bağlantı-yönetimi)
2. [Onboarding Orchestration](#2-onboarding-orchestration)
3. [Şema Zenginleştirme (Admin)](#3-şema-zenginleştirme-admin)
4. [Sorgu Çalıştırma](#4-sorgu-çalıştırma)
5. [Sorgu Geçmişi](#5-sorgu-geçmişi)
6. [Sync ve Zamanlama](#6-sync-ve-zamanlama)
7. [Ops](#7-ops)
8. [Veri Modelleri](#8-veri-modelleri)
9. [Hata Formatı](#9-hata-formatı)

---

## 1. Veritabanı Bağlantı Yönetimi

### POST /api/v1/connections

Yeni bir veritabanı bağlantısı kaydet.

**Request:**
```json
{
  "db_id": "crm_prod",
  "display_name": "CRM Prodüksiyon",
  "db_type": "mssql",
  "connection_string": "mssql+pyodbc://...",
  "description": "Müşteri ilişkileri yönetim sistemi",
  "auto_sync_enabled": true,
  "auto_sync_cron": "0 2 * * *"
}
```

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `db_id` | string | Evet | Sistem genelinde benzersiz kimlik. Slug formatı önerilir: `crm_prod` |
| `display_name` | string | Evet | Kullanıcıya gösterilen ad |
| `db_type` | string | Evet | `mssql`, `postgresql`, `mysql`, `sqlite` |
| `connection_string` | string | Evet | SQLAlchemy URL. Core Backend'de şifreli saklanır |
| `description` | string | Hayır | Bağlantı açıklaması |
| `auto_sync_enabled` | boolean | Hayır | Şema değişiklik takibi açık mı (varsayılan: false) |
| `auto_sync_cron` | string | Hayır | Otomatik extract zamanı (cron syntax) |

**Response 201:**
```json
{
  "db_id": "crm_prod",
  "display_name": "CRM Prodüksiyon",
  "db_type": "mssql",
  "status": "registered",
  "onboarding_status": "pending",
  "created_at": "2026-03-26T10:00:00Z"
}
```

---

### GET /api/v1/connections

Kayıtlı tüm bağlantıları listele.

**Response 200:**
```json
{
  "connections": [
    {
      "db_id": "crm_prod",
      "display_name": "CRM Prodüksiyon",
      "db_type": "mssql",
      "onboarding_status": "ready",
      "table_count": 13,
      "last_synced_at": "2026-03-26T02:00:00Z",
      "auto_sync_enabled": true
    }
  ]
}
```

`onboarding_status` değerleri: `pending` | `extracting` | `enriching` | `ready` | `error`

---

### GET /api/v1/connections/{db_id}

Tek bağlantı detayı.

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "display_name": "CRM Prodüksiyon",
  "db_type": "mssql",
  "description": "Müşteri ilişkileri yönetim sistemi",
  "onboarding_status": "ready",
  "table_count": 13,
  "enriched_table_count": 9,
  "few_shot_count": 5,
  "last_synced_at": "2026-03-26T02:00:00Z",
  "auto_sync_enabled": true,
  "auto_sync_cron": "0 2 * * *",
  "created_at": "2026-03-25T10:00:00Z"
}
```

---

### DELETE /api/v1/connections/{db_id}

Bağlantıyı ve tüm şema verilerini sil (ChromaDB dahil).

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "deleted": true,
  "chroma_docs_removed": 18
}
```

---

## 2. Onboarding Orchestration

### POST /api/v1/connections/{db_id}/extract

AI Backend'e extract isteği gönder, sonucu Core Backend DB'sine kaydet.

Uzun sürebilir — `prefer: respond-async` header'ı ile background job olarak çalıştırılabilir.

**Request:** Body yok.

**Response 200 (sync):**
```json
{
  "db_id": "crm_prod",
  "status": "extracted",
  "table_count": 13,
  "new_tables": ["SalesLT.Address", "SalesLT.CustomerAddress"],
  "removed_tables": [],
  "unchanged_tables": ["SalesLT.Customer", "SalesLT.Product", "SalesLT.SalesOrderHeader"],
  "extracted_at": "2026-03-26T10:05:00Z"
}
```

**Response 202 (async):**
```json
{
  "job_id": "job_abc123",
  "status": "queued",
  "poll_url": "/api/v1/jobs/job_abc123"
}
```

---

### POST /api/v1/connections/{db_id}/publish

Zenginleştirilmiş şemayı AI Backend'e register et (ChromaDB'ye yaz).

Core Backend kendi DB'sinden şu veriyi derler ve AI Backend `/onboard/register` endpoint'ine gönderir:
- `enrichment_status != "ignored"` olan tüm tablolar (kolonlar + description + business_rules)
- Bu `db_id`'ye ait tüm few-shot örnekleri

**Request:** Body yok — Core Backend kendi DB'sinden okur.

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "status": "published",
  "metrics": {
    "indexed_tables": 9,
    "indexed_few_shots": 5,
    "vector_chunks_created": 14
  },
  "published_at": "2026-03-26T10:10:00Z"
}
```

**Response 400:**
```json
{
  "status": "error",
  "error_code": "ENRICHMENT_INCOMPLETE",
  "message": "4 tablo henüz zenginleştirilmedi. Tüm tabloları onaylayıp tekrar deneyin veya force=true gönderin.",
  "detail": {
    "unenriched_tables": ["dbo.BuildVersion", "dbo.ErrorLog", "dbo.sysdiagrams", "SalesLT.ProductModel"]
  }
}
```

**Opsiyonel:** `?force=true` — zenginleştirilmemiş tablolar boş description ile publish edilir.

---

### POST /api/v1/connections/{db_id}/sync

Extract + Publish'i ardışık çalıştır. Şema değişikliği varsa farkı uygular.

**Request:**
```json
{
  "force_republish": false
}
```

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "extract": {
    "table_count": 13,
    "new_tables": [],
    "removed_tables": []
  },
  "publish": {
    "indexed_tables": 9,
    "vector_chunks_created": 14
  },
  "synced_at": "2026-03-26T10:15:00Z"
}
```

---

## 3. Şema Zenginleştirme (Admin)

### GET /api/v1/connections/{db_id}/tables

Bu bağlantının tüm tablolarını listele.

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "tables": [
    {
      "table_name": "SalesLT.Customer",
      "column_count": 15,
      "enrichment_status": "enriched",
      "human_description": "Müşteri bilgilerini tutan ana tablo.",
      "has_business_rules": true,
      "last_updated_at": "2026-03-25T12:00:00Z"
    },
    {
      "table_name": "dbo.BuildVersion",
      "column_count": 4,
      "enrichment_status": "pending",
      "human_description": "",
      "has_business_rules": false,
      "last_updated_at": null
    }
  ]
}
```

`enrichment_status`: `pending` | `enriched` | `ignored`

---

### GET /api/v1/connections/{db_id}/tables/{table_name}

Tek tablo detayı — kolonlar, açıklama, iş kuralları.

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "table_name": "SalesLT.Customer",
  "columns": [
    { "name": "CustomerID", "type": "INTEGER NOT NULL" },
    { "name": "FirstName",  "type": "NVARCHAR(50) NOT NULL" },
    { "name": "LastName",   "type": "NVARCHAR(50) NOT NULL" },
    { "name": "EmailAddress","type": "NVARCHAR(50)" }
  ],
  "human_description": "Müşteri bilgilerini tutan ana tablo.",
  "business_rules": "Ad ve soyadı birleştirmek için FirstName + ' ' + LastName kullan.",
  "enrichment_status": "enriched",
  "last_updated_at": "2026-03-25T12:00:00Z"
}
```

---

### PUT /api/v1/connections/{db_id}/tables/{table_name}

Tablo zenginleştirmesini güncelle.

**Request:**
```json
{
  "human_description": "Müşteri bilgilerini tutan ana tablo. B2B ve B2C müşterileri içerir.",
  "business_rules": "Ad ve soyadı birleştirmek için FirstName + ' ' + LastName kullan. EmailAddress NULL olabilir.",
  "enrichment_status": "enriched"
}
```

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "table_name": "SalesLT.Customer",
  "enrichment_status": "enriched",
  "updated_at": "2026-03-26T10:20:00Z",
  "publish_required": true
}
```

> `publish_required: true` — güncelleme var, ChromaDB henüz eski versiyon. `/publish` çağrılmalı.

---

### PUT /api/v1/connections/{db_id}/tables/{table_name}/ignore

Tabloyu onboarding'den dışla (sistem tabloları için: `dbo.sysdiagrams` vb.).

**Response 200:**
```json
{
  "table_name": "dbo.sysdiagrams",
  "enrichment_status": "ignored"
}
```

---

### GET /api/v1/connections/{db_id}/few-shots

Bu bağlantıya ait few-shot örneklerini listele.

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "few_shots": [
    {
      "id": "fs_001",
      "question": "En çok sipariş veren 5 müşteri kimdir?",
      "sql": "SELECT TOP 5 ...",
      "created_at": "2026-03-25T12:00:00Z"
    }
  ]
}
```

---

### POST /api/v1/connections/{db_id}/few-shots

Yeni few-shot örneği ekle.

**Request:**
```json
{
  "question": "Geçen ay en çok satan ürün hangisi?",
  "sql": "SELECT TOP 1 p.Name, SUM(sod.LineTotal) AS TotalSales FROM SalesLT.Product p JOIN SalesLT.SalesOrderDetail sod ON p.ProductID = sod.ProductID JOIN SalesLT.SalesOrderHeader soh ON sod.SalesOrderID = soh.SalesOrderID WHERE soh.OrderDate >= DATEADD(MONTH, -1, GETDATE()) GROUP BY p.Name ORDER BY TotalSales DESC"
}
```

**Response 201:**
```json
{
  "id": "fs_006",
  "question": "Geçen ay en çok satan ürün hangisi?",
  "sql": "SELECT TOP 1 ...",
  "created_at": "2026-03-26T10:25:00Z",
  "publish_required": true
}
```

---

### DELETE /api/v1/connections/{db_id}/few-shots/{id}

Few-shot örneğini sil.

**Response 200:**
```json
{ "id": "fs_006", "deleted": true, "publish_required": true }
```

---

## 4. Sorgu Çalıştırma

Kullanıcının sorduğu soruyu uçtan uca çalıştırır:

```
1. sql_cache kontrol → HIT ise SQL direkt al
2. AI Backend → POST /api/v1/generate-sql → sql_query al
3. Core Backend → SQL'i hedef DB'de çalıştır → gerçek veri döndür
```

### POST /api/v1/query

**Request:**
```json
{
  "db_id": "crm_prod",
  "question": "En çok sipariş veren 5 müşteriyi getir",
  "user_id": "user-456",
  "max_rows": 100,
  "dry_run_limit": 5
}
```

| Alan | Tip | Zorunlu | Açıklama |
|---|---|---|---|
| `db_id` | string | Evet | Hedef veritabanı |
| `question` | string | Evet | Doğal dil sorusu (max 2000 karakter) |
| `user_id` | string | Hayır | Denetim için kullanıcı kimliği |
| `max_rows` | integer | Hayır | Döndürülecek maks satır sayısı (varsayılan: 100, max: 1000) |
| `dry_run_limit` | integer | Hayır | AI Backend dry-run için satır limiti (varsayılan: 5) |

**Response 200 (başarı):**
```json
{
  "status": "success",
  "query_id": "qry_abc123",
  "question": "En çok sipariş veren 5 müşteriyi getir",
  "sql_query": "SELECT TOP 5 c.CustomerID, c.FirstName + ' ' + c.LastName AS CustomerName, COUNT(soh.SalesOrderID) AS OrderCount FROM SalesLT.Customer c JOIN SalesLT.SalesOrderHeader soh ON c.CustomerID = soh.CustomerID GROUP BY c.CustomerID, c.FirstName, c.LastName ORDER BY OrderCount DESC",
  "explanation": "SalesLT.Customer ve SalesLT.SalesOrderHeader tablolarını birleştirerek sipariş sayısını hesaplar ve en yüksek 5 müşteriyi getirir.",
  "is_validated": true,
  "data": {
    "columns": ["CustomerID", "CustomerName", "OrderCount"],
    "rows": [
      { "CustomerID": 29531, "CustomerName": "Kaitlyn Henderson", "OrderCount": 28 },
      { "CustomerID": 29546, "CustomerName": "Harold Sanz", "OrderCount": 25 }
    ],
    "row_count": 5,
    "truncated": false
  },
  "cached": false,
  "duration_ms": 3240
}
```

**Response 200 (hata — AI Backend'den):**
```json
{
  "status": "error",
  "query_id": "qry_abc124",
  "question": "...",
  "error_code": "SCHEMA_NOT_FOUND",
  "error": "Bu veritabanı için şema kaydı bulunamadı. Lütfen önce onboarding tamamlayın.",
  "data": null
}
```

**Response 200 (hata — execution):**
```json
{
  "status": "error",
  "query_id": "qry_abc125",
  "sql_query": "SELECT TOP 5 ...",
  "is_validated": true,
  "error_code": "EXECUTION_FAILED",
  "error": "Sorgu çalıştırılırken hata oluştu.",
  "data": null
}
```

---

### POST /api/v1/query/stream

Aynı sorgu, SSE ile her adım gerçek zamanlı yayınlanır.

**SSE Event Akışı:**
```
data: {"event": "progress", "node": "retrieve_schema", "message": "Şema aranıyor..."}
data: {"event": "progress", "node": "generate_sql",   "message": "SQL üretiliyor...", "sql_preview": "SELECT TOP 5 ..."}
data: {"event": "progress", "node": "validate_sql",   "message": "SQL doğrulanıyor..."}
data: {"event": "progress", "node": "execute_sql",    "message": "SQL test ediliyor..."}
data: {"event": "progress", "node": "explain_sql",    "message": "Açıklama hazırlanıyor..."}
data: {"event": "executing", "message": "Veriler çekiliyor..."}
data: {"event": "done", "status": "success", "query_id": "qry_abc123", "sql_query": "...", "explanation": "...", "data": {...}}
```

> `executing` eventi: AI Backend tamamlandı, Core Backend gerçek sorguyu çalıştırıyor.

---

## 5. Sorgu Geçmişi

### GET /api/v1/queries

Sorgu geçmişi — filtreli ve sayfalı.

**Query Parameters:**

| Parametre | Tip | Açıklama |
|---|---|---|
| `db_id` | string | Belirli bir DB ile filtrele |
| `user_id` | string | Belirli bir kullanıcı ile filtrele |
| `status` | string | `success` veya `error` |
| `from` | datetime | Başlangıç tarihi (ISO 8601) |
| `to` | datetime | Bitiş tarihi (ISO 8601) |
| `page` | integer | Sayfa numarası (varsayılan: 1) |
| `page_size` | integer | Sayfa boyutu (varsayılan: 20, max: 100) |

**Response 200:**
```json
{
  "total": 142,
  "page": 1,
  "page_size": 20,
  "queries": [
    {
      "query_id": "qry_abc123",
      "db_id": "crm_prod",
      "user_id": "user-456",
      "question": "En çok sipariş veren 5 müşteriyi getir",
      "status": "success",
      "cached": false,
      "duration_ms": 3240,
      "created_at": "2026-03-26T10:30:00Z"
    }
  ]
}
```

---

### GET /api/v1/queries/{query_id}

Tek sorgu detayı — SQL ve veri dahil.

**Response 200:**
```json
{
  "query_id": "qry_abc123",
  "db_id": "crm_prod",
  "user_id": "user-456",
  "question": "En çok sipariş veren 5 müşteriyi getir",
  "sql_query": "SELECT TOP 5 ...",
  "explanation": "...",
  "status": "success",
  "is_validated": true,
  "cached": false,
  "duration_ms": 3240,
  "row_count": 5,
  "created_at": "2026-03-26T10:30:00Z"
}
```

> `data.rows` geçmişte saklanmaz. Veriyi yeniden çekmek için `POST /api/v1/query` ile aynı soruyu tekrar gönderin (cache HIT olur, hızlı döner).
```

---

### POST /api/v1/queries/{query_id}/feedback

Sorgu sonucuna kullanıcı geri bildirimi.

**Request:**
```json
{
  "rating": "positive",
  "comment": "SQL doğru çıktı, sonuçlar beklediğimle örtüşüyor."
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `rating` | string | `positive` veya `negative` |
| `comment` | string | Opsiyonel açıklama |

**Response 200:**
```json
{
  "query_id": "qry_abc123",
  "feedback_saved": true,
  "promote_eligible": true
}
```

`promote_eligible: true` — `rating="positive"` ve `status="success"` koşulları sağlandığında döner. Frontend bu flag'e göre "Few-shot olarak ekle" butonu gösterebilir.

> Negatif feedback → admin panelinde inceleme kuyruğuna düşer. Pozitif feedback → `promote_eligible=true` ile few-shot adayı olarak işaretlenebilir.

---

### POST /api/v1/queries/{query_id}/promote-to-few-shot

Başarılı bir sorguyu few-shot örneği olarak ekle.

**Response 201:**
```json
{
  "id": "fs_007",
  "db_id": "crm_prod",
  "question": "En çok sipariş veren 5 müşteriyi getir",
  "sql": "SELECT TOP 5 ...",
  "publish_required": true
}
```

---

## 6. Sync ve Zamanlama

### GET /api/v1/connections/{db_id}/sync-status

Son sync durumu ve schema diff özeti.

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "last_extract_at": "2026-03-26T02:00:00Z",
  "last_publish_at": "2026-03-26T02:05:00Z",
  "publish_required": false,
  "schema_changes": {
    "new_tables": [],
    "removed_tables": []
  },
  "enrichment_status": {
    "unenriched_tables": ["dbo.BuildVersion", "dbo.ErrorLog"],
    "ignored_tables": ["dbo.sysdiagrams"]
  },
  "next_auto_sync_at": "2026-03-27T02:00:00Z"
}
```

---

### POST /api/v1/connections/{db_id}/sync-settings

Otomatik sync ayarlarını güncelle.

**Request:**
```json
{
  "auto_sync_enabled": true,
  "auto_sync_cron": "0 2 * * *",
  "notify_on_schema_change": true,
  "notify_email": "admin@example.com"
}
```

**Response 200:**
```json
{
  "db_id": "crm_prod",
  "auto_sync_enabled": true,
  "auto_sync_cron": "0 2 * * *",
  "next_run_at": "2026-03-27T02:00:00Z"
}
```

---

### GET /api/v1/jobs/{job_id}

Background job durumunu sorgula (async extract/publish için).

**Response 200:**
```json
{
  "job_id": "job_abc123",
  "type": "extract",
  "db_id": "crm_prod",
  "status": "completed",
  "result": {
    "table_count": 13,
    "new_tables": ["SalesLT.Address"],
    "removed_tables": []
  },
  "started_at": "2026-03-26T10:05:00Z",
  "completed_at": "2026-03-26T10:05:12Z"
}
```

`status`: `queued` | `running` | `completed` | `failed`

---

## 7. Ops

### GET /health

```json
{
  "status": "ok",
  "service": "nl2sql-core-backend",
  "version": "1.0.0",
  "dependencies": {
    "ai_backend": "ok",
    "database": "ok"
  }
}
```

### GET /api/v1/stats

Sistem geneli istatistikler.

**Response 200:**
```json
{
  "connections": {
    "total": 3,
    "ready": 2,
    "pending": 1
  },
  "queries": {
    "total_today": 142,
    "success_rate": 0.94,
    "avg_duration_ms": 2850,
    "cache_hit_rate": 0.38
  },
  "ai_backend": {
    "cache_total_entries": 87,
    "cache_active_entries": 82
  }
}
```

---

## 8. Veri Modelleri

### Connection

```
db_id                    string   PK
display_name             string
db_type                  enum     mssql | postgresql | mysql | sqlite
connection_string        string   şifreli
description              string
onboarding_status        enum     pending | extracting | enriching | ready | error
table_count              integer
enriched_table_count     integer
few_shot_count           integer
last_extract_at          datetime
last_publish_at          datetime
auto_sync_enabled        boolean
auto_sync_cron           string
notify_on_schema_change  boolean
notify_email             string
created_at               datetime
updated_at               datetime
```

### Table

```
id                  uuid     PK
db_id               string   FK → Connection
table_name          string
columns             jsonb    [{"name": ..., "type": ...}]
human_description   string
business_rules      string
enrichment_status   enum     pending | enriched | ignored
last_updated_at     datetime
```

### FewShot

```
id          string   PK
db_id       string   FK → Connection
question    string
sql         string
created_at  datetime
created_by  string
```

### Query

```
query_id      string   PK
db_id         string   FK → Connection
user_id       string
question      string
sql_query     string
explanation   string
status        enum     success | error
error_code    string
is_validated  boolean
cached        boolean
duration_ms   integer
row_count     integer  -- persist edilen sayı; rows kendisi saklanmaz (boyut)
created_at    datetime
```

> `data.rows` alanı yalnızca sorgu anında döndürülür, DB'ye yazılmaz. Geçmiş sorgu detayında (`GET /queries/{id}`) `data` alanı bulunmaz, yalnızca `row_count` gösterilir.

### Feedback

```
id          uuid   PK
query_id    string FK → Query
rating      enum   positive | negative
comment     string
created_at  datetime
```

---

## 9. Hata Formatı

Tüm hata yanıtları aynı yapıyı kullanır:

```json
{
  "status": "error",
  "error_code": "ENRICHMENT_INCOMPLETE",
  "message": "İnsan tarafından okunabilir hata açıklaması.",
  "detail": {}
}
```

### Hata Kodları

| Kod | HTTP | Açıklama |
|---|---|---|
| `CONNECTION_NOT_FOUND` | 404 | db_id kayıtlı değil |
| `CONNECTION_FAILED` | 400 | DB'ye bağlanılamadı |
| `EXTRACT_FAILED` | 502 | AI Backend extract hatası |
| `ENRICHMENT_INCOMPLETE` | 400 | Zenginleştirilmemiş tablo var |
| `PUBLISH_FAILED` | 502 | AI Backend register hatası |
| `AI_BACKEND_UNAVAILABLE` | 503 | AI Backend'e ulaşılamıyor |
| `SQL_GENERATION_FAILED` | 422 | AI Backend SQL üretemedi |
| `SCHEMA_NOT_FOUND` | 422 | ChromaDB'de şema yok (publish yapılmamış) |
| `EXECUTION_FAILED` | 500 | SQL çalıştırma hatası |
| `MAX_ROWS_EXCEEDED` | 400 | max_rows limiti aşıldı |
| `QUERY_NOT_FOUND` | 404 | query_id bulunamadı |

---

## Tipik Akışlar

### Yeni Veritabanı Onboarding

```
1. POST /api/v1/connections                    → bağlantı kaydet
2. POST /api/v1/connections/{db_id}/extract    → şemayı çek
3. PUT  /api/v1/connections/{db_id}/tables/{t} → her tabloyu zenginleştir (×N)
4. POST /api/v1/connections/{db_id}/few-shots  → örnek sorgular ekle (×N)
5. POST /api/v1/connections/{db_id}/publish    → ChromaDB'ye yaz
6. POST /api/v1/query                          → test sorgusu
```

### Şema Güncellemesi

```
1. POST /api/v1/connections/{db_id}/sync       → extract + fark tespit
   → Yanıtta new_tables varsa:
2. PUT  /api/v1/connections/{db_id}/tables/{t} → yeni tabloları zenginleştir
3. POST /api/v1/connections/{db_id}/publish    → ChromaDB güncelle
```

### Kullanıcı Sorgusu (Frontend → Core Backend)

```
1. POST /api/v1/query/stream                   → SSE ile izle
   ├── AI Backend: retrieve → generate → validate → execute → explain
   └── Core Backend: gerçek veriyi çek
2. POST /api/v1/queries/{id}/feedback          → olumlu/olumsuz geri bildirim
3. POST /api/v1/queries/{id}/promote-to-few-shot → başarılı sorguyu örnek yap
4. POST /api/v1/connections/{db_id}/publish    → few-shot güncellendi, ChromaDB yenile
```
