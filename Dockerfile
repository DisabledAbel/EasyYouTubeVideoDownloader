FROM --platform=$BUILDPLATFORM rust:1.99.1-bookworm AS frontend
WORKDIR /app
COPY rust-toolchain.toml ./
RUN rustup target add wasm32-unknown-unknown && cargo install trunk --locked --version 0.21.14
COPY frontend ./frontend
COPY scripts/build-frontend.sh ./scripts/build-frontend.sh
ENV NO_COLOR=true
RUN bash scripts/build-frontend.sh

FROM node:24-bookworm-slim AS javascript

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ARCHIVE_DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 archiver && mkdir /data && chown archiver:archiver /data
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY --from=frontend /app/frontend/dist ./frontend/dist
USER archiver
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["python", "-m", "uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
