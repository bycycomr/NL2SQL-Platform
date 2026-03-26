"""
Pydantic request / response models for the NL2SQL AI Backend.

API Contract v2.0 — Hibrit Mimari:
  AI Backend yalnızca SQL üretir ve dry-run ile doğrular.
  Gerçek veri çekimi Core Backend tarafından yapılır.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


# ---------------------------------------------------------------------------
# Ortak Alt Modeller
# ---------------------------------------------------------------------------

class ColumnSchema(BaseModel):
    """Tek bir kolon: ad ve tip."""

    model_config = ConfigDict(json_schema_extra={
        "example": {"name": "CustomerID", "type": "INTEGER NOT NULL"}
    })

    name: str
    type: str


class TableSchema(BaseModel):
    """Bir tablonun metadata'sı (otomatik çekilen + insan tarafından zenginleştirilen).

    Not: /onboard/extract endpoint'inden dönen tablolarda human_description ve
    business_rules her zaman boş string olarak gelir — DBInspector bu alanları
    doldurmaz. Bu alanlar insan uzmanlar tarafından /onboard/register'a
    gönderilmeden önce doldurulur.
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "table_name": "SalesLT.Customer",
            "columns": [
                {"name": "CustomerID", "type": "INTEGER NOT NULL"},
                {"name": "FirstName",  "type": "NVARCHAR(50) NOT NULL"},
                {"name": "LastName",   "type": "NVARCHAR(50) NOT NULL"},
                {"name": "EmailAddress", "type": "NVARCHAR(50)"},
            ],
            "human_description": "Müşteri bilgilerini tutan ana tablo.",
            "business_rules": "Ad ve soyadı birleştirmek için FirstName + ' ' + LastName kullan.",
        }
    })

    table_name: str
    columns: list[ColumnSchema]
    human_description: str = ""
    business_rules: str = ""


# ---------------------------------------------------------------------------
# Onboarding — Step 1: Extract
# ---------------------------------------------------------------------------

class ExtractSchemaRequest(BaseModel):
    """Hedef veritabanından otomatik şema çıkarmak için istek."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "db_id": "adv_works_local",
            "db_type": "mssql",
            "connection_string": "mssql+pyodbc://@localhost/AdventureWorksLT2025?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes",
        }
    })

    db_id: str = Field(..., description="Tenant veya veritabanı kimliği.")
    db_type: str = Field(
        default="",
        description="Veritabanı türü (postgresql, mssql, mysql, sqlite). Bilgilendirme amaçlıdır, bağlantı tipini connection_string belirler.",
    )
    connection_string: str = Field(..., description="SQLAlchemy bağlantı dizesi.")


class ExtractSchemaResponse(BaseModel):
    """Otomatik çekilen ham şema — insan zenginleştirmesi için döndürülür.

    Önemli: Dönen tablolarda human_description ve business_rules her zaman
    boş string ("") olarak gelir. Bu alanlar extract tarafından doldurulmaz;
    insan uzmanlar tarafından zenginleştirilerek /onboard/register'a gönderilir.
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "db_id": "adv_works_local",
            "message": "5 tablo başarıyla okundu.",
            "tables": [
                {
                    "table_name": "SalesLT.Customer",
                    "columns": [
                        {"name": "CustomerID", "type": "INTEGER NOT NULL"},
                        {"name": "FirstName",  "type": "NVARCHAR(50) NOT NULL"},
                        {"name": "LastName",   "type": "NVARCHAR(50) NOT NULL"},
                        {"name": "EmailAddress", "type": "NVARCHAR(50)"},
                    ],
                    "human_description": "",
                    "business_rules": "",
                },
                {
                    "table_name": "SalesLT.Product",
                    "columns": [
                        {"name": "ProductID",   "type": "INTEGER NOT NULL"},
                        {"name": "Name",        "type": "NVARCHAR(50) NOT NULL"},
                        {"name": "ListPrice",   "type": "MONEY NOT NULL"},
                        {"name": "Color",       "type": "NVARCHAR(15)"},
                    ],
                    "human_description": "",
                    "business_rules": "",
                },
            ],
        }
    })

    status: str = "success"
    db_id: str
    message: str
    tables: list[TableSchema]


# ---------------------------------------------------------------------------
# Onboarding — Step 2: Register
# ---------------------------------------------------------------------------

class RegisterSchemaRequest(BaseModel):
    """İnsan tarafından zenginleştirilmiş şemayı ve few-shot örneklerini kaydet."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "db_id": "adv_works_local",
            "mode": "upsert",
            "tables": [
                {
                    "table_name": "SalesLT.Customer",
                    "columns": [
                        {"name": "CustomerID", "type": "INTEGER NOT NULL"},
                        {"name": "FirstName",  "type": "NVARCHAR(50) NOT NULL"},
                        {"name": "LastName",   "type": "NVARCHAR(50) NOT NULL"},
                    ],
                    "human_description": "Müşteri bilgilerini tutan ana tablo.",
                    "business_rules": "Ad ve soyadı birleştirmek için FirstName + ' ' + LastName kullan.",
                }
            ],
            "few_shot_examples": [
                {
                    "question": "Kaç müşteri var?",
                    "query": "SELECT COUNT(*) AS TotalCustomers FROM SalesLT.Customer",
                },
                {
                    "question": "En çok sipariş veren 5 müşteriyi getir",
                    "query": "SELECT TOP 5 c.CustomerID, c.FirstName + ' ' + c.LastName AS CustomerName, COUNT(soh.SalesOrderID) AS OrderCount FROM SalesLT.Customer c JOIN SalesLT.SalesOrderHeader soh ON c.CustomerID = soh.CustomerID GROUP BY c.CustomerID, c.FirstName, c.LastName ORDER BY OrderCount DESC",
                },
            ],
        }
    })

    db_id: str = Field(..., description="Tenant veya veritabanı kimliği.")
    mode: str = Field(default="upsert", description="'upsert': mevcut şemanın üzerine yaz.")
    tables: list[TableSchema]
    few_shot_examples: list[dict[str, Any]] = Field(
        default=[],
        description=(
            "Örnek soru–SQL çiftleri. Her eleman {'question': ..., 'query': ...} "
            "veya {'question': ..., 'sql': ...} formatında olabilir — ikisi de kabul edilir."
        ),
    )


class RegisterSchemaMetrics(BaseModel):
    """Kayıt işleminin istatistikleri."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "indexed_tables": 5,
            "indexed_few_shots": 3,
            "vector_chunks_created": 8,
        }
    })

    indexed_tables: int
    indexed_few_shots: int
    vector_chunks_created: int


class RegisterSchemaResponse(BaseModel):
    """Şema kayıt işleminin sonucu."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "db_id": "adv_works_local",
            "message": "'adv_works_local' için zenginleştirilmiş şema ve örnek sorgular ChromaDB'ye başarıyla indekslendi.",
            "metrics": {
                "indexed_tables": 5,
                "indexed_few_shots": 3,
                "vector_chunks_created": 8,
            },
        }
    })

    status: str
    db_id: str
    message: str
    metrics: RegisterSchemaMetrics


# ---------------------------------------------------------------------------
# SQL Üretme
# ---------------------------------------------------------------------------

class NL2SQLRequest(BaseModel):
    """Doğal dil → SQL dönüşümü için istek (çok kiracılı)."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "db_id": "adv_works_local",
            "connection_string": "mssql+pyodbc://@localhost/AdventureWorksLT2025?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes",
            "query": "En çok sipariş veren 5 müşteriyi getir",
            "dry_run_limit": 5,
            "user_id": "user-123",
        }
    })

    db_id: str = Field(..., description="Hedef veritabanı kimliği.")
    connection_string: str = Field(..., description="Dry-run doğrulaması için DB bağlantı dizesi.")
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Kullanıcının doğal dil sorusu.",
        examples=["En çok sipariş veren 5 müşteriyi getir"],
    )
    dry_run_limit: int | None = Field(
        default=None,
        ge=1,
        description="Dahili dry-run doğrulaması için satır limiti. Döndürülen SQL'de LIMIT bulunmaz.",
    )
    user_id: str | None = Field(
        default=None,
        description="Opsiyonel çağıran kimliği (denetim için).",
    )

    @field_validator("connection_string")
    @classmethod
    def validate_connection_string(cls, value: str) -> str:
        """SQLAlchemy URL formatını erken doğrula — ajan döngüsüne girmeden hata ver."""
        try:
            make_url(value)
        except ArgumentError as exc:
            raise ValueError(
                "Geçersiz connection_string. SQLAlchemy URL formatı bekleniyor. "
                "Örnek: postgresql://user:pass@host:5432/db"
            ) from exc
        return value


class NL2SQLResponse(BaseModel):
    """SQL üretme işleminin sonucu.

    Hibrit Mimari Notu:
        Bu yanıt veri içermez. AI Backend yalnızca doğrulanmış SQL'i döndürür.
        Gerçek veri çekimi Core Backend tarafından yapılır.

    HTTP Status Notu:
        Bu endpoint her zaman HTTP 200 döndürür. Hata durumu body'deki
        status ("error") ve error_code alanlarıyla belirlenir.
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "success",
            "sql_query": "SELECT TOP 5 c.CustomerID, c.FirstName + ' ' + c.LastName AS CustomerName, COUNT(soh.SalesOrderID) AS OrderCount FROM SalesLT.Customer c JOIN SalesLT.SalesOrderHeader soh ON c.CustomerID = soh.CustomerID GROUP BY c.CustomerID, c.FirstName, c.LastName ORDER BY OrderCount DESC",
            "explanation": "SalesLT.Customer ve SalesLT.SalesOrderHeader tablolarını birleştirerek her müşterinin sipariş sayısını hesaplar ve en yüksek 5 müşteriyi sıralar.",
            "is_validated": True,
            "impact_rows": 0,
            "error": None,
            "error_code": None,
        }
    })

    status: str = Field(..., description="'success' veya 'error'.")
    sql_query: str | None = Field(default=None, description="Üretilen ve doğrulanan SQL sorgusu (LIMIT içermez).")
    explanation: str | None = Field(default=None, description="Sorgunun Türkçe açıklaması.")
    is_validated: bool = Field(default=False, description="SQL'in güvenlik ve sözdizimi kontrolünden geçip geçmediği.")
    impact_rows: int = Field(default=0, description="Etkilenen satır sayısı (ilerleyen fazda DML için kullanılacak, şimdilik her zaman 0).")
    error: str | None = Field(default=None, description="Hata mesajı (başarısız durumlarda).")
    error_code: str | None = Field(
        default=None,
        description="Makine tarafından okunabilir hata kodu.",
        examples=["SQL_VALIDATION_FAILED", "SCHEMA_NOT_FOUND", "AGENT_ERROR"],
    )
