# Two images from one Dockerfile:
#   ml  - document and evidence workers (PyMuPDF, torch CPU, embedding model)
#   api - API, migrations, dispatcher, discovery worker (small)
# `api` is the LAST stage so hosts that build the default target (Render) get it.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --system --uid 10001 appuser

# ---------------------------------------------------------------- ml workers
FROM base AS ml
# CPU-only torch: the default PyPI wheel for Linux bundles ~2 GB of CUDA libraries.
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements-ml.txt
# Bake the pinned embedding model into the image; workers never download at runtime.
ENV HF_HOME=/opt/models HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
COPY app/retrieval/embeddings.py /tmp/embeddings.py
RUN HF_HUB_OFFLINE=0 python -c "\
import re; src = open('/tmp/embeddings.py').read(); \
name = re.search(r'MODEL_NAME = \"(.+?)\"', src).group(1); \
rev = re.search(r'MODEL_REVISION = \"(.+?)\"', src).group(1); \
from sentence_transformers import SentenceTransformer; \
SentenceTransformer(name, revision=rev, device='cpu')" \
    && rm /tmp/embeddings.py && chmod -R a+rX /opt/models
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
USER appuser
CMD ["python", "-m", "app.workers.documents"]

# ------------------------------------------------------------------- api
FROM base AS api
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY alembic.ini start-with-migrations.sh ./
COPY migrations ./migrations
COPY app ./app
USER appuser
EXPOSE 8000
# PORT is set by hosts such as Render; proxy headers give the real client IP
# (used for per-client rate limiting) when running behind nginx or a platform proxy.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
