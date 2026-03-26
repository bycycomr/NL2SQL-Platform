# ============================================================
# Gunicorn Configuration – AI Backend
# Production-ready, GPU/CPU workload optimized
# Usage: gunicorn -c gunicorn.conf.py main:app
# ============================================================
import os

# ─── Server Socket ───
bind = "0.0.0.0:8000"
backlog = 2048

# ─── Worker Processes ───
# AI Backend: Daha az worker, her biri daha fazla bellek kullanır (LLM)
# CPU-only: 2 worker yeterli, GPU varsa 1 worker bile yeterli olabilir
workers = int(os.getenv("WORKERS", 2))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 100
threads = 1  # Uvicorn async olduğu için thread gerekmez

# ─── Worker Lifecycle ───
# Memory leak koruması: her worker N request sonra yeniden başlar
max_requests = 1000
max_requests_jitter = 50
timeout = 120          # LLM çağrıları uzun sürebilir
graceful_timeout = 30  # Graceful shutdown süresi
keepalive = 5

# ─── Pre-loading ───
# Modelleri bir kez yükle, tüm worker'lar paylaşsın (cold start opt.)
preload_app = True

# ─── Logging ───
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ─── Process Naming ───
proc_name = "nl2sql-ai-backend"

# ─── Server Hooks ───
def on_starting(server):
    """Server başlangıcında çalışır."""
    server.log.info("NL2SQL AI Backend starting...")

def post_fork(server, worker):
    """Her worker fork sonrası çalışır."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def pre_exec(server):
    """Yeni master process öncesi çalışır."""
    server.log.info("Forked child, re-executing.")

def when_ready(server):
    """Server hazır olduğunda çalışır."""
    server.log.info("Server is ready. Spawning workers.")

def worker_int(worker):
    """Worker SIGINT aldığında çalışır."""
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    """Worker SIGABRT aldığında çalışır."""
    worker.log.info("Worker received SIGABRT signal")
