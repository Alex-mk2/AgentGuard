# SPEC-0004 — Plan

> Estado: **aprobado** · Spec: [spec.md](spec.md)

## Contexto técnico
- **Sin dependencias nuevas.** `httpx` ya está; la resolución DNS usa `asyncio` (`getaddrinfo`), la
  verificación de IP usa `ipaddress` y los hosts en Unicode se pasan a punycode con el códec `idna`
  de la biblioteca estándar.
- No toca Postgres: la auditoría sigue en el log (SPEC-0003 D-03) y los contadores de `/estado` viven
  en memoria (un solo proceso, SPEC-0001).
- **Cambio de comportamiento visible (D-01):** desde este PR, sin `EGRESOS_CONFIG` el broker no
  sale. `config/egresos.ejemplo.json` trae los hosts de `acciones.ejemplo.json`.

## Estructura

Tres paquetes con dependencias en un solo sentido: `secretos → egresos → agentes`. `egresos` nunca
importa `secretos`, y `agentes` no importa ningún módulo. Lo verifica una prueba de arquitectura.

```
backend/app/
  agentes/                 compartido (RF-06): lo usan los módulos 2 y 3, y después el 4 y el 5
    __init__.py            exporta Agente, RegistroAgentes
    modelo.py              Agente (id, acciones, max_por_minuto, web), movido de secretos/config.py
    identidad.py           movido de secretos/ sin cambios de lógica (tokens SHA-256, tiempo constante)
    limite.py              movido de secretos/ sin cambios (E14: un solo límite para las dos rutas)
    registro.py            RegistroAgentes: definiciones + Identidades + LimitePorAgente
  egresos/                 módulo 3: el único punto de salida de red (RF-02)
    __init__.py            exporta Salida, PeticionSaliente, RespuestaExterna, Bloqueado, ErrorExterno,
                           limpiar_respuesta, crear_salida, router
    config.py              EGRESOS_CONFIG: allowlist global, modos DLP, marcadores (RF-01)
    hosts.py               normalizar host (minúsculas, sin punto final, punycode, sin IP literal) y
                           calzar contra la allowlist (`*.x.com` solo subdominios) (E1, RF-03)
    red.py                 Protocol Resolutor + ResolutorSistema (getaddrinfo); solo IP públicas (E2)
    dlp.py                 reglas deterministas, decodificación de un nivel y modos (H2)
    limpieza.py            movido de secretos/: variantes de los secretos y allowlist de cabeceras
    salida.py              Salida: allowlist → DLP → DNS → conexión a la IP verificada → tope 1 MB;
                           único archivo que importa httpx (antes secretos/ejecutor.py)
    web.py                 egreso controlado hacia la web (H4)
    rutas.py               POST /egresos/peticion · GET /egresos/estado
  secretos/
    config.py              `secreto` e `inyeccion` opcionales (E9); `web` por agente; descripción de
                           parámetros; nombres MCP únicos
    peticion.py            construir() llena PeticionSaliente.del_agente con los valores del agente
    catalogo.py            herramientas en formato MCP y manifiesto del Detector (E10, E11)
    broker.py              usa Salida; 403 por egresos/DLP; limpia con TODOS los secretos cargados;
                           estado con `bloqueada_por_egresos` (E3)
    rutas.py               + GET /secretos/herramientas
    ejecutor.py, identidad.py, limite.py, limpieza.py   → se mueven (arriba)
  core/config.py           + egresos_config: Path | None
  main.py                  arma registro → salida → broker; registra en la salida las variantes de
                           los secretos para el DLP; incluye router_egresos
config/egresos.ejemplo.json
backend/tests/
  egresos_util.py          ResolutorFalso (host → IP), configuración de egresos para las pruebas
  test_spec0004_{hosts,red,dlp,salida,catalogo,api,sistema}.py
frontend/src/
  egresos.ts + egresos.test.ts, paginas/Egresos.tsx, rutas.ts, modulos.ts (egresos → activo)
  paginas/Secretos.tsx     muestra «bloqueada por egresos»
```

## Contratos

### `EGRESOS_CONFIG` (JSON versionado)
```json
{
  "allowlist": ["api.github.com", "httpbin.org", "*.wikipedia.org", "hooks.empresa.cl:8443"],
  "dlp": {
    "modos": { "dlp.tarjeta": "observar" },
    "marcadores": ["CONFIDENCIAL", "canario-7f3a9c2e"]
  }
}
```
- Entrada de la allowlist: `host` o `*.dominio`, con `:puerto` opcional (si falta, `443`). Sin IP
  literales, sin esquema y sin ruta. Máximo 500.
- `modos`: solo ids de reglas que existen; las que no aparecen, `bloquear` (D-02).
  `dlp.secreto_cargado` **no se puede pasar a `observar`**: que salga una credencial del broker nunca
  es un falso positivo aceptable.
- `marcadores`: literales de 4 a 200 caracteres, máximo 100, sin distinguir mayúsculas.
- Sin archivo → allowlist vacía, todo bloqueado (D-01). Archivo inválido → igual todo bloqueado, el
  error va al log y a `/egresos/estado`, y `POST /egresos/peticion` responde `503`.

### `acciones.json` (cambios compatibles con SPEC-0003)
```json
{ "id": "clima.actual", "metodo": "GET", "url": "https://api.clima.ejemplo/v1/actual",
  "parametros": { "ciudad": { "en": "query", "descripcion": "Ciudad", "max_largo": 80 } } }
```
- `secreto` e `inyeccion` van los dos o ninguno.
- `Parametro.descripcion` (opcional, 300 caracteres): va al `inputSchema`.
- `Agente.web` (opcional): hosts de la allowlist global que ese agente puede pedir por H4. Una entrada
  que la global no cubre se avisa al arrancar; igual nunca saldría, porque la salida revisa la global.

### `PeticionSaliente` (pasa a `app/egresos`)
```python
@dataclass(frozen=True)
class PeticionSaliente:
    metodo: str
    url: str
    cabeceras: dict[str, str] = field(repr=False)
    del_agente: tuple[str, ...] = field(repr=False)  # sin valor por defecto: obliga a decidir qué
    json: dict[str, Valor] | None = None             # revisa el DLP; nunca incluye la credencial
    timeout_s: float = 10
```

### `Salida.enviar(peticion, agente)` — orden fijo
1. **Allowlist** del host normalizado y su puerto → `Bloqueado(403, "Destino no permitido")`.
2. **DLP** sobre `del_agente` → `Bloqueado(403, {"mensaje": "Salida bloqueada por DLP", "reglas": [...]})`
   si alguna regla en `bloquear` encontró algo; las de `observar` solo se auditan.
3. **DNS:** todas las IP deben cumplir `ip.is_global and not ip.is_multicast`; IPv6 que encapsula IPv4
   se revisa como IPv4. Así quedan fuera loopback, privadas, *link-local*, CGNAT y reservadas →
   `Bloqueado(403, "Destino no permitido")`, el mismo mensaje que en el paso 1 para no revelar a qué
   resuelve un host. Con `http_local`, `localhost` se acepta sin este paso.
4. **Conexión a la IP verificada:** la URL se reescribe con la IP, se envía `Host: <host>` y la
   extensión `sni_hostname` de httpx, que también hace que el certificado se valide contra el nombre.
   No hay segunda resolución.
5. Envío como hoy: sin redirecciones, `trust_env=False`, tope de 1 MB sobre lo descomprimido.

Cada bloqueo deja una línea JSON en `agentguard.egresos.auditoria`
(`{"agente", "destino": host, "resultado": "destino"|"dlp"|"ip", "reglas"}`) y suma a su contador.

### DLP (`dlp.py`)
- **Textos revisados:** cada valor de `del_agente`, más una decodificación de un nivel: URL
  (`unquote_plus`), los trozos `[A-Za-z0-9+/_-]{16,}={0,2}` que decodifican como base64 a UTF-8
  imprimible y los `[0-9a-fA-F]{32,}` de largo par como hex (E8). Lo decodificado no se vuelve a
  decodificar.
- **Reglas:** expresiones sin cuantificadores anidados, para que el tiempo sea lineal (RF-04).

| Id | Detecta |
|---|---|
| `dlp.secreto_cargado` | las variantes de SPEC-0003 de los secretos del broker (búsqueda por subcadena) |
| `dlp.credencial` | PEM `-----BEGIN … PRIVATE KEY-----`, AWS `AKIA/ASIA…`, GitHub `gh?_…`/`github_pat_…`, Slack `xox?-…`, Google `AIza…`, Stripe `sk_live_`/`rk_live_`, JWT `eyJ….eyJ….…` |
| `dlp.tarjeta` | 13 a 19 dígitos, con espacios o guiones, que cumplen Luhn |
| `dlp.rut` | `12.345.678-5` o `12345678-5` (exige guion) con dígito verificador módulo 11 |
| `dlp.marcador` | los marcadores de la configuración, sin distinguir mayúsculas |

- El resultado son los **ids** de las reglas, nunca el texto encontrado (E6, RF-05).

### Endpoints
| Endpoint | Token | Respuesta |
|---|---|---|
| `POST /api/v1/secretos/acciones/{accion}` | agente | igual que SPEC-0003; además `403` por destino o DLP |
| `GET /api/v1/secretos/herramientas?formato=mcp\|triada` | agente | `{"tools": [...]}` o un `ManifiestoPropio` |
| `POST /api/v1/egresos/peticion` | agente | `{"estado", "cabeceras", "cuerpo"\|"cuerpo_base64", "limpiado", "origen": "no_confiable"}` |
| `GET /api/v1/egresos/estado` | admin | allowlist, `web` por agente, reglas y modos, cantidad de marcadores (no su texto), contadores, error |

- **Herramienta MCP:** `name` = id con `.` → `__` (las APIs de modelos solo aceptan
  `[a-zA-Z0-9_-]{1,64}`; la unicidad se valida al cargar), `description`, `inputSchema`
  (`string`/`integer`/`boolean`, `pattern`, `maxLength`, `description`, `required`,
  `additionalProperties: false`), `annotations` (`readOnlyHint` e `idempotentHint` en `GET`,
  `destructiveHint` en `PUT` y `DELETE`, `openWorldHint: true`) y `_meta.accion` con el id original.
- **Manifiesto del Detector:** `{"agente", "herramientas": [{"nombre", "descripcion", "parametros",
  "egreso": {"allowlist": [host]}}]}`, que `POST /triada/analisis` acepta tal cual.
- **`POST /egresos/peticion`:** la forma del cuerpo se valida **después** de autenticar (patrón de
  SPEC-0003). `metodo` `GET`|`POST`; `url` `https` de hasta 2000 caracteres, sin usuario ni
  fragmento; `cuerpo` JSON opcional, solo con `POST`. El DLP revisa ruta, query y el cuerpo
  serializado. Un agente sin `web`, o un host fuera de su `web`, → `403`. Solo se envían
  `User-Agent` y `Accept`. La respuesta se limpia con las variantes de los secretos cargados.
- **Precisión sobre E15:** las acciones bloqueadas por egresos salen en `/secretos/estado`, porque
  `egresos` no conoce el broker. La pantalla `/modulos/egresos` lee los dos estados.

## Decisiones de diseño
- **`agentes` como paquete compartido.** La alternativa, que `egresos` importe la identidad desde
  `secretos`, crea un ciclo, porque `secretos` ya usa la salida. Los módulos 4 y 5 van a necesitar
  lo mismo.
- **Los agentes siguen declarados en `acciones.json`.** Un archivo propio de agentes rompería la
  configuración recién publicada en SPEC-0003. Si los módulos 4 y 5 lo piden, se separa ahí.
- **El DLP se aplica en la salida, sobre `del_agente`, y no en cada ruta.** Así ninguna ruta nueva
  puede olvidarlo, y el campo sin valor por defecto obliga a decidir qué se revisa. La credencial
  queda fuera porque la inyecta AgentGuard, no el agente.
- **Fijar la IP en vez de resolver dos veces:** cerrar *DNS rebinding* con una segunda resolución
  sigue dejando la ventana abierta; conectar a la IP verificada la cierra.
- **Sin caché de DNS:** cuesta una resolución por petición. Es aceptable para el volumen de un agente
  y evita razonar sobre TTL.
- **La limpieza de respuestas usa todos los secretos cargados**, no solo el de la acción. Cuesta casi
  nada y cubre las acciones sin credencial y el egreso web.

## Reglas del proyecto
- Sin IA en las decisiones: todo determinista (context.md §2). ✅
- Un módulo no importa el interior de otro: `secretos` usa solo `app.egresos` y `app.agentes`. Lo
  verifica `test_spec0004_dependencias_en_un_sentido`. ✅
- `test_spec0003_httpx_solo_en_el_ejecutor` pasa a apuntar a `app/egresos/salida.py` (cambio
  intencional; el comentario lo explica). `context.md` se actualiza.
- **Pruebas de SPEC-0003 que cambian a propósito:** sus configuraciones suman una allowlist con
  `api.github.com` y `eco.ejemplo`, y un `ResolutorFalso` con IP públicas. Las que miran
  `request.url.host` en la API falsa pasan a mirar la cabecera `Host`, porque ahora la URL lleva la IP.

## Riesgos
| Categoría | Riesgo | Mitigación |
|---|---|---|
| Seguridad | Evasión del DLP cifrando el dato o repartiéndolo en muchas llamadas | Documentado (E8); la garantía son los parámetros acotados y la allowlist |
| Seguridad | Que `sni_hostname` no valide el certificado contra el nombre | Prueba unitaria de que la extensión se envía, y validación manual contra un host real con TLS |
| Técnico | Mover cuatro archivos de `secretos` rompe imports | Se mueven primero y las 213 pruebas de SPEC-0003 deben seguir pasando antes de agregar nada |
| Rendimiento | DLP sobre 1 MB | Expresiones lineales y una sola decodificación; prueba de menos de 100 ms en el CI |
| Mantenibilidad | Falsos positivos de tarjeta o RUT | Modo `observar` (D-02) y contadores en `/estado` |
| Seguridad | Credenciales falsas en las pruebas que dispare gitleaks | Se arman concatenando en tiempo de ejecución |

## Guía de validación
1. `pytest` completo, ruff, mypy, bandit y pip-audit; `npm test` y build. Validador de Mermaid
   sobre el README.
2. Imagen endurecida con `EGRESOS_CONFIG` permitiendo `httpbin.org`:
   - una acción con secreto hacia `httpbin.org/headers` → `200` y limpieza, como en SPEC-0003 (esto
     prueba que el TLS funciona con la IP fijada);
   - una acción cuyo host se quita de la allowlist → `403` y aparece bloqueada en `/secretos/estado`;
   - un parámetro con un número de tarjeta válido → `403` con `dlp.tarjeta`, sin el número en la
     respuesta ni en el log;
   - `POST /egresos/peticion` a `https://httpbin.org/get` → `200` con `origen: no_confiable`; a
     `https://example.com` → `403`;
   - un host en la allowlist que resuelve a una IP privada (`127.0.0.1.nip.io`) → `403`;
   - sin `EGRESOS_CONFIG` → todo `403`.
