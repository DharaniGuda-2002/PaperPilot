FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini start-with-migrations.sh ./
COPY migrations ./migrations
COPY app ./app

# Run as an unprivileged user.
RUN useradd --system --uid 10001 appuser
USER appuser

EXPOSE 8000
# PORT is set by hosts such as Render; proxy headers give the real client IP
# (used for per-client rate limiting) when running behind nginx or a platform proxy.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
