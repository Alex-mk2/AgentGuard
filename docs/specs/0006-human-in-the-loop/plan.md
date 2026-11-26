# SPEC-0006 — Plan

> Estado: **aprobado** (Alex, 2026-11-26) · Spec: [spec.md](spec.md)

## Contexto técnico
- **Sin dependencias nuevas.** `asyncpg` ya está; el resto es biblioteca estándar (`hashlib`,
  `json`, `secrets`).
- **Primer uso real de PostgreSQL.** Hoy no hay migraciones ni quien las aplique, y la imagen no
  copia `backend/db`. Este plan agrega las dos cosas, sin romper que la app arranque con la base
  caída (SPEC-0001 RF-04).
- **Cambio de comportamiento visible:** con la acción en `si_contaminada` (el valor por defecto), el
  `403` de sesión contaminada (SPEC-0005 E8) pasa a `202` con una solicitud. Con `"aprobacion":
  "nunca"` vuelve el `403` de antes. Con la base caída, `503`. En ningún caso se ejecuta sin
  aprobación.

## Estructura

Dependencias en un solo sentido: `secretos → {egresos, inyeccion, aprobacion}`,
`egresos → {inyeccion, aprobacion}`, `aprobacion → {agentes, base, inyeccion}`. `aprobacion` no
importa `secretos`, `egresos` ni `httpx`, y solo `app/base` importa `asyncpg`. La prueba de
arquitectura de SPEC-0004 se amplía con el módulo nuevo.

```
backend/
  db/postgres/001_aprobaciones.sql   tabla `aprobaciones` (abajo)
  app/base/
    conexion.py              ConexionPostgres gana fetch/fetchrow/execute, que traducen los errores
                             del driver a ServicioNoDisponible (503) igual que `verificar`
    migraciones.py           aplica db/postgres/NNN_*.sql en orden, en una transacción con
                             pg_advisory_xact_lock y la tabla `migraciones`; al arrancar si la base
                             responde y, si no, antes de la primera consulta (una sola vez)
  app/aprobacion/            módulo 5
    __init__.py              exporta Puerta, Pendiente, Motivo, huella, crear_puerta, router
    config.py                APROBACION_CONFIG: vencimientos (15 y 5 min), topes (20 y 1 000),
                             `notificar` (RF-01); sin archivo, valores por defecto
    huella.py                JSON canónico + SHA-256 (RF-04)
    modelos.py               Solicitud, Estado, Motivo; modelos Pydantic de las rutas
    almacen.py               Protocol `Almacen` y AlmacenPostgres (SQL sobre ConexionPostgres)
    puerta.py                Puerta: exigir, decidir, consultar, listar, cancelar_sesion, estado
    rutas.py                 GET /aprobacion/solicitudes · GET /aprobacion/solicitudes/{id} ·
                             POST /aprobacion/solicitudes/{id}/decision · GET /aprobacion/estado
  app/secretos/config.py     Accion.aprobacion; Agente.web_aprobacion (en app/agentes/modelo.py)
  app/secretos/broker.py     exigir aprobación tras validar; ejecutar_interna() para notificar
  app/egresos/salida.py      revisar(peticion, agente): allowlist + DLP sin DNS ni envío; enviar()
                             la llama primero (mismo orden de hoy)
  app/egresos/web.py         exigir aprobación tras revisar
  app/inyeccion/contencion.py  Contenida gana `motivo` y `origen`; observadores de cierre de sesión
  app/main.py                crea la Puerta y la pasa al broker y al egreso web; router nuevo
  Dockerfile                 COPY backend/db ./db
tests/dobles/aprobaciones.py AlmacenMemoria (mismo contrato que AlmacenPostgres, reloj inyectable)
frontend/src/aprobacion.ts (+ .test.ts), src/paginas/Aprobacion.tsx   pantalla /modulos/aprobacion
config/aprobacion.ejemplo.json, config/acciones.ejemplo.json (`aprobacion` y una acción notificar)
```

### Tabla
```sql
CREATE TABLE aprobaciones (
  id             text PRIMARY KEY,            -- secrets.token_urlsafe(24): es el boleto
  agente         text NOT NULL,
  sesion         bytea NOT NULL,              -- SHA-256 del id de sesión (es una capacidad)
  sesion_corta   text NOT NULL,               -- la forma abreviada de SPEC-0005 para mostrar
  destino        text NOT NULL,               -- id de acción, o `web:<host>`
  metodo         text NOT NULL,
  huella         bytea NOT NULL,
  motivo         text NOT NULL,               -- siempre | sesion_contaminada
  origen         text,                        -- origen de la contaminación
  senales        jsonb NOT NULL DEFAULT '{}', -- regla → conteo de la sesión; nunca contenido
  parametros     jsonb,                       -- NULL al decidir o vencer (E14)
  estado         text NOT NULL,               -- pendiente | aprobada | negada | vencida | usada | cancelada
  nota           text,
  decidida_por   text,
  creada         timestamptz NOT NULL,
  vence          timestamptz NOT NULL,        -- para decidir; al aprobar, para usar el boleto
  decidida       timestamptz,
  usada          timestamptz
);
CREATE UNIQUE INDEX aprobaciones_pendiente_unica
  ON aprobaciones (agente, sesion, huella) WHERE estado = 'pendiente';   -- E4
CREATE INDEX aprobaciones_por_estado ON aprobaciones (estado, creada DESC);
```

### La fachada `Puerta`
```python
@dataclass(frozen=True)
class Motivo:            # por qué se pide: "siempre" o "sesion_contaminada" (con su origen)
    tipo: str
    origen: str | None = None

class Pendiente(Exception):   # el broker y el egreso web la traducen a 202 + Retry-After
    solicitud: Solicitud

class Puerta:
    async def exigir(self, agente: Agente, sesion: Sesion, destino: str, metodo: str,
                     huella: bytes, parametros: dict, motivo: Motivo,
                     boleto: str | None) -> None
        # con boleto: lo consume (UPDATE … WHERE estado='aprobada' AND vence > ahora
        #   AND agente, sesion y huella coinciden RETURNING) → vuelve y se ejecuta; si no → 403 (E9)
        # sin boleto: crea la solicitud o devuelve la pendiente idéntica (E4) → Pendiente;
        #   tope por agente y total → 429; dispara la notificación en segundo plano (E13)
    async def decidir(self, id: str, aprobar: bool, nota: str | None) -> Solicitud   # 404 / 409
    async def consultar(self, id: str, agente: Agente) -> Solicitud                  # E10; 404
    async def listar(self) -> list[Solicitud]                                         # E5
    async def cancelar_sesion(self, sesion: str) -> None                              # E11
```
La consumición es un solo `UPDATE … RETURNING`: Postgres serializa la fila y dos reintentos
simultáneos no pueden consumir el mismo boleto. Los vencimientos se aplican al leer (`vence <
ahora` cuenta como vencida) y se persisten con un barrido al listar y al crear, que además pone
`parametros = NULL`.

### Orden en el broker y en el egreso web
1. Token → agente (`401`), sesión (`409`) y acción del agente (`403`), como hoy.
2. **Contención**: fuera de la sesión → `403` como hoy. Si es efecto en una sesión contaminada,
   `Contenida` trae `motivo="sesion_contaminada"`; con `aprobacion: nunca` → `403` como hoy, si no
   se anota el motivo y se sigue. `aprobacion: siempre` anota el motivo `siempre`.
3. Límite por minuto, parámetros (`422`), secreto disponible (`503`), como hoy.
4. **Revisar sin enviar**: `salida.revisar` (allowlist + DLP). Lo bloqueado → `403` como hoy, sin
   solicitud (E3).
5. **Puerta**, solo si hay motivo: sin boleto → `202`; con boleto válido → sigue; si no → `403`.
6. Enviar, limpiar e ingerir, como hoy (`enviar` vuelve a revisar: la defensa no depende del paso 4).

La huella del broker es `{"accion", "metodo", "valores"}` con los valores **ya validados**. La del
egreso web es `{"metodo", "url", "json"}`. El agente y la sesión van aparte, como columnas.

### Notificación (E13)
`APROBACION_CONFIG.notificar` nombra una acción del broker. Al validar la configuración: debe
existir, ser `POST`, tener `"aprobacion": "nunca"` y un parámetro de texto `texto`. Al crear una
solicitud, la puerta llama a la función que le entrega `main` (`broker.ejecutar_interna(accion,
{"texto": ...})`) en una tarea aparte, así que el `202` no la espera. El texto lleva solo ids
validados por patrón: «AgentGuard: el agente soporte-web pide `github.crear_issue` (sesión
contaminada por web). Solicitud 3f9c…». `ejecutar_interna` pasa por la misma salida (allowlist,
DLP) y no por la contención ni la puerta. Un fallo va al log con el código.

### Cancelar al cerrar la sesión (E11)
`Contencion` no puede importar `aprobacion` (ciclo). Gana `al_cerrar(callback)`: `main` registra
`puerta.cancelar_sesion`, que se agenda con `asyncio.create_task` cuando una sesión se cierra o
vence. Aunque la cancelación falle, el boleto de una sesión cerrada no sirve: el reintento resuelve
antes la sesión y responde `409`.

## Decisiones de diseño
- **`ConexionPostgres` con métodos de consulta, no un ORM.** Respeta «solo `app/base` importa
  `asyncpg`» y la traducción a `ServicioNoDisponible` queda en un solo lugar. Son 8 consultas; un
  ORM sería más superficie que código.
- **Migraciones aplicadas por la app con un candado advisory**, no por
  `docker-entrypoint-initdb.d`: eso solo corre con el volumen vacío y nunca aplicaría la `002`. Se
  descartó Alembic: para SQL plano numerado basta un archivo de 40 líneas. Si la base está caída
  al arrancar, la app arranca igual y migra antes de la primera consulta.
- **La sesión se guarda como hash.** Su id es una capacidad del runtime (SPEC-0005); el registro
  no debe permitir reusarla.
- **Revisar antes de pedir (paso 4).** No se le pide a una persona aprobar algo que el DLP igual
  bloquearía, y así la bandeja no sirve para exfiltrar mostrando datos que el DLP habría frenado.
- **El dashboard es el único canal de decisión.** El webhook solo avisa (D-03).

## Riesgos
- **Fatiga de aprobación**: un agente secuestrado puede pedir muchas cosas para que alguien apruebe
  sin mirar. Lo acotan la deduplicación (E4), el tope de 20 pendientes, el motivo y las señales a la
  vista, y el aviso de sesión contaminada (E7).
- **La bandeja muestra datos del agente**: parámetros saneados y truncados, React los escapa, y se
  borran al decidir. El DLP ya pasó (paso 4).
- **Postgres en el camino**: solo de las acciones que piden aprobación. Las demás no lo tocan, y
  `health` sigue sin consultar la base.
- **Romper integraciones**: el runtime que trataba el `403` como final ahora recibe `202`. Se
  documenta en el README con el bucle de reintento; `"aprobacion": "nunca"` restaura lo anterior.

## Desviaciones al implementar
- **La sesión implícita reusa su id** (`implicita:<agente>`) al vencer: la huella de la sesión
  lleva también su hora de creación, para que un boleto de la anterior no sirva en la nueva.
- **`Sesion` guarda sus señales** (regla → conteo) para mostrarlas en la bandeja (E5), y gana
  `corta` (la forma abreviada que ya usaba la auditoría). `app.inyeccion` exporta `sanear`.
- **Timeouts de la base:** el pool conecta con 5 s de timeout (asyncpg espera 60) y la migración
  del arranque se corta a los 5 s. Sin eso, una base que no responde dejaba el arranque y cada
  acción que pide aprobación esperando un minuto (lo mostró el paso «Levantar sin base» del CI).
- **`.dockerignore`** es una lista de permitidos: se agregó `backend/db/postgres/*.sql`.
- **Pruebas de SPEC-0005:** su configuración usa `"aprobacion": "nunca"` y `"web_aprobacion":
  "nunca"`, que conservan el `403` que prueban. El `202` lo cubre `test_spec0006_api.py`.
- **Bandit B608** marca las consultas que interpolan `_COLUMNAS` (una constante del módulo): van
  como constantes con `# nosec B608` y el motivo en la línea de arriba.

## Validación
- **Unitarias** con `AlmacenMemoria` y `MockTransport`: E1 a E15 y los casos borde. Inyección sin
  señales → `202` y **cero** peticiones salientes. Aprobar y reintentar → exactamente una. Cada
  condición de E9, pendiente reintentada, deduplicación, topes, vencimientos con reloj falso, base
  caída → `503`, notificación sin parámetros y que no bloquea, el agente no puede decidir, y
  configuración inválida → `503` en las rutas y `403` en lo que pide aprobación.
- **Cambios intencionales** en `test_spec0005_api.py`: las acciones con efecto en sesión
  contaminada pasan a `202` (o a `403` con `aprobacion: nunca`, para conservar el caso).
- **Integración** (`-m integracion`): migraciones idempotentes, deduplicación por el índice único,
  consumición concurrente (10 tareas, una gana) y barrido de vencidas, contra el Postgres local.
- **Frontend**: lógica de la bandeja en `aprobacion.ts` con `node --test`.
- **Manual** con la imagen endurecida, la base del compose y red real: una sesión contaminada
  por `httpbin.org/base64/…` pide un `POST` → `202`; se aprueba; el
  reintento sale una vez y el segundo reintento con el mismo boleto da `403`. Después se reinicia
  la app y la solicitud sigue en la bandeja.
  **Resultado (2026-11-26): 14/14.** Lectura con inyección → `iny.instruccion` y sesión
  contaminada; `POST` → `202` con `Retry-After: 5`; la bandeja muestra parámetros, motivo y
  señales; el agente no puede aprobar (`401`); reintento sin aprobar, con otro parámetro y segundo
  uso → `403`; con el boleto → `200` y httpbin recibió el título; `POST` web → `202`; `DELETE`
  `siempre` en sesión limpia → `202`; tras reiniciar, la pendiente sigue. En el log: auditoría sin
  parámetros ni tokens. Capa `imagen` en local: health en 2 s sin base, contenido y Trivy en 0.
