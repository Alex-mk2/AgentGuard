# AgentGuard

_Pendiente: qué problema resuelve y para quién._

## Arquitectura
Monolito: un backend **FastAPI** (Python 3.12) que expone la API en `/api/v1` y sirve el build de
**React + Vite**, empaquetado en **una sola imagen Docker**, sobre **PostgreSQL 16**. Detalle y
reglas en [.claude/context.md](.claude/context.md).

## Cómo trabajamos
- Nada va directo a `main`: rama `feat/`, `fix/`, `docs/` o `chore/` y un PR.
- `main` está protegida: el PR se integra solo con las **5 capas** en verde (`backend-tests`,
  `frontend`, `integracion`, `imagen`, `gitleaks`) y la rama al día con `main`.
- Antes del primer commit en un clon: `pip install pre-commit && pre-commit install`.
- Variables de entorno: copia `.env.example` a `.env` (nunca se versiona).

## Claude Code
Skills del proyecto en `.claude/skills/`: `sdd-feature-workflow`, `sdd-bugfix-workflow`,
`swe-prompt`, `project_memory`, `report-pdf` y `graphify`. Estado del trabajo en
[.claude/PROGRESS.md](.claude/PROGRESS.md).
