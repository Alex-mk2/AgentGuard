# AgentGuard — Bitácora de trabajo

> Estado volátil del proyecto. Arquitectura estable → CLAUDE.md / context.md. Estructura de
> código → `graphify query`. Esta bitácora → en qué vamos y por qué.

## Estado actual
- `chore/fundacion` (Alex) — base del repo tomada de CondorForge: skills, hooks de Claude Code, gitleaks en pre-commit, CI con las 5 capas (cada una se omite con aviso hasta que exista su parte), Dependabot y protección de `main`. — Alex, 2026-11-24

## Decisiones
- 2026-11-24 — Monolito: FastAPI sirve la API y el build de React en una sola imagen, con PostgreSQL. Por qué: un solo despliegue y un solo pipeline bastan para el tamaño del proyecto; los módulos por dominio dejan el corte hecho si algún día hay que separar. — Alex
- 2026-11-24 — Mismas 5 capas y misma protección de `main` que CondorForge. Por qué: es el flujo ya probado allá. — Alex

## Pendientes
- [ ] Describir qué es AgentGuard en `context.md` §1 y en el README.
- [ ] SPEC-0001: esqueleto del monolito (`crear_app`, `/api/v1/health`, frontend Vite, `Dockerfile`, `docker-compose.yml`). Con eso se activan `backend-tests`, `frontend` e `imagen`.
- [ ] CD (despliegue automático desde `main`) cuando el flujo de CI esté internalizado.

## Trampas conocidas
- Las capas del CI pasan en verde mientras su parte no existe: un check verde al inicio no prueba nada. Revisa el `::notice::` del job.
