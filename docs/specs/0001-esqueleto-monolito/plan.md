# SPEC-0001 — Plan

> Estado: **aprobado** · Spec: [spec.md](spec.md)

## Contexto técnico
- **Backend:** Python 3.12, `fastapi==0.165.0`, `uvicorn[standard]==0.54.0`, `pydantic==2.14.4`,
  `pydantic-settings==2.16.3`, `asyncpg==0.32.0`. Mismas versiones que CondorForge hoy.
- **Desarrollo:** `pytest==9.2.0`, `pytest-asyncio==1.5.0`, `httpx==0.28.1`, `ruff==0.17.6`,
  `mypy==2.4.1`, `pip-audit==2.10.1`, `bandit==1.9.4`, `pre-commit==4.7.0`.
- **Frontend:** `react`/`react-dom` 19.3.1, `vite` 8.3.8, `@vitejs/plugin-react` 6.3.0,
  `typescript` 7.0.2, `@types/react` 19.3.3, `@types/react-dom` 19.3.0. **Sin librería de pruebas:**
  `node --test` de Node 24 ejecuta `.ts` directo (type stripping), igual que CondorForge con `.js`.
- **Imágenes:** `node:24.22.3-slim` (etapa de build), `python:3.12.16-slim` (final), `postgres:16.16`
  (compose y CI; el CI hoy fija `16.11` y se sube).
- Ya verificado en CondorForge: `asyncpg.create_pool(min_size=0)` no conecta al crearse; la primera
  consulta a un host caído lanza `OSError`/`TimeoutError`.

## Estructura

```
backend/
  app/
    main.py                crear_app(settings, dependencias): fábrica (uvicorn --factory)
    core/
      config.py            Settings + cargar_settings() sin valores en los errores
      errores.py           ServicioNoDisponible + manejadores (422 / 503 / 500 + id_error)
      salud.py             Protocol Dependencia + router /health y /health/dependencias
      registro.py          logging y middleware de acceso sin IP ni query string
      version.py           router /version (lee importlib.metadata / pyproject)
      web.py               montaje de frontend/dist con respaldo a index.html
    base/
      __init__.py          exporta ConexionPostgres
      conexion.py          pool asyncpg: abrir(), verificar(), cerrar() — único que importa asyncpg
  tests/
    conftest.py            settings_prueba, DobleDependencia, cliente, dist_prueba (tmp_path)
    dobles/dependencias.py DobleDependencia (ok / caída / lenta)
    test_spec0001_config.py
    test_spec0001_salud.py
    test_spec0001_errores.py
    test_spec0001_web.py
    test_spec0001_arquitectura.py   asyncpg solo en app/base/
    test_spec0001_integracion.py    pytestmark = integracion; SELECT 1 contra localhost
  pyproject.toml           ruff, mypy strict, bandit (copiado de CondorForge sin lo de su dominio)
  pytest.ini               addopts = -m "not integracion"
  requirements.txt / requirements-dev.txt
frontend/
  index.html, package.json, package-lock.json, tsconfig.json, vite.config.ts
  src/
    main.tsx, App.tsx      página de estado
    api/cliente.ts         único cliente REST (fetch con timeout)
    estado.ts              lógica pura: respuesta de la API → lo que muestra la página
    estado.test.ts         node --test
    modulos.ts             los 5 módulos con su estado «pendiente»
Dockerfile                 multi-etapa: node construye dist, python sirve API + dist
docker-compose.yml         postgres:16.16 + app
```

El paquete de la base se llama `base` y no `db`, para no chocar con la carpeta `backend/db/postgres`
de migraciones.

## Decisiones

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| **Fábrica `crear_app(settings, dependencias)`** con `--factory` | Importar `main` no lee `.env`; los tests inyectan settings y dobles sin parchear nada. Probado en CondorForge. | `app` global + `dependency_overrides`: exige un entorno válido solo para importar. |
| **`Protocol Dependencia`** (`nombre`, `abrir()`, `verificar()`, `cerrar()`) | `core` no conoce `asyncpg` (RF-05). `abrir()` desde el inicio: en CondorForge hubo que agregarlo a mitad de camino porque el pool se crea con `await`. | Que `health` use el pool directo: acopla `core` a la base. |
| **Timeout de 2 s con `asyncio.wait_for` en el router de salud** | Un Postgres lento no cuelga el readiness (caso borde). Pensado para N dependencias con `gather`. | Timeout dentro de cada módulo: fácil de olvidar en el siguiente. |
| **`cargar_settings()` relanza el `ValidationError` sin `input_value`** | El mensaje de pydantic incluye el valor, y `DATABASE_URL` trae la clave (E3). | Confiar en `SecretStr`: no protege un valor mal formado. |
| **`DATABASE_URL: SecretStr` con `min_length=1`** | E4: vacía cuenta como faltante. | — |
| **Manejador de `Exception` → `500` + `id_error` (`secrets.token_hex(8)`)**, log con `logger.exception` | D-02. | — |
| **Log de acceso propio** (método, ruta sin query, código, ms) y uvicorn `--no-access-log` | RF-08: el de uvicorn lleva la IP; la query string puede llevar tokens. | Filtrar el logger de uvicorn: depende de su formato interno. |
| **Frontend servido con una subclase de `StaticFiles`**, montada en `/` **después** de los routers: si el archivo no existe y la ruta no empieza con `api/`, entrega `index.html` | `StaticFiles` ya rechaza rutas fuera del directorio (caso borde de `/../.env`); solo se agrega el respaldo para E13. Una ruta `api/...` inexistente sigue en `404` JSON (E10). | Ruta comodín propia que abre archivos: habría que reimplementar la defensa contra path traversal. |
| **`FRONTEND_DIST` configurable**, por defecto `<repo>/frontend/dist`; si no existe, no se monta | E2: en desarrollo se usa Vite (`npm run dev` con proxy a `:8000`) y la API funciona sola. | Exigir el build siempre: obliga a correr `npm run build` para tocar el backend. |
| **Proxy de Vite a `http://localhost:8000` para `/api`** | En desarrollo el navegador ve un solo origen; CORS solo hace falta si alguien sirve el frontend aparte (RF-07). | CORS siempre activo: superficie que la imagen no necesita. |
| **TypeScript estricto con `erasableSyntaxOnly`** y la lógica de la página en `estado.ts` sin JSX | `node --test` corre `.ts` sin compilar solo si no hay sintaxis que requiera transformación. Lo que tiene JSX se cubre con `tsc --noEmit` y el build. | Vitest + Testing Library: tres dependencias más para una sola página. |
| **`npm test` = `tsc --noEmit && node --test`** | La capa `frontend` revisa tipos y lógica con un solo comando, sin tocar `ci.yml`. | Paso de tipado aparte en el CI. |
| **Dockerfile en la raíz, multi-etapa**, usuario `10001`, `apt-get upgrade` (Trivy), `HEALTHCHECK` a `/api/v1/health` | Patrón ya probado en la capa `imagen` de CondorForge. La etapa final no lleva Node ni `node_modules` (E18). | Dos imágenes (front y API): rompe «una imagen» del monolito. |
| **Prueba de integración en `test_spec0001_integracion.py`** que abre `ConexionPostgres` real y verifica `SELECT 1` | Es lo mínimo que activa la capa `integracion` con algo real; el guardia de host vive en un helper de `conftest.py` que reusan las specs siguientes. | Dejar `integracion` omitida hasta el primer módulo con tablas. |

## Contratos

```python
# core/salud.py
class Dependencia(Protocol):
    nombre: str                          # "postgres"
    async def abrir(self) -> None: ...   # no exige que la base responda
    async def verificar(self) -> None:   # lanza ServicioNoDisponible
        ...
    async def cerrar(self) -> None: ...

# main.py
def crear_app(
    settings: Settings | None = None,                     # None → cargar_settings()
    dependencias: Sequence[Dependencia] | None = None,    # None → [ConexionPostgres(settings)]
) -> FastAPI: ...
```

| Endpoint | Éxito | Error |
|---|---|---|
| `GET /api/v1/health` | `200 {"estado": "ok"}` | — |
| `GET /api/v1/health/dependencias` | `200 {"estado": "ok", "dependencias": {"postgres": "ok"}}` | `503 {"estado": "degradado", "dependencias": {"postgres": "caida"}}` |
| `GET /api/v1/version` | `200 {"version": "0.1.0"}` | — |
| Cualquiera, `ServicioNoDisponible` | — | `503 {"detail": "Servicio no disponible temporalmente"}` |
| Cualquiera, no prevista | — | `500 {"detail": "Error interno", "id_error": "<hex>"}` |
| `/api/...` inexistente | — | `404 {"detail": "Not Found"}` |
| Otra ruta sin archivo (`/modulos/triada`) | `200` con `index.html` | — |

## Cambios fuera de `backend/` y `frontend/`
- `.github/workflows/ci.yml`: Postgres `16.16`; la capa `imagen` también comprueba que no exista
  `node_modules` y que `/` devuelva HTML (E17, E18).
- `.env.example`: `FRONTEND_DIST` y `LOG_LEVEL`.
- `.claude/context.md`: comandos de arranque (§3) y la regla «solo `app/base` importa `asyncpg`».
- `.claude/PROGRESS.md`: entrada de la rama.

## Reglas del proyecto revisadas
- Módulos que no importan el interior de otro: `main` solo usa `base.ConexionPostgres` desde `base/__init__.py`.
- Claves solo en variables de entorno; nunca se imprimen ni se registran.
- Tipado estricto en ambos lados; pruebas unitarias sin red; integración solo contra localhost.
- **Sin excepciones a las reglas.**

## Validación
1. En local: `ruff check`, `ruff format --check`, `mypy`, `pip-audit`, `bandit`, `pytest`; `npm audit`, `npm test`, `npm run build`.
2. `pytest -m integracion` contra el Postgres de `docker compose`.
3. `docker build` + Trivy + arranque con `DATABASE_URL` falsa, como la capa `imagen`.
4. Manual: `docker compose up` → la página en `localhost:8000` muestra API y Postgres en verde;
   `docker compose stop db` → la página muestra Postgres caído y `/api/v1/health` sigue en `200`.
5. En el PR: las 5 capas corren **sin el aviso de omisión** y pasan.

## Riesgos
| Categoría | Riesgo | Mitigación |
|---|---|---|
| Técnico | TypeScript 7 es la reescritura nativa (Go); alguna opción de `tsconfig` podría haber cambiado. | Se valida en local con `tsc --noEmit` antes de abrir el PR; si falla, se fija la última 6.x y se anota. |
| Técnico | El montaje en `/` podría capturar un `405` de la API (método equivocado en una ruta existente). | Prueba explícita de E10 para `POST /api/v1/health`; si lo captura, el respaldo devuelve `405` igual. |
| Seguridad | Servir archivos estáticos abre path traversal. | `StaticFiles` de Starlette lo bloquea; prueba con `/../`, `%2e%2e/` y rutas absolutas. |
| Seguridad | Un error de conexión con la URL de la base termina en el log. | Solo en el log del servidor; `ServicioNoDisponible` solo nombra la dependencia. |
| Mantenibilidad | Los módulos nuevos olvidan traducir los errores de su driver. | Regla en el docstring de `ServicioNoDisponible` y en `context.md`. |
