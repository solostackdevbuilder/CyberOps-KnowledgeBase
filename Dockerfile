# Frontend build
FROM node:20-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# API + static UI
FROM python:3.11-slim
WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /build/frontend/dist ./static

# Run as a non-root user. Container exploits (e.g. any path that still reaches
# a shell or file write) get UID 1000, not root, which combined with the host
# volume mounts in docker-compose.yml limits what a compromised process can
# overwrite on the host. /app is chowned so the user can write its own data
# directory (mounted volume may be chown'd differently by the host).
RUN useradd --create-home --uid 1000 --shell /bin/bash cyberops \
    && chown -R cyberops:cyberops /app
USER cyberops

ENV SERVE_FRONTEND=1
ENV FRONTEND_DIST=/app/backend/static
ENV DATA_DIR=./data

# Declare the bind host explicitly so the startup guard in
# app/core/startup_guards.py can see it. The guard refuses to run on
# 0.0.0.0 unless CYBEROPS_TRUST_NETWORK=1 is also set, which is the
# operator's signal that an authenticating reverse proxy (YubiKey,
# oauth2-proxy, etc.) is in front. docker-compose.yml or the deployment
# environment is the right place to set CYBEROPS_TRUST_NETWORK=1 after
# the gate is confirmed.
ENV CYBEROPS_BIND_HOST=0.0.0.0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
