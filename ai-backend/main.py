"""
NL2SQL AI Backend — FastAPI uygulama giriş noktası.

Çalıştırmak için:
    uvicorn main:app --reload                  # Geliştirme
    gunicorn -c gunicorn.conf.py main:app      # Prodüksiyon
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.routes import router as nl2sql_router
from core.config import settings


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str

    model_config = {"json_schema_extra": {"example": {"status": "ok", "service": "nl2sql-ai-backend", "version": "2.0.0"}}}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ChromaDB telemetri hatalarını bastır
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------
app = FastAPI(
    title="NL2SQL AI Backend",
    description=(
        "Doğal dil sorularını güvenli SQL'e çeviren ve dry-run ile doğrulayan mikroservis. "
        "LangGraph + Ollama/OpenAI + ChromaDB tabanlı hibrit mimari. "
        "Gerçek veri çekimi Core Backend tarafından yapılır."
    ),
    version="2.0.0",
    contact={"name": "AI Backend Team"},
    license_info={"name": "Private"},
)

# ---------------------------------------------------------------------------
# CORS — Prodüksiyonda ALLOWED_ORIGINS env değişkeniyle kısıtla
# ---------------------------------------------------------------------------
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_allow_origins = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Prometheus Metrics (opsiyonel — bağımlılık yoksa sessizce atla)
# ---------------------------------------------------------------------------
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus instrumentator aktif — /metrics")
except ImportError:
    logger.warning("prometheus_fastapi_instrumentator kurulu değil — /metrics devre dışı")

# ---------------------------------------------------------------------------
# Route'lar
# ---------------------------------------------------------------------------
app.include_router(nl2sql_router)


@app.get("/health", tags=["Ops"], summary="Servis sağlık kontrolü.", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="nl2sql-ai-backend", version="2.0.0")


@app.get("/", tags=["Ops"], include_in_schema=False)
async def root() -> JSONResponse:
    return JSONResponse({"message": "NL2SQL AI Backend çalışıyor. Dokümantasyon: /docs"})
