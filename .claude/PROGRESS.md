# AgentGuard — Bitácora de trabajo

> Estado volátil del proyecto. Arquitectura estable → CLAUDE.md / context.md. Estructura de
> código → `graphify query`. Esta bitácora → en qué vamos y por qué.

## Estado actual
- `chore/fundacion` mergeada (#1, integrada por Alex) — base del repo tomada de CondorForge: skills, hooks, gitleaks, CI con las 5 capas, Dependabot y protección de `main`. — Alex, 2026-11-24
- `docs/que-es-agentguard` mergeada (#2, integrada por Alex) — qué es AgentGuard y sus 5 módulos en `context.md` §1 y el README. — Alex, 2026-11-25
- `feat/esqueleto-monolito` (Alex) — [SPEC-0001](../docs/specs/0001-esqueleto-monolito/spec.md): `crear_app`, health y readiness, errores 503/500 + `id_error`, pool de Postgres, página de estado en React + TypeScript, Dockerfile multi-etapa y compose. Las 5 capas dejan de omitirse. Probado en local: backend-tests, frontend, integración y `docker compose` a mano (página, rutas, 404 de la API y Postgres detenido → `/health` 200 y dependencias 503 en 2 s, log sin IP). Postgres local en el 5433. — Alex, 2026-11-25

## Decisiones
- 2026-11-24 — Monolito: FastAPI sirve la API y el build de React en una sola imagen, con PostgreSQL. Por qué: un solo despliegue y un solo pipeline bastan para el tamaño del proyecto; los módulos por dominio dejan el corte hecho si algún día hay que separar. — Alex
- 2026-11-25 — AgentGuard es un proxy/middleware de seguridad para agentes de IA (SAIF, Tríada Letal), separado de OptiVeil v2, que se queda con infraestructura, redes y postura cloud. Por qué: son dos superficies de ataque distintas. Los controles de Google Cloud se construyen como equivalentes propios. — Alex
- 2026-11-24 — Mismas 5 capas y misma protección de `main` que CondorForge. Por qué: es el flujo ya probado allá. — Alex

## Pendientes
- [ ] SPEC-0002: Detector de la Tríada Letal (`app/triada`).
- [ ] Un módulo por spec, en el orden 1 → 5 (el Detector de la Tríada es análisis puro, sin LLM: el más fácil de probar primero).
- [ ] CD (despliegue automático desde `main`) cuando el flujo de CI esté internalizado.

## Trampas conocidas
- En Windows, `StaticFiles` entrega la ruta con `\`: para saber si una ruta es de la API se mira `scope["path"]`, no el `path` del método (lo detectó `test_spec0001_e10_api_gana_al_frontend`). — Alex, 2026-11-25
- `FRONTEND_DIST=` vacío en el `.env` apunta a la carpeta actual: déjalo comentado si no lo usas.
- El equipo de Alex tiene un PostgreSQL instalado en el 5432: el compose publica Postgres en el **5433** (`POSTGRES_PUERTO`), como CondorForge. — Alex, 2026-11-25
- `docker compose build` falla en Git Bash con «failed to execute bake: exit status 1»; en PowerShell funciona. Desde Git Bash: `docker build -t agentguard-app .` y luego `docker compose up -d --no-build`. — Alex, 2026-11-25
