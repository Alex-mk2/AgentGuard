# SPEC-0003 — Plan

> Estado: **aprobado** · Spec: [spec.md](spec.md)

## Contexto técnico
- **Única dependencia nueva de ejecución: `httpx==0.28.1`**, que ya está fijada en
  `requirements-dev.txt` por el `TestClient`. Pasa a `requirements.txt`. Es el cliente HTTP async
  estándar con FastAPI, y su `MockTransport` permite probar sin red.
- No toca Postgres (D-03). No hay migraciones ni pruebas de integración nuevas.
- El módulo es **opcional**: sin `SECRETOS_CONFIG`, AgentGuard arranca igual y las rutas del broker
  responden `503 Secret Broker no configurado`. La imagen y el CI no cambian de comportamiento.

## Estructura

```
backend/app/
  core/config.py           + secretos_config: Path | None, secretos_http_local: bool (solo dev)
  secretos/
    __init__.py            exporta router y crear_broker()
    config.py              modelos del JSON (Accion, Parametro, Inyeccion, Agente) y su validación
    fuentes.py             Protocol FuenteSecretos + FuenteEntorno (AGENTGUARD_SECRETO_*) (RF-08)
    boveda.py              Boveda sobre una FuenteSecretos; SecretStr; solo nombres hacia afuera
    identidad.py           tokens de agente y de admin → SHA-256; verificación en tiempo constante
    peticion.py            arma la petición httpx desde la acción y los parámetros; verifica el destino
    limpieza.py            variantes del secreto (claro, base64, base64url, URL) y allowlist de cabeceras
    ejecutor.py            envía con httpx (sin redirecciones, timeout, tope 1 MB) y registra la auditoría
    limite.py              límite por agente, ventana deslizante de 60 s (E16)
    broker.py              SecretBroker: une todo; vive en app.state
    rutas.py               POST /secretos/acciones/{accion} · GET /secretos/estado
  core/endurecer.py        RLIMIT_CORE = 0 y PR_SET_DUMPABLE = 0 al arrancar (Linux) (E17)
  main.py                  + crear_app(..., transporte_saliente=None) para inyectar MockTransport
  arranque.py              punto de entrada sin shell: lee PORT y lanza uvicorn (E17)
Dockerfile                 CMD y HEALTHCHECK en forma exec (sin sh -c)
docker-compose.yml         read_only, tmpfs /tmp, cap_drop ALL, no-new-privileges
.github/workflows/ci.yml   la capa imagen arranca el contenedor con las mismas restricciones
config/
  acciones.ejemplo.json    ejemplo comentado en la doc; el real lo monta cada despliegue
backend/tests/
  test_spec0003_*.py       config, bóveda, identidad, petición (SSRF), limpieza, ejecutor, API
frontend/src/
  paginas/Secretos.tsx     estado del broker (pide el token de admin; no lo guarda)
  secretos.ts + secretos.test.ts
  modulos.ts               secretos → activo
```

## Contratos

### Configuración (`SECRETOS_CONFIG` → archivo JSON, D-02)
```json
{
  "acciones": [
    {
      "id": "github.crear_issue",
      "descripcion": "Crea un issue en un repositorio",
      "metodo": "POST",
      "url": "https://api.github.com/repos/{owner}/{repo}/issues",
      "parametros": {
        "owner": { "tipo": "texto", "en": "ruta", "patron": "^[A-Za-z0-9-]{1,39}$" },
        "repo":  { "tipo": "texto", "en": "ruta", "patron": "^[A-Za-z0-9._-]{1,100}$" },
        "titulo": { "tipo": "texto", "en": "cuerpo", "campo": "title", "max_largo": 256 },
        "cuerpo": { "tipo": "texto", "en": "cuerpo", "campo": "body", "max_largo": 10000, "requerido": false }
      },
      "secreto": "github_token",
      "inyeccion": { "cabecera": "Authorization", "formato": "Bearer {secreto}" },
      "timeout_s": 10
    }
  ],
  "agentes": [
    { "id": "soporte", "acciones": ["github.crear_issue"], "max_por_minuto": 30 }
  ]
}
```
- Secreto `github_token` ← variable `AGENTGUARD_SECRETO_GITHUB_TOKEN`.
- Token del agente `soporte` ← `AGENTGUARD_AGENTE_SOPORTE`. Token de administración ← `AGENTGUARD_ADMIN_TOKEN`.
- Validaciones al cargar: ids únicos; toda acción de un agente existe; la URL tiene esquema y host
  literales (sin huecos en el host); cada hueco `{x}` es un segmento completo de la ruta y tiene su
  parámetro `en: "ruta"`; método en `GET|POST|PUT|PATCH|DELETE`; `timeout_s` ≤ 30; `inyeccion` es
  `cabecera` o `query` (RF-03) y su `formato` contiene `{secreto}` una sola vez.

### Petición del agente
```http
POST /api/v1/secretos/acciones/github.crear_issue
Authorization: Bearer <token del agente>
Content-Type: application/json

{"parametros": {"owner": "acme", "repo": "web", "titulo": "Falla el login"}}
```

### Respuesta
AgentGuard responde **siempre `200` cuando la API externa contestó**, con su código adentro. Así el
agente distingue un error de AgentGuard (`401/403/422/502/503/504`) de uno de la API externa.
```json
{
  "estado": 201,
  "cabeceras": { "content-type": "application/json; charset=utf-8" },
  "cuerpo": { "number": 42, "title": "Falla el login" },
  "limpiado": false
}
```
`cuerpo` es JSON si la respuesta lo es; si no, texto; si es binario, `cuerpo_base64`. `limpiado`
indica si hubo que borrar el secreto (sirve para detectar una API que lo refleja).

| Caso | Respuesta |
|---|---|
| Sin token / token inválido | `401` |
| Acción no asignada al agente (exista o no) | `403` |
| Parámetros inválidos | `422` sin valores |
| Broker sin configurar o secreto no cargado | `503` |
| Agente pasó su límite por minuto | `429` + `Retry-After` |
| API externa no responde / > 1 MB | `502` |
| Timeout de la API externa | `504` |

`GET /api/v1/secretos/estado` (token de admin):
```json
{
  "configurado": true,
  "acciones": [{"id": "github.crear_issue", "secreto": "github_token", "disponible": true}],
  "agentes": [{"id": "soporte", "acciones": ["github.crear_issue"], "token_cargado": true}],
  "secretos": [{"nombre": "github_token", "cargado": true, "compartido": false, "acciones": ["github.crear_issue"]}],
  "avisos": []
}
```

## Decisiones

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| **Respuesta envuelta** (`estado`, `cabeceras`, `cuerpo`) con `200` | El agente distingue errores de AgentGuard de los de la API externa; un `401` externo no se confunde con «tu token de agente es inválido». | Reenviar el código externo tal cual: ambiguo. |
| **Construir la URL y luego verificar** que esquema, host y puerto son los declarados | Defensa en dos capas contra SSRF: aunque un parámetro codificado escape del hueco, la petición no sale si el destino cambió. | Confiar solo en la codificación. |
| **Parámetros de ruta con `quote(valor, safe="")`** | `/`, `?`, `#`, `@`, `..` quedan codificados dentro del segmento. | Interpolación de texto: SSRF directo. |
| **El reemplazo de `{secreto}` ocurre solo en el `formato` de la inyección**, después de validar los parámetros | E9: un parámetro con `{secreto}` es texto y se envía tal cual. | Plantillas sobre toda la petición. |
| **`follow_redirects=False`** | E8: httpx quitaría `Authorization` en un salto entre hosts, pero no una key en la query; no seguir es lo seguro. | Seguir y confiar en httpx. |
| **Leer la respuesta en streaming con tope de 1 MB** | Una API (o un atacante que la controle) no llena la memoria. | `response.read()` completo. |
| **Limpieza por bytes** de cada variante del secreto antes de decodificar | Cubre texto, JSON y binario por igual; las variantes codificadas cubren ecos típicos (Basic auth, query reflejada). | Limpiar solo el JSON ya parseado: se escapa el texto plano. |
| **Allowlist de cabeceras externas** (`content-type`, `content-language`, `retry-after`, `x-ratelimit-*`, `x-request-id`, `etag`, `location` limpia) | Cualquier otra puede traer cookies o datos de sesión; `set-cookie` nunca pasa. | Blocklist: siempre falta una. |
| **Tokens como SHA-256 + `hmac.compare_digest` contra todos los agentes** sin cortar al primero | E4: tiempo constante y no se revela qué agentes existen. Los tokens son aleatorios largos, así que no hace falta un hash lento. | bcrypt: lento por diseño, sin beneficio para tokens aleatorios. |
| **Secretos de menos de 8 caracteres se rechazan al cargar** | Caso borde de la spec: limpiarlos borraría texto legítimo. | Aceptarlos. |
| **Un `httpx.AsyncClient` compartido** creado en el ciclo de vida, con transporte inyectable | Reutiliza conexiones; las pruebas pasan `MockTransport` por `crear_app`. | Un cliente por petición: más lento y difícil de simular. |
| **Configuración inválida → módulo deshabilitado, app arriba** | RF-01: un error en `acciones.json` no tumba los otros módulos; el log dice qué falló y `/estado` lo muestra. | No arrancar: un typo dejaría todo AgentGuard caído. |
| **Auditoría como una línea JSON** en el logger `agentguard.secretos.auditoria` | D-03; fácil de llevar a un SIEM después. Sin parámetros ni cuerpo. | — |
| **`FuenteSecretos` como `Protocol` async** (`obtener(nombre)`, `nombres()`) | RF-08: un gestor externo es async por naturaleza; la fuente de entorno lo cumple trivialmente. Las opciones 4 y 5 se suman sin tocar el broker. | Leer `os.environ` dentro del broker. |
| **Aviso de secreto compartido** en `/estado` (E15), no un error | Compartir un token es una mala práctica, no un fallo: bloquearlo rompería configuraciones válidas. | Rechazar la configuración. |
| **Límite por agente en memoria**, ventana deslizante con `deque` de marcas de tiempo; el `429` se cuenta antes de validar parámetros | Un agente comprometido no puede martillar la API externa ni probar parámetros sin límite. Un solo proceso (SPEC-0001) → sin Redis. | Limitar por IP: el agente se identifica por token, no por IP. |
| **`RLIMIT_CORE = 0` y `prctl(PR_SET_DUMPABLE, 0)` con `ctypes`**, solo en Linux y sin fallar si no se puede | Un volcado de memoria o un `ptrace` del mismo usuario sacaría los secretos en claro; Python no puede borrar un `str` de memoria. | Nada: es la vía de robo más barata tras una intrusión. |
| **Contenedor de solo lectura, sin *capabilities* y con `no-new-privileges`** en compose y en el CI | Tras una intrusión no se puede persistir, instalar herramientas ni escalar. El CI prueba que la app arranca así, para que no se rompa sin aviso. | Solo documentarlo. |
| **Arranque sin shell** (`arranque.py` lee `PORT` y llama a uvicorn; `HEALTHCHECK` con `python -c` en forma exec) | La app deja de necesitar `sh`. **Desviación:** el binario de la shell sigue en la imagen, porque las verificaciones de la capa `imagen` usan `docker exec … test`; quitarlo (base *distroless*) queda para un `chore` propio. | Base *distroless* ahora: obliga a rehacer las verificaciones del CI dentro de esta spec. |
| **Pantalla de estado pide el token de admin y lo guarda solo en memoria del componente** | No queda en `localStorage` (un XSS no lo encuentra al recargar). | Guardarlo para no repetirlo. |

## Reglas del proyecto revisadas
- Módulo por dominio: `secretos` no importa nada de `triada`; `main` solo usa lo exportado.
- Pydantic en los endpoints, mypy `strict`, sin IA (RF-07).
- Claves solo en variables de entorno (D-01 es justamente esa regla llevada a las credenciales de terceros).
- Primera red saliente: toda prueba usa `MockTransport`; una prueba de arquitectura verifica que
  `httpx` solo se importa en `app/secretos/ejecutor.py` (y en pruebas).
- **Sin excepciones a las reglas.**

## Validación
1. `pytest` también para E15 (secreto compartido), E16 (`429` y `Retry-After`, ventana que se
   libera) y E17 (`endurecer` deja `RLIMIT_CORE` en 0 en Linux y no falla en Windows).
2. `pytest` con una prueba por vía de fuga (criterio de éxito): eco en cuerpo, en cabeceras, en
   base64/base64url/URL, en `set-cookie`, en el mensaje de un error de red, en el log (con `caplog`),
   en `repr` de la bóveda y la configuración, redirección a otro host, y SSRF por `../`, `@`, `%2F`,
   `?` y host completo en un parámetro.
3. `npm test`: la lógica de la pantalla de estado.
4. Manual con la imagen: una acción contra `https://httpbin.org/headers`, que **devuelve las
   cabeceras recibidas**, con un secreto falso: la respuesta debe llegar con `[SECRETO]` y
   `limpiado: true`. Además `401`, `403`, `422` y `503` a mano.
   Además, con `docker inspect`: solo lectura, sin *capabilities* y `no-new-privileges`; y
   `/proc/1/status` dentro del contenedor muestra el proceso no *dumpable*.
5. Las 5 capas en verde (el repo es público: no gasta minutos).

## Riesgos
| Categoría | Riesgo | Mitigación |
|---|---|---|
| Seguridad | AgentGuard concentra credenciales: comprometerlo las expone. | En esta spec: tokens de alcance mínimo con aviso de compartidos (E15), límite por agente (E16), sin volcados de memoria, solo lectura y sin *capabilities* (E17), además de memoria sin logs e imagen no root. Riesgo residual aceptado hasta las specs futuras: proceso separado para el broker (opción 6), gestor externo (5) y credenciales de vida corta (4). |
| Técnico | Solo lectura puede romper algo que escribe en disco (cachés de Python, uvicorn). | `PYTHONDONTWRITEBYTECODE=1` ya está; `tmpfs /tmp`; el CI arranca la imagen así en cada PR. |
| Seguridad | Una API devuelve el secreto transformado de una forma no cubierta (hash, recorte). | Las variantes cubren los ecos comunes; `limpiado` y la auditoría ayudan a detectar APIs que reflejan. Queda escrito como limitación. |
| Seguridad | El token del agente es en sí un secreto que el agente debe guardar. | Es un token de alcance mínimo, revocable cambiando la variable; no da acceso directo a ninguna API externa. |
| Técnico | `MockTransport` no reproduce todo (TLS, redirecciones reales). | La validación manual contra httpbin cubre el camino real una vez. |
