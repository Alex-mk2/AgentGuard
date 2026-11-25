# SPEC-0001 — Esqueleto del monolito

> Estado: **aprobada** (decisiones D-01 a D-03) · Autor: Alex · Fecha: 2026-11-25
> Primer código del repo. No implementa ninguno de los 5 módulos: deja la base sobre la que se montan.

## Objetivo
Dejar el monolito andando de punta a punta: configuración tipada, la app FastAPI con su prefijo
`/api/v1`, el contrato de errores, los health checks, el pool de Postgres, la parte web en React
servida por el mismo proceso, la imagen Docker única y el `docker-compose.yml` local. Al terminar,
cada módulo nuevo (`triada`, `secretos`, `egresos`, `inyeccion`, `aprobacion`) solo agrega su paquete,
su router y su doble; y las capas `backend-tests`, `frontend`, `integracion` e `imagen` del CI dejan
de omitirse y prueban algo real.

## Historias de usuario

### H1 (P1) — Integrante levanta AgentGuard en local
Como integrante, quiero levantar todo con un comando, para desarrollar sobre el monolito.

- **E1.** `docker compose up` levanta Postgres y la app; `http://localhost:8000` muestra la página
  de estado y `http://localhost:8000/api/v1/health` responde `200`.
- **E2.** Para desarrollar el backend sin Docker, `uvicorn app.main:crear_app --factory` arranca con
  el `.env`; para el frontend, `npm run dev` (Vite) llama a la API local.
- **E3.** Si falta una variable obligatoria, el arranque falla con un mensaje que **nombra la
  variable** y **no imprime su valor**.
- **E4.** Una variable obligatoria vacía cuenta como faltante.

### H2 (P1) — La plataforma sabe si la instancia sirve
Como plataforma de despliegue, quiero health checks, para saber si la instancia está viva y si
alcanza su base.

- **E5.** `GET /api/v1/health` (liveness) responde `200 {"estado": "ok"}` mientras el proceso viva,
  **aunque Postgres esté caído**. No consulta la base.
- **E6.** `GET /api/v1/health/dependencias` (readiness) responde `200` si Postgres responde y `503`
  si está caído o tarda más de 2 s, indicando cuál, sin host, usuario ni traza.

### H3 (P1) — Cliente de la API recibe errores predecibles
Como frontend (y como agente que habla con el proxy), quiero que todo error tenga un código y un
formato conocidos.

- **E7.** Cuerpo o parámetros inválidos → `422`.
- **E8.** Un módulo informa que Postgres no responde → `503`.
- **E9.** Una excepción no prevista → `500` con un `id_error` (D-02); la traza va al log
  con el mismo `id_error` y **nunca** a la respuesta.
- **E10.** Ruta inexistente bajo `/api/` → `404` en JSON (no la página web). Método no permitido → `405`.

### H4 (P1) — Usuario ve el estado del sistema en la web
Como usuario, quiero una página de estado, para comprobar que AgentGuard está arriba antes de
conectarle un agente.

- **E11.** La página raíz muestra el estado de la API y de Postgres (consumiendo
  `/health/dependencias`) y la lista de los 5 módulos marcados «pendiente».
- **E12.** Si la API no responde, la página lo dice en vez de quedarse cargando.
- **E13.** Una ruta del frontend que no es de la API (p. ej. `/modulos/triada`) entrega la página
  web, para que la navegación de React funcione al recargar.

### H5 (P2) — Integrante escribe tests sin servicios reales
- **E14.** Un fixture entrega un `TestClient` con Postgres reemplazado por un doble.
- **E15.** El doble se puede configurar como «caído» para probar el `503`.
- **E16.** Una prueba de integración marcada `integracion` abre el pool contra el Postgres local y
  ejecuta `SELECT 1`; se niega a correr si el host no es `localhost`/`127.0.0.1`.

### H6 (P1) — La imagen es segura por defecto
- **E17.** Una sola imagen, construida desde la raíz, con la API y el build de React.
- **E18.** Corre con un usuario no root y no contiene `.env`, `backend/tests` ni `node_modules`.
- **E19.** Arranca con una `DATABASE_URL` falsa y su `/api/v1/health` responde (lo comprueba la capa `imagen`).

## Requisitos funcionales
- **RF-01.** Configuración con `pydantic-settings` en un único objeto tipado, desde el entorno y `.env`.
  Los secretos (`DATABASE_URL`) se guardan como `SecretStr`.
- **RF-02.** Única variable obligatoria: `DATABASE_URL`. Opcionales: `FRONTEND_ORIGIN` (CORS en
  desarrollo) y `LOG_LEVEL`.
- **RF-03.** `app/main.py` expone `crear_app()`, que monta los routers bajo `/api/v1` y sirve
  `frontend/dist` en el resto de las rutas, con `index.html` como respaldo (E13). Si `frontend/dist`
  no existe (desarrollo con Vite), la API funciona igual.
- **RF-04.** El ciclo de vida abre el pool de Postgres (`asyncpg`) al arrancar y lo cierra al apagar.
  **Arrancar no exige que Postgres responda** (E5, E19).
- **RF-05.** Excepción de dominio `ServicioNoDisponible` en `app/core`. Solo el módulo de base de
  datos importa `asyncpg`; `main` y `core` no (lo verifica una prueba de arquitectura).
- **RF-06.** Manejadores globales con formato `{"detail": ...}`: `ServicioNoDisponible` → `503`;
  validación → `422`; no prevista → `500` + `id_error` (D-02).
- **RF-07.** CORS solo para `FRONTEND_ORIGIN`; sin ese valor, sin CORS (la imagen sirve todo desde
  el mismo origen).
- **RF-08.** Los logs no registran la IP del cliente ni el valor de ninguna variable secreta.
- **RF-09.** `docker-compose.yml` con `postgres:16` y la app; el Postgres local usa credenciales de
  desarrollo que solo existen en `.env.example`.
- **RF-10.** `GET /api/v1/version` responde la versión de la app (de `pyproject.toml`), que muestra la
  página de estado.

## Casos borde
- `.env` inexistente: se leen solo las variables del entorno (así corre en la imagen).
- Postgres responde pero tarda más de 2 s: cuenta como `caida`.
- Una ruta `/api/v1/...` inexistente nunca devuelve `index.html` (E10).
- Un archivo pedido fuera de `frontend/dist` (`/../.env`, rutas codificadas) → `404`, nunca su contenido.

## Criterios de éxito
- Las 5 capas del CI corren **sin omitirse** y pasan sin credenciales reales.
- Ningún test unitario abre una conexión de red.
- Hay pruebas para E3–E10, E13–E16 y el caso borde de rutas fuera de `dist`; la capa `imagen` cubre E17–E19.
- `docker compose up` en una máquina limpia deja la página de estado en verde.

## Supuestos
- Las pruebas se nombran por escenario: `test_spec0001_e5_health_200_sin_postgres`.
- Autenticación, límite de peticiones y cabeceras de seguridad quedan para la spec que las necesite.
- Aún no hay migraciones ni tablas: el comando de migraciones llega con el primer módulo que guarde datos.

## Decisiones (D-01 a D-03, antes preguntas abiertas; aprobadas por Alex el 2026-11-25)
- **D-01 → liveness y readiness separados**, como en CondorForge: `/health` siempre `200`;
  `/health/dependencias` informa el `503`. La plataforma no reinicia una instancia sana cuando falla la base.
- **D-02 → `500` + `id_error`** ante una excepción no prevista: `{"detail": "Error interno",
  "id_error": "<hex>"}`. **Diverge de CondorForge** (`503`): AgentGuard es un proxy y el agente que lo
  llama debe distinguir «la base cayó» (`503`, reintentable) de «falla de AgentGuard» (`500`).
- **D-03 → frontend en TypeScript**, para cumplir el tipado estricto de `context.md` §5 desde el
  primer archivo (CondorForge quedó en JSX).
