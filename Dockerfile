FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS rust-muscles

WORKDIR /tooling
COPY tooling/package.json tooling/package-lock.json ./
RUN npm ci

FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY --chown=appuser:appuser backend backend
COPY --chown=appuser:appuser fixtures fixtures
COPY --from=rust-muscles /usr/local/bin/node /usr/local/bin/node
COPY --from=rust-muscles /tooling/node_modules /app/tooling/node_modules

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/livez', timeout=3)"]
USER appuser
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
