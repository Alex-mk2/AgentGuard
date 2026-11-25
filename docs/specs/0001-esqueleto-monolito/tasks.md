# SPEC-0001 — Tareas

| # | Tarea | Archivos | Depende de | Historia | Hecha |
|---|---|---|---|---|---|
| T1 | Dependencias y configuración de herramientas | `backend/requirements*.txt`, `backend/pyproject.toml`, `backend/pytest.ini` | — | H1 | ✅ |
| T2 | Settings y `cargar_settings()` sin valores en errores | `app/core/config.py` | T1 | H1 | ✅ |
| T3 | `ServicioNoDisponible` y manejadores 503 / 500 + `id_error` | `app/core/errores.py` | T1 | H3 | ✅ |
| T4 | `Protocol Dependencia` y router de salud | `app/core/salud.py` | T3 | H2 | ✅ |
| T5 | Logging y acceso sin IP; router de versión | `app/core/registro.py`, `app/core/version.py` | T1 | H3, H4 | ✅ |
| T6 | `ConexionPostgres` | `app/base/conexion.py`, `app/base/__init__.py` | T3, T4 | H2 | ✅ |
| T7 | Montaje del frontend con respaldo a `index.html` | `app/core/web.py` | T1 | H4 | ✅ |
| T8 | `crear_app()`: ciclo de vida, CORS, routers, web | `app/main.py` | T2–T7 | H1 | ✅ |
| T9 | Dobles, fixtures y pruebas (unitarias, arquitectura, integración) | `backend/tests/**` | T8 | H1–H5 | ✅ |
| T10 | Frontend TypeScript: página de estado, cliente, lógica y pruebas | `frontend/**` | — | H4 | ✅ |
| T11 | Dockerfile multi-etapa y docker-compose | `Dockerfile`, `docker-compose.yml`, `.dockerignore` | T8, T10 | H1, H6 | ✅ |
| T12 | CI (Postgres 16.16, más comprobaciones de imagen), `.env.example`, `context.md`, `PROGRESS.md` | varios | T11 | H6 | ✅ |

T1–T9 (backend) y T10 (frontend) son independientes y se pueden hacer en paralelo.
