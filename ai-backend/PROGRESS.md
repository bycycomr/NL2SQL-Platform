# NL2SQL AI Backend – İlerleme Raporu

## Proje Nedir?

NL2SQL AI Backend, kullanıcıların **doğal dilde sordukları soruları otomatik olarak SQL sorgularına çeviren**, sorguyu **hedef veritabanında çalıştıran** ve sonuçları döndüren **çok kiracılı (multi-tenant)** bir mikroservistir.

- **Girdi:** Doğal dil sorusu + hedef veritabanı bilgisi (`db_id`, `connection_string`)
- **Çıktı:** Doğrulanmış SQL sorgusu + Türkçe açıklama + sorgu sonuç verisi

---

## Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| Web Framework | FastAPI (async) |
| AI Orkestrasyon | LangGraph (StateGraph) |
| LLM | Llama 3.1 8B (lokal Ollama) |
| SQL Güvenliği | sqlglot AST + Regex |
| Vektör DB (RAG) | ChromaDB |
| DB İntrospeksiyon | SQLAlchemy |
| Modeller | Pydantic v2 |

---

## Mevcut Dosya Yapısı

```
ai-backend/
├── main.py                  # FastAPI uygulama giriş noktası
├── requirements.txt         # Bağımlılıklar
├── core/
│   ├── config.py            # Ortam değişkenleri / ayarlar (LLM, ChromaDB vb.)
│   └── security.py          # SQL doğrulama (regex + AST) → str | None
├── api/
│   ├── schemas.py           # Pydantic modelleri (Query + Onboarding)
│   └── routes.py            # 3 endpoint: extract, register, generate-sql
├── agent/
│   ├── state.py             # AgentState TypedDict (db_id, connection_string, execution_data vb.)
│   ├── prompts.py           # Türkçe sistem prompt şablonları
│   ├── nodes.py             # 5 LangGraph düğüm fonksiyonu
│   └── graph.py             # StateGraph tanımı ve derleme
└── services/
    ├── llm.py               # ChatOllama bağlantısı
    ├── db_inspector.py      # SQLAlchemy introspection + read-only execution
    └── vector_store.py      # ChromaDB: şema kayıt / semantik arama (db_id filtreli)
```

---

## Tamamlanan Adımlar

### Adım 1 – Proje İskeleti ✅
- Dizin yapısı ve tüm modüller oluşturuldu
- `requirements.txt` güncellendi (langchain, langgraph, sqlglot, langchain-ollama vb.)

### Adım 2 – API & Modeller ✅
- **Pydantic modelleri:** `NL2SQLRequest` / `NL2SQLResponse`
- **FastAPI endpoint:** `POST /api/v1/generate-sql`
- **Health check:** `GET /health`
- **SQL güvenlik katmanı:** 2 katmanlı doğrulama (regex + sqlglot AST)

### Adım 3 – Çekirdek AI Mantığı ✅
- **`services/llm.py`** – `ChatOllama` singleton, `llama3.1:8b-instruct-q4_K_M` modeli
- **`agent/nodes.py`** – 4 async düğüm (retrieve → generate → validate → explain)
- **`agent/graph.py`** – LangGraph StateGraph (koşullu retry döngüsü dahil)
- **`api/routes.py`** – Endpoint, gerçek LangGraph agent'ına bağlandı

### Adım 4 – V2 Refaktör: Multi-Tenant & Execution ✅
- **`agent/state.py`** – `db_id`, `connection_string`, `execution_data` alanları eklendi
- **`api/schemas.py`** – Onboarding modelleri eklendi:
  - `ExtractSchemaRequest` / `ExtractSchemaResponse` / `TableSchema` / `RegisterSchemaRequest`
  - `NL2SQLRequest`'e `db_id` + `connection_string` eklendi
  - `NL2SQLResponse`'a `data` (sorgu sonuçları) alanı eklendi
- **`services/db_inspector.py`** – **YENİ**: SQLAlchemy ile:
  - `get_schema()` → tablo/kolon introspection
  - `execute_read_only()` → `SET SESSION READ ONLY` + sorgu çalıştırma
- **`services/vector_store.py`** – **YENİ**: ChromaDB entegrasyonu:
  - `save_schema_chunks()` → DDL + few-shot örneklerini `db_id` metadata ile kayıt
  - `retrieve_relevant_schema()` → Semantik arama (`db_id` filtreli)
  - `delete_schema()` → Belirli bir DB'nin şemasını silme
- **`agent/nodes.py`** – 5 düğüme güncellendi:
  1. `retrieve_schema_node` → ChromaDB'den şema getirme
  2. `generate_sql_node` → LLM ile SQL üretme (Türkçe prompt)
  3. `validate_sql_node` → Güvenlik doğrulaması (`str | None` API)
  4. `execute_sql_node` → **YENİ**: Hedef DB'de read-only sorgu çalıştırma
  5. `explain_sql_node` → LLM ile Türkçe açıklama
- **`agent/graph.py`** – `execute_sql` düğümü eklendi (`validate → execute → explain`)
- **`api/routes.py`** – 2 yeni onboarding endpoint:
  - `POST /api/v1/onboard/extract` → Otomatik şema çıkarma
  - `POST /api/v1/onboard/register` → Zenginleştirilmiş şemayı ChromaDB'ye kayıt
- **`core/security.py`** – `validate_sql()` artık `str | None` döndürüyor
- **`core/config.py`** – `CHROMA_PERSIST_DIR` ayarı eklendi
- **`agent/prompts.py`** – Tüm promptlar Türkçe

---

## Nasıl Çalışır?

### Onboarding Akışı
```
1. POST /api/v1/onboard/extract   →  DB'ye bağlan, şemaları çıkar
2. İnsan şemaları zenginleştirir  →  description, business_rules, few-shot ekler
3. POST /api/v1/onboard/register  →  ChromaDB'ye kaydet
```

### Sorgu Akışı
```
Kullanıcı Sorusu (db_id + connection_string)
       │
       ▼
  Şema Getir (ChromaDB, db_id filtreli)
       │
       ▼
  SQL Üret (Llama 3.1, Türkçe prompt)
       │
       ▼
  SQL Doğrula ──────┐
       │            │ Hata varsa & retry < 3
       │            └──► SQL Üret (tekrar dene)
       ▼
  SQL Çalıştır (hedef DB, read-only)
       │
       ▼
  SQL Açıkla (Llama 3.1, Türkçe)
       │
       ▼
  JSON Yanıt { sql_query, explanation, data, status }
```

---

## API Endpoints

| Metod | Path | Açıklama |
|---|---|---|
| `GET` | `/health` | Sağlık kontrolü |
| `POST` | `/api/v1/onboard/extract` | DB şemasını otomatik çıkar |
| `POST` | `/api/v1/onboard/register` | Zenginleştirilmiş şemayı kaydet |
| `POST` | `/api/v1/generate-sql` | NL → SQL → çalıştır → açıkla |

---

## Güvenlik

- **Regex katmanı:** `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `MERGE`, `EXEC` anında engellenir
- **AST katmanı:** `sqlglot` ile parse edilerek DML/DDL ifade tipleri tespit edilir
- `ParseError` / `TokenError` yakalanıp açıklayıcı hata döner
- **Read-only execution:** `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`

### Adım 5 – Çapraz DBMS Uyumluluk & Güvenlik İyileştirmeleri ✅
- **`services/db_inspector.py`** – Multi-DBMS şema introspection'a güncellendi:
  - Tüm şemalar taranıyor (`inspector.get_schema_names()`)
  - Evrensel sistem şema karalistesi: MSSQL (`sys`, `information_schema`), PostgreSQL (`pg_catalog`, `pg_toast`), MySQL (`mysql`, `performance_schema`), Oracle (`ctxsys`, `mdsys` vb.), SQLite (`sqlite_master` vb.)
  - Şema destekleyen DB'ler için `schema.table` isimlendirmesi, desteklemeyenler için sadece `table`
  - `human_description` ve `business_rules` alanları introspection çıktısına eklendi
  - Hata toleransı: Şema okunamazsa `continue` ile devam
- **`core/security.py`** – sqlglot T-SQL dialect desteği eklendi:
  - `sqlglot.parse(cleaned, read="tsql")` ile MS SQL Server sorgularını doğru parse ediyor

---

## Kalan İşler

- [ ] Uçtan uca test (Ollama + gerçek DB ile)
- [ ] Prometheus metrikleri / yapısal loglama
- [ ] Docker Compose ile tam entegrasyon testi
- [ ] Rate limiting / authentication
- [ ] Few-shot örnekleri ile prompt zenginleştirme
