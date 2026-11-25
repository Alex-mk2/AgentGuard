# SPEC-0003 — Tareas

| # | Tarea | Archivos | Depende de | Historia | Hecha |
|---|---|---|---|---|---|
| T1 | `httpx` a dependencias de ejecución; settings `secretos_config` y `secretos_http_local` | `backend/requirements*.txt`, `app/core/config.py` | — | — | ✅ |
| T2 | Modelos y validación de `acciones.json` | `app/secretos/config.py` | — | RF-01 | ✅ |
| T3 | `FuenteSecretos` y fuente de entorno (mínimo 8 caracteres, sin saltos de línea, se retiran del entorno) | `app/secretos/fuentes.py` | — | RF-02, RF-08 | ✅ |
| T4 | Tokens de agente y de admin en tiempo constante | `app/secretos/identidad.py` | T2 | H2 | ✅ |
| T5 | Validar parámetros y armar la petición; verificar el destino (anti-SSRF) | `app/secretos/peticion.py` | T2 | H3 | ✅ |
| T6 | Limpieza de respuesta y allowlist de cabeceras | `app/secretos/limpieza.py` | — | E2, RF-05 | ✅ |
| T7 | Ejecutor httpx: sin redirecciones, timeout, tope 1 MB, sin proxy del entorno | `app/secretos/ejecutor.py` | T5 | E8, E10 | ✅ |
| T8 | Límite por agente | `app/secretos/limite.py` | — | E16 | ✅ |
| T9 | `SecretBroker`, estado y auditoría | `app/secretos/broker.py` | T2–T8 | H1, H4, H5, E15 | ✅ |
| T10 | Rutas y registro en `crear_app` | `app/secretos/rutas.py`, `app/secretos/__init__.py`, `app/main.py` | T9 | H1, H2, H4 | ✅ |
| T11 | Endurecimiento del proceso y arranque sin shell | `app/core/endurecer.py`, `app/arranque.py`, `Dockerfile`, `docker-compose.yml`, `ci.yml` | — | E17 | ✅ |
| T12 | Pruebas (una por vía de fuga) | `backend/tests/test_spec0003_*.py` | T10, T11 | todas | ✅ |
| T13 | Frontend: pantalla de estado del broker, módulo activo | `frontend/src/**` | T10 | E13 | ✅ |
| T14 | Ejemplo de configuración, `context.md`, `README`, `PROGRESS.md`, validación manual | `config/acciones.ejemplo.json`, docs | T12, T13 | — | ✅ |

> Ajustes durante la implementación:
> 1. No hay `boveda.py`: la `FuenteSecretos` ya cumple ese papel (mínimo de 8 caracteres, sin saltos
>    de línea) y una capa más no agregaba nada.
> 2. Los secretos **y los tokens** se retiran de `os.environ` al leerlos (no estaba en el plan): ni un
>    subproceso ni un volcado del entorno los ve.
> 3. El token de administración se carga aunque el broker no esté configurado, para que `/estado`
>    siempre lo exija.
> 4. **Bug encontrado por las pruebas:** el ejecutor leía la respuesta cruda (`aiter_raw`), todavía
>    comprimida. Un secreto reflejado dentro de un gzip habría pasado la limpieza. Ahora se
>    descomprime (`aiter_bytes`) y el tope de 1 MB cuenta lo descomprimido (frena una bomba de gzip).
>    Pruebas: `test_spec0003_e2_respuesta_en_gzip_se_limpia` y `test_spec0003_e10_bomba_de_gzip_502`.
> 5. `compose` carga el `.env` en el contenedor (`env_file`, opcional) para pasar secretos y tokens.
