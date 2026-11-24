# AgentGuard — Contexto técnico

> Resumen estable del proyecto: arquitectura, reglas de código y forma de trabajo. El estado del
> trabajo en curso vive en `PROGRESS.md`; la estructura del código, en `graphify query`.

## 1. Qué es
_Pendiente: el problema que resuelve AgentGuard y para quién, en dos o tres frases._

## 2. Arquitectura: monolito
- **Un repo, un proceso, una imagen.** El backend FastAPI expone la API en `/api/v1/*` y sirve el
  build estático de React (`frontend/dist`) en el resto de las rutas. Se despliega como una sola
  imagen Docker (`Dockerfile` en la raíz, multi-etapa: Node construye, Python sirve).
- **Módulos por dominio dentro de `backend/app/`**, no por capa técnica. Un módulo no importa el
  interior de otro: se llaman por sus funciones públicas. Así, si algún día hace falta separar un
  servicio, el corte ya está hecho.
- **Una sola base: PostgreSQL.** Migraciones numeradas `NNN_nombre.sql` en `backend/db/postgres/`;
  un archivo ya aplicado no se edita, cada cambio va en uno nuevo.
- `GET /api/v1/health` no consulta la base: una base caída no debe reiniciar el contenedor.

## 3. Estructura
```
backend/
  app/            # FastAPI: main.py (crear_app), core/, un paquete por módulo de dominio
  db/postgres/    # migraciones NNN_nombre.sql
  tests/          # unitarios con dobles; integración marcada `integracion`
  pyproject.toml  # ruff, mypy estricto, bandit
frontend/         # React + Vite; cliente REST único en src/api/
Dockerfile        # imagen única del monolito
docker-compose.yml
```

## 4. Stack
| Capa | Elección |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic |
| Frontend | React + Vite, Node 24 |
| Base de datos | PostgreSQL 16 |
| Empaquetado | Una imagen Docker |
| Calidad | ruff, mypy estricto, bandit, pip-audit, npm audit, Trivy, gitleaks |

## 5. Reglas de código
- **Claves solo en variables de entorno** (`.env`, nunca versionado; plantilla en `.env.example`).
- Tipado estricto: Pydantic en todos los endpoints y mypy `strict`.
- **Seguridad continua:** el CI falla con cualquier vulnerabilidad conocida (`pip-audit` y `bandit`
  en `backend-tests`, `npm audit` en `frontend`, Trivy con arreglo en `imagen`); se arregla en ese
  momento, en un `fix/`. Ignorar una sin arreglo va en `backend/auditoria_ignorar.txt` con su motivo;
  un `# nosec` lleva la regla y el motivo. Las acciones del CI van fijadas por SHA y Dependabot las actualiza.
- Nombres del dominio en español. Ids en `snake_case`.

## 6. Pruebas
- **Unitarias** (`pytest`): la base y cualquier servicio externo se reemplazan por dobles de prueba;
  ningún test unitario llama a un servicio real. Son el criterio de "listo".
- **Integración** (`pytest -m integracion`): SQL contra un Postgres **local** (docker compose o el
  contenedor del CI), con `INTEGRACION_DATABASE_URL`. Se niegan a correr si el host no es
  `127.0.0.1`/`localhost`: vacían la base.
- Un cambio que rompe un test no se integra; si el test está mal, se corrige en el mismo cambio y se explica en el commit.

## 7. Las 5 capas de verificación
Cada PR a `main` pasa por cinco checks, todos obligatorios:

| Check | Qué verifica |
|---|---|
| `backend-tests` | ruff (lint y formato), mypy, pip-audit, bandit y pytest |
| `frontend` | npm audit, pruebas y build |
| `integracion` | pruebas `integracion` contra un Postgres desechable |
| `imagen` | build de la imagen, Trivy, arranque sin base, usuario no root y sin archivos privados |
| `gitleaks` | ningún secreto en todo el historial (respaldo del hook de pre-commit) |

Mientras una parte no exista, su job pasa con un aviso (`::notice::`); se activa sola cuando llega
el archivo que la dispara (`backend/requirements-dev.txt`, `frontend/package-lock.json`, una prueba
marcada `integracion`, el `Dockerfile`).

## 8. Flujo de trabajo
- **Nada se integra directo a `main`:** una rama por funcionalidad o bug, nacida de `main`
  actualizado, y un PR con las 5 capas en verde, revisado por Alex.
- **Protección de `main` (GitHub):** exige PR y las 5 capas en verde. La rama debe estar al día con
  `main`, la regla también aplica a administradores y no hay force push ni borrado. No exige
  aprobaciones, porque GitHub no deja aprobar un PR propio. Se cambia en Settings → Branches.
- Nombres de rama: `feat/<tema>`, `fix/<tema>`, `docs/<tema>`, `chore/<tema>`. Commits en español,
  en imperativo y cortos; cita la spec que corresponda (`SPEC-0001`).
- **Lo compartido se versiona; lo personal, no.** `.claude/settings.json`, las skills, `context.md`
  y `PROGRESS.md` se versionan. Las preferencias personales van en `.claude/settings.local.json` y
  `CLAUDE.local.md` (ignorados por git). Nunca escribas rutas locales, claves ni datos personales en
  archivos versionados.
- Hooks locales, una vez por clon: `pip install pre-commit && pre-commit install` (gitleaks antes de cada commit).

## 9. Flujo con Claude Code
- Estado volátil → `.claude/PROGRESS.md` (skill `project_memory`). Estructura del código → `graphify query`.
- Funcionalidades → `sdd-feature-workflow`; bugs → `sdd-bugfix-workflow`; pedidos vagos → `swe-prompt`; informes → `report-pdf`.
- Specs en `docs/specs/SPEC-NNNN-<tema>.md`.
