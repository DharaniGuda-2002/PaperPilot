#!/bin/sh
# Entry point for single-instance hosts (Render free plan): apply migrations, then serve.
# Not safe with several instances starting at once; see docs/deployment.md.
set -e
alembic upgrade head
# Client addresses come from X-Forwarded-For per TRUSTED_PROXY_HOPS (app code),
# not uvicorn's proxy handling, which would trust the client-supplied entry.
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --no-proxy-headers
