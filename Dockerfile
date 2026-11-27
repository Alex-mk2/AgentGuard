# Imagen única del monolito (SPEC-0001 H6). Se construye desde la raíz del repo:
#   docker build -t agentguard .
# Etapa 1: Node construye el frontend. Etapa 2: Debian arma el entorno de Python. Etapa 3: una base
# distroless sirve la API y ese build. La imagen final no lleva shell, gestor de paquetes, Node,
# node_modules, pruebas ni .env (lista de permitidos en .dockerignore).

FROM node:24.22.3-slim AS frontend
WORKDIR /srv/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build


# Mismo Debian y mismo paquete python3.13 que la base distroless: el venv apunta a /usr/bin/python3
# y las extensiones compiladas quedan con la ABI exacta del intérprete final.
FROM debian:13.7-slim AS python
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/
RUN python3 -m venv /srv/venv \
    && /srv/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && /srv/venv/bin/pip uninstall -y pip


# Distroless (Debian 13, Python 3.13): sin shell ni apt. Fijada por digest; Dependabot la actualiza.
# Sus paquetes están registrados, así que Trivy los ve (la capa `imagen`).
FROM gcr.io/distroless/python3-debian13:nonroot@sha256:72de1dda9d4c52c370e2ef2d93c28e3e1a8193c92058b7dfa42bace38a83d114

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/srv/venv/bin:/usr/bin:/bin

WORKDIR /srv/backend

COPY --from=python /srv/venv /srv/venv

# Misma estructura que el repo: config.py busca frontend/dist relativo al código.
COPY backend/pyproject.toml ./
COPY backend/app ./app
# Migraciones NNN_nombre.sql: la app las aplica al arrancar o antes de la primera consulta (SPEC-0006).
COPY backend/db ./db
COPY --from=frontend /srv/frontend/dist /srv/frontend/dist

# Usuario nonroot de distroless (65532), sin shell de login.
USER 65532

EXPOSE 8000

# /health no consulta la base: una base caída no debe reiniciar el contenedor (SPEC-0001 D-01).
# Forma exec, sin shell (SPEC-0003 E17): Python lee PORT por su cuenta.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/v1/health', timeout=4)"]

# app.arranque endurece el proceso (sin core dumps, no dumpable) y lanza uvicorn sin su log de
# acceso, que registra la IP (RF-08). Correr con --read-only --tmpfs /tmp --cap-drop ALL
# --security-opt no-new-privileges, como en docker-compose.yml y en la capa `imagen` del CI.
# La base trae ENTRYPOINT python3.13; se vacía para que el comando sea solo este.
ENTRYPOINT []
CMD ["python", "-m", "app.arranque"]
