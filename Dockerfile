# Imagen única del monolito (SPEC-0001 H6). Se construye desde la raíz del repo:
#   docker build -t agentguard .
# Etapa 1: Node construye el frontend. Etapa 2: Python sirve la API y ese build. La imagen final
# no lleva Node, node_modules, pruebas ni .env (lista de permitidos en .dockerignore).

FROM node:24.22.3-slim AS frontend
WORKDIR /srv/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build


FROM python:3.12.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/backend

# Parches de seguridad de Debian que la imagen oficial aún no trae (Trivy en la capa `imagen`).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Misma estructura que el repo: config.py busca frontend/dist relativo al código.
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY --from=frontend /srv/frontend/dist /srv/frontend/dist

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin agentguard
USER 10001

EXPOSE 8000

# /health no consulta la base: una base caída no debe reiniciar el contenedor (SPEC-0001 D-01).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["sh", "-c", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+'${PORT:-8000}'+'/api/v1/health', timeout=4)\""]

# --no-access-log: el log de uvicorn registra la IP; la app tiene el suyo sin IP (RF-08).
CMD ["sh", "-c", "exec uvicorn app.main:crear_app --factory --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
