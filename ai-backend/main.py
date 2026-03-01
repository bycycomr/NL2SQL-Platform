"""
FastAPI application entry-point for the NL2SQL AI Backend.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as nl2sql_router
from core.config import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="NL2SQL AI Backend",
    description="Natural Language to SQL translation microservice powered by LangGraph and Llama 3.1.",
    version="0.1.0",
)

# CORS – restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(nl2sql_router)


@app.get("/health", tags=["Ops"])
async def health_check():
    return {"status": "ok"}
