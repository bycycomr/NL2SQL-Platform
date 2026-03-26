# ============================================================
# NL2SQL AI Backend Dockerfile (LangGraph / LLM)
# Multi-stage, production-ready, security-hardened
# ============================================================

# ----- Stage 1: Builder -----
FROM python:3.11-slim AS builder

WORKDIR /build

# OS-level deps for building wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ----- Stage 2: Runtime -----
FROM python:3.11-slim AS runtime

# Labels
LABEL maintainer="devops@nurolteknoloji.com" \
      description="NL2SQL AI Backend Service" \
      version="2.0.0"

# Security: non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser

WORKDIR /app

# Runtime-only OS deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Remove unnecessary files from image
RUN rm -rf tests/ docs/ .git/ __pycache__/ *.md

# Pre-download / warm-up model artifacts at build time (cold-start opt)
# Uncomment and adapt when model download logic is ready:
# RUN python -c "from app.model_loader import preload_models; preload_models()"

# Ownership
RUN chown -R appuser:appgroup /app

USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Gunicorn + Uvicorn workers (production)
CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
