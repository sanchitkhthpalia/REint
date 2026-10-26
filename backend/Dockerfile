# syntax=docker/dockerfile:1
# Backend API image. Build context is the repo root (needs backend/ and data/):
#   docker build -f backend/Dockerfile -t wind-api .

# --- build stage: resolve and install dependencies into a self-contained venv -------------
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Same pinned runtime deps as the Vercel function, plus the ASGI server.
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt "uvicorn[standard]==0.54.0"

# --- runtime stage: venv + code + snapshot, non-root -----------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/app/data \
    CORS_ORIGINS="" \
    LOG_LEVEL=INFO

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=build /opt/venv /opt/venv
COPY --chown=app:app backend/app /app/backend/app
COPY --chown=app:app data /app/data

WORKDIR /app/backend
USER app
EXPOSE 8000

# slim has no curl; use the interpreter that is already there.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

# uvicorn's access log is off: the app writes its own structured access log.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
