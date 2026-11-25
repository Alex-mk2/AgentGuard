# SPEC-0002 — Tareas

| # | Tarea | Archivos | Depende de | Historia | Hecha |
|---|---|---|---|---|---|
| T1 | Tope global de 1 MB (413) | `app/core/tope.py`, `app/main.py` | — | RF-06 | ✅ |
| T2 | Modelos de entrada, herramienta normalizada y reporte | `app/triada/modelos.py` | — | H1–H3 | ✅ |
| T3 | Tokenizador (tildes, camelCase, snake, kebab) | `app/triada/texto.py` | — | H3 | ✅ |
| T4 | Normalizadores MCP (con y sin JSON-RPC) y propio; parámetros con profundidad 5 y tope 200 | `app/triada/normalizar.py` | T2 | H3 | ✅ |
| T5 | Reglas como datos | `app/triada/reglas.py` | T3 | H1 | ✅ |
| T6 | Clasificación declarado > anotaciones > reglas, con evidencia | `app/triada/clasificar.py` | T4, T5 | H2, H4 | ✅ |
| T7 | Severidad, peor caso, faltantes y recomendaciones | `app/triada/analisis.py` | T6 | H1, H2, H4 | ✅ |
| T8 | Ruta `POST /triada/analisis` y registro en `crear_app` | `app/triada/rutas.py`, `app/triada/__init__.py`, `app/main.py` | T1, T7 | H1 | ✅ |
| T9 | Manifiestos de referencia y pruebas | `tests/datos/triada/*.json`, `tests/test_spec0002_*.py` | T8 | H1–H4 | ✅ |
| T10 | Frontend: enrutado, página de la tríada, lógica y pruebas, módulo activo | `frontend/src/**` | T8 | H5 | ✅ |
| T11 | `context.md`, `PROGRESS.md`, validación manual con compose | varios | T9, T10 | — | ✅ |

> Ajustes durante la implementación: (1) el criterio de rendimiento solo se exige con `CI` definido,
> porque en local varía demasiado con la carga (ver PROGRESS.md); (2) el tokenizador usa un caché
> acotado solo para textos cortos (nombres y parámetros), para no abrir un consumo de memoria
> controlado por el atacante; (3) los puertos del compose son configurables (`POSTGRES_PUERTO` 5434,
> `APP_PUERTO`) para convivir con CondorForge; (4) la validación con servidores MCP reales sumó los
> plurales `directories`/`folders` a P-ARCHIVO.

T2/T3 y T1 son independientes. T10 puede empezar en cuanto el contrato (T2) está fijo.
