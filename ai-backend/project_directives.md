# SYSTEM CONTEXT & IMPLEMENTATION DIRECTIVE FOR AI CODER AGENT (V2 - MULTI-TENANT & EXECUTION)

## 1. PROJECT OVERVIEW
**Project:** NL2SQL (Natural Language to SQL) AI Backend Engine.
**Role:** You are the AI Backend Developer Agent. Your task is to upgrade the existing NL2SQL microservice into a **Multi-Tenant, Dynamic RAG-based, and Execution-capable** system.
**Tech Stack:** Python 3.10+, FastAPI, LangGraph, LangChain, Pydantic, SQLAlchemy (for DB introspection/execution), ChromaDB (for Vector RAG), local LLM inference.
**Target Model:** `llama3.1:8b-instruct-q4_K_M` (Locally hosted, accessed via Ollama/vLLM bindings).

## 2. ARCHITECTURAL CONSTRAINTS & WORKSPACE
* **Workspace:** ALL development MUST be created strictly inside the `/ai-backend` directory. Do not modify or create files outside of this root folder.
* **Isolation:** This is a backend-only AI service. Do NOT build frontends.
* **Multi-Tenant RAG:** The system MUST support multiple databases. Database schemas are stored in ChromaDB and retrieved by `db_id`.
* **Human-in-the-Loop Onboarding:** Database onboarding is a two-step process: (1) Auto-extract schema via SQLAlchemy, (2) Register human-enriched schema into ChromaDB.
* **Read-Only Execution:** The AI Backend WILL execute the generated and validated SQL query against the target database. Execution MUST be strictly read-only.
* **Security Strictness:** The system MUST strictly block any DML operations (INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER) via AST parsing and Regex before execution.

## 3. DIRECTORY STRUCTURE
Implement the project using the following modular structure inside `/ai-backend`:

```text
/ai-backend
├── main.py                 # FastAPI application instance and router inclusion
├── requirements.txt        # Project dependencies (add sqlalchemy, chromadb)
├── core/
│   ├── config.py           # Environment variables and settings
│   └── security.py         # AST/Regex SQL validation logic (Must catch ParseError/TokenError)
├── api/
│   ├── routes.py           # FastAPI endpoints (/api/v1/...)
│   └── schemas.py          # Pydantic models (Request/Response for Query and Onboarding)
├── agent/
│   ├── graph.py            # LangGraph StateGraph definition, edges, and compilation
│   ├── nodes.py            # Node functions (retrieve, generate, validate, execute, explain)
│   ├── state.py            # AgentState TypedDict definition
│   └── prompts.py          # System prompt templates
└── services/
    ├── llm.py              # LLM binding configurations (ChatOllama)
    ├── db_inspector.py     # NEW: SQLAlchemy logic to extract schemas and execute SQL
    └── vector_store.py     # NEW: ChromaDB integration for RAG (saving/retrieving chunks by db_id)
4. LANGGRAPH STATE MACHINE DESIGN
4.1 State Definition (agent/state.py)
Python
from typing import TypedDict, Any

class AgentState(TypedDict):
    db_id: str
    connection_string: str
    question: str
    relevant_schema: str
    generated_sql: str
    validation_error: str | None
    explanation: str
    execution_data: list[dict[str, Any]] | None
    retry_count: int
4.2 Graph Routing & Logic (agent/nodes.py & agent/graph.py)
Node 1 (retrieve_schema_node): Fetches relevant DDL/Schema from ChromaDB using semantic search, filtered by state["db_id"].

Node 2 (generate_sql_node): Calls Llama 3.1. Injects schema. If validation_error exists, instructs the model to fix it.

Node 3 (validate_sql_node): Validates generated_sql. If valid, proceeds. If invalid (DML detected or syntax error), sets validation_error and loops back to Node 2 (max 3 retries).

Node 4 (execute_sql_node): [NEW] Connects to the database using state["connection_string"], executes state["generated_sql"] safely, and stores results in state["execution_data"].

Node 5 (explain_sql_node): Calls LLM to explain the logic of the validated SQL in Turkish.

5. SYSTEM PROMPT TEMPLATES (agent/prompts.py)
Use the following strict prompts to force pure outputs and Turkish explanations:

SQL_GENERATION_PROMPT:

Plaintext
Sen bir SQL Veri Analisti uzmanısın. 
Görevin, aşağıda verilen veritabanı şemasını kullanarak kullanıcının sorusuna yönelik optimize edilmiş ve geçerli bir SQL sorgusu üretmektir.

### VERİTABANI ŞEMASI:
{schema}

### KESİN KURALLAR:
1. Sadece ve sadece geçerli SQL sorgusu döndür. 
2. Asla açıklama, selamlama veya giriş cümlesi yazma.
3. SQL sorgusunu ```sql ... ``` gibi markdown blokları içine ALMA. Sadece ham metin (raw text) döndür.
4. Sadece SELECT işlemlerine izin verilir. DROP, DELETE, INSERT, UPDATE, ALTER, CREATE gibi işlemleri içeren sorgu üretmek KESİNLİKLE YASAKTIR.
5. Eğer bir önceki denemende hata yaptıysan, aşağıda belirtilen hatayı tekrarlamayacak şekilde sorguyu düzelt.

### ÖNCEKİ DENEME HATASI (Varsa):
{validation_error}

### KULLANICI SORUSU:
{question}

SQL:
SQL_EXPLAIN_PROMPT:

Plaintext
Sen bir Veri Çevirmenisin.
Aşağıdaki SQL sorgusunun mantığını, teknik bilgisi olmayan birinin anlayabileceği şekilde, sade ve doğal bir dille açıkla.

### KURALLAR:
1. Açıklamayı her zaman TÜRKÇE yap.
2. Hangi tabloların kullanıldığını, hangi filtrelerin uygulandığını ve sonucun neyi temsil ettiğini belirt.
3. Maksimum 3 cümle kullan.
4. "İşte sorgunun açıklaması:" gibi kalıplar kullanma, doğrudan açıklamaya gir.

### SQL SORGUSU:
{sql_query}

### KULLANICI SORUSU:
{question}

TÜRKÇE AÇIKLAMA:
6. API CONTRACTS (api/schemas.py)
Implement the following Pydantic models for the new Multi-Tenant and Onboarding flows:

Python
from pydantic import BaseModel, Field
from typing import Any

# --- ONBOARDING FLOW ---
class ExtractSchemaRequest(BaseModel):
    db_id: str
    connection_string: str

class TableSchema(BaseModel):
    name: str
    columns: list[str]
    human_description: str = ""
    business_rules: str = ""

class ExtractSchemaResponse(BaseModel):
    db_id: str
    tables: list[TableSchema]
    few_shot_examples: list[dict] = []

class RegisterSchemaRequest(BaseModel):
    db_id: str
    tables: list[TableSchema]
    few_shot_examples: list[dict]

# --- QUERY FLOW ---
class NL2SQLRequest(BaseModel):
    db_id: str = Field(..., description="Target database ID")
    connection_string: str = Field(..., description="DB connection string for execution")
    query: str = Field(..., example="Hangi departmanda en çok çalışan var?")
    user_id: str | None = None

class NL2SQLResponse(BaseModel):
    sql_query: str | None
    explanation: str | None
    data: list[dict[str, Any]] | None = Field(None, description="Actual data returned from the DB")
    error: str | None
    status: str = Field(..., example="success|failed")
7. EXECUTION DIRECTIVES FOR THE AI AGENT
Acknowledge and Install: Read this context. Update requirements.txt to include sqlalchemy and chromadb.

Build Services First:

Implement services/db_inspector.py to handle SQLAlchemy introspection (get_schema) and execution (execute_read_only_query).

Implement services/vector_store.py to handle ChromaDB logic (saving table chunks with metadata {"db_id": "..."} and semantic search).

Update API: Implement the two-step onboarding endpoints (/api/v1/onboard/extract and /api/v1/onboard/register) and update /api/v1/generate-sql in routes.py.

Upgrade Graph: Update agent/state.py and agent/nodes.py to include the execute_sql_node step and ChromaDB retrieval. Recompile the graph in agent/graph.py.