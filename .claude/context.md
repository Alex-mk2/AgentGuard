# AgentGuard — Contexto técnico

> Resumen estable del proyecto: arquitectura, reglas de código y forma de trabajo. El estado del
> trabajo en curso vive en `PROGRESS.md`; la estructura del código, en `graphify query`.

## 1. Qué es
AgentGuard es un **proxy/middleware de seguridad que protege agentes de IA en tiempo de ejecución**,
con enfoque Zero Trust y alineado con el **Secure AI Framework (SAIF)** de Google. Con los agentes,
la superficie de ataque ya no es solo datos, nube, API e infraestructura: también lo es el propio
modelo, que puede ser manipulado por el contenido que lee y usar sus herramientas en contra de quien
lo despliega.

El riesgo central que ataca es la **Tríada Letal**: un agente que a la vez (1) lee **datos privados**,
(2) ingiere **contenido no confiable** (web, correos, documentos) y (3) tiene **salida externa**
(webhooks, APIs) puede ser llevado por una inyección de prompt a exfiltrar esos datos. AgentGuard
rompe la tríada en cada punto en vez de confiar en que el modelo se porte bien.

**Fuera de alcance:** la postura de infraestructura cloud, redes y SDLC. Eso es de OptiVeil v2, un
proyecto separado; no se mezclan.

### Los 5 módulos
| # | Módulo | Paquete | Qué hace |
|---|---|---|---|
| 1 | Detector de la Tríada Letal ✅ | `app/triada` | Analiza el manifiesto de herramientas de un agente y alerta como crítico si combina datos privados + contenido no confiable + salida de red sin control de egresos. `POST /api/v1/triada/analisis`, pantalla `/modulos/triada` (SPEC-0002). |
| 2 | Secret Broker ✅ | `app/secretos` | El LLM pide ejecutar una acción y el intermediario inyecta la API key o el token desde un vault en memoria al ejecutarla. **El secreto nunca entra en la ventana de contexto del modelo.** `POST /api/v1/secretos/acciones/{accion}`, `GET /api/v1/secretos/estado`, pantalla `/modulos/secretos` (SPEC-0003). |
| 3 | Sealed Tools y control de egresos (DLP) ✅ | `app/egresos` | Única salida de red: allowlist global, DLP determinista y solo IP públicas (conexión a la IP verificada). Herramientas selladas sin credencial y catálogo MCP del agente (`GET /api/v1/secretos/herramientas`); egreso web `POST /api/v1/egresos/peticion`; `GET /api/v1/egresos/estado`, pantalla `/modulos/egresos` (SPEC-0004). |
| 4 | Contención de prompt injection y rogue actions ✅ | `app/inyeccion` | Una sesión que ingirió contenido no confiable (web, respuesta de una acción, memoria, otro agente) queda contaminada y pierde las acciones con efecto, se detecte o no la inyección. Inspección determinista (invisibles, frases, rol, herramienta, HTML oculto) y envoltorio. Sesiones por `X-AgentGuard-Sesion`; `POST /api/v1/inyeccion/sesiones`, `/inspeccion`, `GET /estado`, pantalla `/modulos/inyeccion` (SPEC-0005). El sandbox de ejecución de código va en una spec propia (D-03). |
| 5 | Human-in-the-Loop Gate ✅ | `app/aprobacion` | Pausa toda acción `aprobacion: siempre` (irreversible o del plano de control del destino) y toda acción con efecto de una sesión contaminada (`si_contaminada`, por defecto): `202` con una solicitud, decisión en el dashboard y reintento con `X-AgentGuard-Aprobacion`. El boleto vale una vez y solo para esa huella; si nadie decide, vence y se niega. Aviso opcional por webhook (una acción del broker, sin parámetros). `GET/POST /api/v1/aprobacion/solicitudes…`, `GET /estado`, pantalla `/modulos/aprobacion` (SPEC-0006). |

Origen: evento de Deloitte y charlas de Google Cloud sobre Securing AI (2026-11). La lámina «Cómo
podemos proteger la AI» divide la defensa en aplicación, datos, modelo e infraestructura;
AgentGuard construye equivalentes propios de los controles de aplicación, datos y modelo en vez de
usar los productos de Google Cloud.

## 2. Arquitectura: monolito
- **Un repo, un proceso, una imagen.** El backend FastAPI expone la API en `/api/v1/*` y sirve el
  build estático de React (`frontend/dist`) en el resto de las rutas. Se despliega como una sola
  imagen Docker (`Dockerfile` en la raíz, multi-etapa: Node construye, Python sirve).
- **Módulos por dominio dentro de `backend/app/`**, no por capa técnica. Un módulo no importa el
  interior de otro: se llaman por sus funciones públicas. Así, si algún día hace falta separar un
  servicio, el corte ya está hecho.
- **Una sola base: PostgreSQL.** Migraciones numeradas `NNN_nombre.sql` en `backend/db/postgres/`;
  un archivo ya aplicado no se edita, cada cambio va en uno nuevo. Las aplica la app
  (`app/base/migraciones.py`, con candado advisory) al arrancar o, si la base estaba caída, antes de
  la primera consulta. Los módulos consultan con `ConexionPostgres.fetch/fetchrow/execute`.
- `GET /api/v1/health` no consulta la base: una base caída no debe reiniciar el contenedor.
  `GET /api/v1/health/dependencias` sí, con 2 s de timeout (SPEC-0001 D-01).
- **Solo `app/base` importa `asyncpg`.** Todo módulo que use un driver traduce sus errores de
  conexión a `ServicioNoDisponible` (`503`); `core` y `main` no conocen drivers. Lo verifica
  `test_spec0001_arquitectura.py`.
- **Errores:** `{"detail": ...}`; base caída → `503` (reintentable); bug → `500` con `id_error`, traza
  solo en el log (SPEC-0001 D-02). El log de acceso no registra IP ni query string.
- Cada módulo agrega su router en `crear_app()` bajo `/api/v1`, **antes** del montaje del frontend,
  y exporta desde su `__init__.py` solo lo público (`app/triada` es el patrón).
- **Tope global de 1 MB por petición** (`core/tope.py`, `413`). Lo que viene de un agente o de un
  manifiesto es entrada hostil: límites de cantidad y profundidad en los modelos, y los errores
  `422` nunca reflejan el valor recibido (`include_input=False`).
- **Red saliente solo en `app/egresos/salida.py`** (único que importa `httpx`; lo verifica
  `test_spec0003_httpx_solo_en_el_ejecutor`). Orden fijo: allowlist → DLP sobre
  `PeticionSaliente.del_agente` → DNS con todas las IP públicas → conexión a la IP verificada
  (`sni_hostname`) → sin redirecciones, sin proxies del entorno, tope de 1 MB descomprimido. **Sin
  `EGRESOS_CONFIG` no sale nada** (SPEC-0004 D-01). Las pruebas simulan las APIs con `MockTransport`
  y el DNS con `ResolutorFalso` (`tests/egresos_util.py`).
- **Dependencias en un solo sentido:** `secretos → {egresos, inyeccion, aprobacion}`,
  `egresos → {inyeccion, aprobacion}`, `aprobacion → {agentes, base, inyeccion}`,
  `inyeccion → agentes`; `app/agentes` (identidad, tokens, límite por minuto) no importa ningún
  módulo. `inyeccion` avisa a `aprobacion` por un callback (`Contencion.al_cerrar`). Desde otro módulo se importa solo `app.<modulo>`, nunca su interior
  (`test_spec0004_sistema.py`).
- **Contención (SPEC-0005):** el broker y el egreso web llaman a `Contencion` en orden fijo:
  sesión (`409` si es desconocida, falla cerrado) → autorizar (antes del límite y del envío) →
  enviar → ingerir la respuesta (contamina por origen e inspecciona).
- **Aprobación (SPEC-0006):** si la acción la pide, tras validar todo: `salida.revisar` (allowlist +
  DLP sin enviar) → `Puerta.exigir` (sin boleto `202`, boleto válido sigue, si no `403`) → enviar.
  Sin almacén, con base caída o `APROBACION_CONFIG` inválido, nunca se ejecuta (`403`/`503`). Sin `INYECCION_CONFIG`
  valen los valores por defecto: la contención no depende de que alguien la active.
- **Secretos de terceros** (SPEC-0003): solo por variables de entorno, se retiran de `os.environ` al
  leerlos y nunca aparecen en logs, errores, `repr` ni respuestas. La imagen arranca con
  `python -m app.arranque` (sin shell), que desactiva *core dumps* y deja el proceso no *dumpable*;
  se corre con `--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges`.
- **Sin IA en las decisiones de seguridad** mientras puedan ser deterministas: un clasificador con
  LLM es atacable con la misma inyección que se busca detectar (SPEC-0002 D-02). Un modelo local
  podría sumar señales, nunca quitarlas.

## 3. Estructura y comandos
```
backend/
  app/            # main.py (crear_app), core/ (config, errores, salud, registro, web), base/ (Postgres)
                  # y un paquete por módulo de dominio
  db/postgres/    # migraciones NNN_nombre.sql
  tests/          # unitarios con dobles; integración marcada `integracion`
  pyproject.toml  # ruff, mypy estricto, bandit
frontend/         # React + Vite + TypeScript; cliente REST único en src/api/cliente.ts
Dockerfile        # imagen única del monolito
docker-compose.yml
```

| Para | Comando |
|---|---|
| Todo en local | `docker compose up --build` → http://localhost:8000 (`APP_PUERTO` si el 8000 está ocupado; Postgres en el 5434) |
| Backend en desarrollo | en `backend/`: `uvicorn app.main:crear_app --factory --reload --no-access-log` |
| Frontend en desarrollo | en `frontend/`: `npm run dev` (Vite reenvía `/api` a `localhost:8000`) |
| Pruebas | `pytest` · `pytest -m integracion` (con `docker compose up db`) · `npm test` |

Las pruebas del frontend van en `src/**/*.test.ts` sin JSX: `node --test` las ejecuta sin compilar.
La lógica se separa de los componentes para poder probarla así.

## 4. Stack
| Capa | Elección |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic |
| Frontend | React + Vite + TypeScript estricto, Node 24 |
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
Cada PR a `main` pasa por cinco checks, todos obligatorios. Corren **solo en PR** (no tras el merge) y
un commit nuevo cancela la corrida anterior del mismo PR: los minutos de Actions son limitados.

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
