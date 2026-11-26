# SPEC-0004 — Tareas

| # | Tarea | Archivos | Depende de | Historia | Hecha |
|---|---|---|---|---|---|
| T1 | Mover identidad, límite y `Agente` a `app/agentes`; ejecutor y limpieza a `app/egresos` (sin cambiar lógica; las pruebas de SPEC-0003 siguen pasando) | `app/agentes/*`, `app/egresos/*`, `app/secretos/*` | — | RF-02, RF-06 | ✅ |
| T2 | Configuración de egresos y settings | `app/egresos/config.py`, `app/core/config.py` | T1 | RF-01, D-01 | ✅ |
| T3 | Normalizar hosts y calzar con la allowlist | `app/egresos/hosts.py` | T2 | E1, RF-03 | ✅ |
| T4 | Resolutor y verificación de IP públicas | `app/egresos/red.py` | — | E2 | ✅ |
| T5 | DLP: reglas, decodificación de un nivel, modos | `app/egresos/dlp.py` | T2 | H2 | ✅ |
| T6 | `Salida`: allowlist → DLP → DNS → IP fijada → envío; auditoría y contadores | `app/egresos/salida.py` | T3–T5 | E1–E8 | ✅ |
| T7 | Broker sobre `Salida`: acciones sin secreto, `del_agente`, 403 por egresos/DLP, limpieza con todos los secretos, `bloqueada_por_egresos` | `app/secretos/{config,peticion,broker}.py` | T6 | E3, E9 | ✅ |
| T8 | Catálogo MCP y manifiesto del Detector | `app/secretos/catalogo.py`, `app/secretos/rutas.py` | T7 | E10, E11 | ✅ |
| T9 | Egreso web y estado | `app/egresos/{web,rutas}.py`, `app/main.py` | T6 | H4, E15 | ✅ |
| T10 | Pruebas (una por evasión) y ajuste de las de SPEC-0003 | `backend/tests/test_spec0004_*.py`, `egresos_util.py` | T1–T9 | todas | ✅ |
| T11 | Frontend: pantalla de egresos, bloqueadas en Secretos, módulo activo | `frontend/src/**` | T9 | E16 | ✅ |
| T12 | Ejemplos, `.env.example`, `context.md`, README, `PROGRESS.md`, validación manual | `config/*`, docs | T10, T11 | — | ✅ |

> Ajustes durante la implementación:
> 1. Los tipos de la salida (`PeticionSaliente`, `RespuestaExterna`, `ErrorExterno`, `Bloqueado`) van
>    en `app/egresos/modelos.py`, sin `httpx`, para que `secretos` los use sin conocerlo.
> 2. El parser de `Authorization: Bearer` pasó a `app/agentes` (`token_bearer`): lo usan las rutas de
>    los dos módulos.
> 3. **El DLP tuvo que optimizarse para cumplir los 100 ms:** la primera versión tardaba 825 ms sobre 1 MB de
>    texto. Ahora filtra credenciales por prefijos literales (`in`, en C) antes de la expresión,
>    busca tarjeta y RUT solo dentro de los tramos con dígitos, y hace una sola pasada para base64 y
>    hex: 75 ms. La tarjeta exige formatos reales (contiguo, 4-4-4-x o Amex 4-6-5, con un mismo
>    separador): la expresión genérica retrocedía tanto que 1 MB de dígitos tardaba casi 1 s.
> 4. Con más de 64 KB de texto, el DLP corre en un hilo (`asyncio.to_thread`): un cuerpo patológico
>    (1 MB de RUTs, unos 0,8 s) no frena las demás peticiones.
> 5. Con `SECRETOS_HTTP_LOCAL`, `localhost` se salta la allowlist y el DNS (no el DLP), como en
>    SPEC-0003: es solo para desarrollo y pruebas.
