# AgentGuard — Bitácora de trabajo

> Estado volátil del proyecto. Arquitectura estable → CLAUDE.md / context.md. Estructura de
> código → `graphify query`. Esta bitácora → en qué vamos y por qué.

## Estado actual
- `chore/fundacion` mergeada (#1, integrada por Alex) — base del repo tomada de CondorForge: skills, hooks, gitleaks, CI con las 5 capas, Dependabot y protección de `main`. — Alex, 2026-11-24
- `docs/que-es-agentguard` (Alex) — qué es AgentGuard y sus 5 módulos en `context.md` §1 y el README. — Alex, 2026-11-25

## Decisiones
- 2026-11-24 — Monolito: FastAPI sirve la API y el build de React en una sola imagen, con PostgreSQL. Por qué: un solo despliegue y un solo pipeline bastan para el tamaño del proyecto; los módulos por dominio dejan el corte hecho si algún día hay que separar. — Alex
- 2026-11-25 — AgentGuard es un proxy/middleware de seguridad para agentes de IA (SAIF, Tríada Letal), separado de OptiVeil v2, que se queda con infraestructura, redes y postura cloud. Por qué: son dos superficies de ataque distintas. Los controles de Google Cloud se construyen como equivalentes propios. — Alex
- 2026-11-24 — Mismas 5 capas y misma protección de `main` que CondorForge. Por qué: es el flujo ya probado allá. — Alex

## Pendientes
- [ ] SPEC-0001: esqueleto del monolito (`crear_app`, `/api/v1/health`, frontend Vite, `Dockerfile`, `docker-compose.yml`). Con eso se activan `backend-tests`, `frontend` e `imagen`.
- [ ] Un módulo por spec, en el orden 1 → 5 (el Detector de la Tríada es análisis puro, sin LLM: el más fácil de probar primero).
- [ ] CD (despliegue automático desde `main`) cuando el flujo de CI esté internalizado.

## Trampas conocidas
- Las capas del CI pasan en verde mientras su parte no existe: un check verde al inicio no prueba nada. Revisa el `::notice::` del job.
