# AgentGuard — Bitácora de trabajo

> Estado volátil del proyecto. Arquitectura estable → CLAUDE.md / context.md. Estructura de
> código → `graphify query`. Esta bitácora → en qué vamos y por qué.

## Estado actual
- `chore/fundacion` mergeada (#1, integrada por Alex) — base del repo tomada de CondorForge: skills, hooks, gitleaks, CI con las 5 capas, Dependabot y protección de `main`. — Alex, 2026-11-24
- `docs/que-es-agentguard` mergeada (#2, integrada por Alex) — qué es AgentGuard y sus 5 módulos en `context.md` §1 y el README. — Alex, 2026-11-25
- `feat/esqueleto-monolito` mergeada (#3, integrada por Alex) — [SPEC-0001](../docs/specs/0001-esqueleto-monolito/spec.md): `crear_app`, health/readiness, errores 503/500 + `id_error`, pool de Postgres, página de estado en React + TypeScript, Dockerfile multi-etapa y compose. Las 5 capas dejaron de omitirse. — Alex, 2026-11-25
- `feat/detector-triada` (Alex) — [SPEC-0002](../docs/specs/0002-detector-triada/spec.md), módulo 1: `POST /api/v1/triada/analisis` (MCP `tools/list` y formato propio), 23 reglas por palabras con evidencia, peor caso para lo sin clasificar, tope global de 1 MB y pantalla `/modulos/triada`. Probado con la imagen: los 6 manifiestos de referencia, 422/413, y servidores MCP reales (filesystem → baja, fetch → media, juntos → crítica). — Alex, 2026-11-25

## Decisiones
- 2026-11-25 — CI y Secretos solo en PR, con `concurrency` que cancela la corrida vieja del mismo PR; igual que CondorForge (#98). Por qué: aviso de 2.700 de 3.000 minutos de Actions usados en la cuenta (cuota compartida con CondorForge y OptiVeil-v2), y ~40 % se iba en repetir el CI tras el merge, cuando `main` exige la rama al día y no admite push directo. Antes de cada push se corren las 5 capas en local. — Alex
- 2026-11-24 — Monolito: FastAPI sirve la API y el build de React en una sola imagen, con PostgreSQL. Por qué: un solo despliegue y un solo pipeline bastan para el tamaño del proyecto; los módulos por dominio dejan el corte hecho si algún día hay que separar. — Alex
- 2026-11-25 — AgentGuard es un proxy/middleware de seguridad para agentes de IA (SAIF, Tríada Letal), separado de OptiVeil v2, que se queda con infraestructura, redes y postura cloud. Por qué: son dos superficies de ataque distintas. Los controles de Google Cloud se construyen como equivalentes propios. — Alex
- 2026-11-24 — Mismas 5 capas y misma protección de `main` que CondorForge. Por qué: es el flujo ya probado allá. — Alex
- 2026-11-25 — La prueba de rendimiento de SPEC-0002 (500 herramientas < 200 ms) solo exige el tiempo en el CI. Por qué: en local con Docker y CondorForge corriendo varió entre 190 y 380 ms en corridas seguidas; una prueba que falla al azar es peor que no tenerla. — Alex

## Pendientes
- [ ] Spec futura: historial de análisis de la Tríada (exige autenticación y retención; SPEC-0002 D-03).
- [ ] Idea futura: modelo local como segunda opinión del Detector, que solo pueda sumar patas (SPEC-0002 D-02).
- [ ] Siguiente módulo: Secret Broker (módulo 2), un módulo por spec en el orden 1 → 5.
- [ ] CD (despliegue automático desde `main`) cuando el flujo de CI esté internalizado.

## Trampas conocidas
- En Windows, `StaticFiles` entrega la ruta con `\`: para saber si una ruta es de la API se mira `scope["path"]`, no el `path` del método (lo detectó `test_spec0001_e10_api_gana_al_frontend`). — Alex, 2026-11-25
- `FRONTEND_DIST=` vacío en el `.env` apunta a la carpeta actual: déjalo comentado si no lo usas.
- Puertos en el equipo de Alex: 5432 = PostgreSQL instalado, 5433 = Postgres de CondorForge, 8000 = uvicorn de CondorForge en desarrollo. AgentGuard publica Postgres en el **5434** (`POSTGRES_PUERTO`) y la app en `APP_PUERTO` (8000 por defecto; usar otro si CondorForge está corriendo). — Alex, 2026-11-25
- `docker compose build` falla en Git Bash con «failed to execute bake: exit status 1»; en PowerShell funciona. Desde Git Bash: `docker build -t agentguard-app .` y luego `docker compose up -d --no-build`. — Alex, 2026-11-25
- Reglas de la Tríada: una palabra exacta siempre calza (`drive_car` → P-NUBE). Es la limitación conocida de las reglas por palabras; se corrige declarando las patas en el formato propio. Al sumar una regla, sumar su caso en `test_spec0002_reglas.py` (una prueba lo exige). — Alex, 2026-11-25
