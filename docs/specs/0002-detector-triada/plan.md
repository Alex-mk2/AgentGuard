# SPEC-0002 — Plan

> Estado: **aprobado** · Spec: [spec.md](spec.md)

## Contexto técnico
- Solo backend Python y frontend TypeScript ya existentes. **No se agregan dependencias** en ninguno
  de los dos: la normalización de texto usa `unicodedata` y `re` de la biblioteca estándar; el
  frontend no suma router (dos páginas se resuelven por `location.pathname`).
- No toca Postgres (D-03): no hay migraciones ni pruebas de integración nuevas.
- Primer módulo de dominio: deja el patrón que siguen los otros cuatro (paquete propio, router
  propio, solo exporta lo público desde `__init__.py`).

## Estructura

```
backend/app/
  core/tope.py              NUEVO · middleware: rechaza cuerpos > 1 MB con 413 (RF-06), global
  triada/
    __init__.py             exporta router y analizar()
    modelos.py              entrada (ManifiestoMcp, ManifiestoPropio), Herramienta normalizada, Reporte
    normalizar.py           detecta el formato (RF-02) y lo lleva a list[Herramienta]
    texto.py                tokens: minúsculas, sin tildes, separa camelCase/snake/kebab
    reglas.py               DATOS: tupla de Regla(id, pata, campos, palabras) en español e inglés (RF-04)
    clasificar.py           declarado > anotaciones > reglas, con Evidencia (RF-03, RF-07)
    analisis.py             severidad, peor caso, patas faltantes, recomendaciones (RF-05, RF-08)
    rutas.py                POST /triada/analisis
  main.py                   + include_router(triada.router) y RegistroAcceso/Tope
backend/tests/
  datos/triada/*.json       manifiestos de referencia (criterio de éxito)
  test_spec0002_*.py
frontend/src/
  App.tsx                   enruta / y /modulos/triada por pathname
  paginas/Estado.tsx        lo que hoy es App (página de estado)
  paginas/Triada.tsx        pegar / cargar JSON, botón «Ejemplo», reporte
  triada.ts                 lógica pura: validar el JSON local, traducir errores 413/422, etiquetas
  triada.test.ts
  ejemplos/triada.ts        manifiesto de ejemplo (agente de correo con la tríada completa)
  api/cliente.ts            + enviar(ruta, cuerpo) (POST) con el mismo contrato de Respuesta
  modulos.ts                triada → «activo», con su ruta
```

## Contratos

### Entrada — formato propio (D-01)
```json
{
  "agente": "asistente-correo",
  "herramientas": [
    {
      "nombre": "leer_bandeja",
      "descripcion": "Lee los correos entrantes",
      "parametros": ["carpeta"],
      "patas": ["no_confiable", "datos_privados"],
      "egreso": null
    },
    {
      "nombre": "notificar",
      "descripcion": "POST a un webhook",
      "parametros": ["url", "mensaje"],
      "patas": ["salida_externa"],
      "egreso": { "allowlist": ["hooks.empresa.cl"] }
    }
  ]
}
```
- `patas` omitido o `null` → se infiere; `[]` → declarada inofensiva (caso borde de la spec).
- `egreso.allowlist` presente (aunque vacía) → su salida cuenta como **restringida**.

### Entrada — MCP `tools/list`
`{"tools": [{"name", "description"?, "inputSchema"?, "annotations"?}, ...]}` y también la respuesta
JSON-RPC completa (`{"jsonrpc", "id", "result": {"tools": [...]}}`), porque es lo que se copia al
depurar un servidor. Campos extra se ignoran. Las herramientas MCP nunca tienen salida restringida
(MCP no lo puede declarar).

### Salida
```json
{
  "formato": "mcp",
  "severidad": "critica",
  "incompleto": true,
  "severidad_peor_caso": "critica",
  "faltan": [],
  "patas": {
    "datos_privados": [{"herramienta": "query_db", "origen": "regla", "regla": "P-BD", "fragmento": "sql"}],
    "no_confiable":   [...],
    "salida_externa": [...]
  },
  "herramientas": [
    {"nombre": "fetch_url", "patas": ["no_confiable", "salida_externa"], "clasificacion": "inferida",
     "egreso_restringido": false, "multipata": true}
  ],
  "recomendaciones": [{"id": "R-CORTAR-E", "texto": "..."}]
}
```
`clasificacion`: `declarada` | `inferida` | `sin_clasificar`. `severidad_peor_caso` es `null` si
`incompleto` es `false`.

| Caso | Respuesta |
|---|---|
| Manifiesto válido | `200` con el reporte |
| JSON con forma desconocida, nombres repetidos, > 500 herramientas | `422` `{"detail": ...}` |
| Cuerpo > 1 MB | `413` `{"detail": "La petición supera el máximo de 1 MB"}` |

## Decisiones

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| **Reglas por token completo**, no por subcadena: el texto se parte en palabras (`sendEmail` → `send`, `email`; `enviar_correo` → `enviar`, `correo`) sin tildes ni mayúsculas | Evita falsos positivos como `readme` → `read` o `urlencode` → `url`. Determinista y fácil de explicar en la evidencia. | Regex por subcadena: más alcance, muchos falsos positivos. |
| **Reglas como datos** en `reglas.py` (tupla de `Regla` inmutables con `id`, `pata`, `campos`, `palabras`) | RF-04: sumar una regla es agregar una línea con su prueba. Python y no JSON: mypy revisa la forma y no hay que cargar archivos en la imagen. | JSON: sin tipado y otra ruta que copiar al `Dockerfile`. |
| **Campos que mira cada regla**: `nombre`, `descripcion`, `parametro` | Una regla de E por parámetro `url` es fuerte; la palabra «url» suelta en una descripción es débil. Cada regla elige dónde aplica. | Mismo peso en todo el texto: más ruido. |
| **`parametros` de MCP**: nombres de `inputSchema.properties`, recorridos hasta **profundidad 5** y **200 nombres** por herramienta | RF-06: un esquema hostil muy anidado no cuelga el análisis. | Recorrido completo recursivo: riesgo de recursión profunda. |
| **`openWorldHint: true` suma U y E**; `readOnlyHint` y `destructiveHint` no restan nada | E13: las anotaciones vienen del servidor que se evalúa. | Usar `readOnlyHint: true` para descartar E: un servidor malicioso lo pondría siempre. |
| **Lo declarado reemplaza la inferencia de esa herramienta** (no se suma) | D-02 y E11: si el dueño del agente afirma las patas, el reporte respeta eso y lo marca «declarada». | Unir declarado + inferido: el formato propio no serviría para corregir un falso positivo. |
| **Peor caso**: cada herramienta `sin_clasificar` cuenta como P+U+E sin restricción | E12, Zero Trust. Se reporta aparte; la severidad principal no se infla. | Ignorarlas: un agente con herramientas opacas saldría «ninguna». |
| **Fragmento de evidencia = el token que calzó**, máx. 40 caracteres | RF-07: nunca se devuelve la descripción. | Devolver la frase: puede traer la inyección o datos sensibles. |
| **Recomendaciones fijas** por combinación de patas (`R-CORTAR-E`, `R-SEPARAR-AGENTE`, `R-ALLOWLIST`, `R-APROBACION`, `R-CLASIFICAR`) | Deterministas y probables; enlazan con los módulos 3 y 5 que vienen. | Texto generado: no determinista. |
| **Tope de 1 MB como middleware global en `core/tope.py`** | Hoy no hay otro endpoint con cuerpo; ponerlo global deja la protección para los módulos siguientes. Rechaza por `Content-Length` y también cuenta bytes si llega sin él (chunked). | Solo en esta ruta: el próximo módulo podría olvidarlo. |
| **Límite de 500 herramientas** con `max_length` de Pydantic | `422` con el formato estándar sin código propio. | Validación a mano. |
| **Frontend sin `react-router`**: `App` elige la página por `location.pathname` y los enlaces son `<a>` normales | Dos páginas; el backend ya entrega `index.html` en cualquier ruta (SPEC-0001 E13). Cero dependencias nuevas. | `react-router-dom`: una dependencia para dos rutas. |
| **Validar el JSON en el navegador antes de enviarlo** y traducir 413/422 a texto claro en `triada.ts` | E15, y se prueba con `node --test`. | Enviar texto crudo: errores de parseo como 422 opacos. |

## Reglas iniciales (resumen; la lista completa queda en `reglas.py`)
| Pata | Ejemplos de palabras (es / en) |
|---|---|
| Datos privados (P) | `sql`, `query`/`consulta`, `database`/`base de datos`, `file`/`archivo`, `read_file`, `customer`/`cliente`, `crm`, `inbox`/`bandeja`, `secret`/`secreto`, `credential`, `drive`, `calendar`/`calendario` |
| No confiable (U) | `fetch`, `browse`/`navegar`, `scrape`, `web`, `search`/`buscar` (en la web), `email`/`correo` entrante, `issue`, `ticket`, `comment`/`comentario`, `upload`/`subido`, `rss` |
| Salida externa (E) | parámetro `url`/`uri`/`endpoint`/`webhook`; `send`/`enviar`, `post`, `notify`/`notificar`, `email`/`correo` saliente, `slack`, `publish`/`publicar`, `create_issue`, `http`, `request` |

`fetch`/`browse` con parámetro `url` cubre U **y** E (E7). La ambigüedad de `email`/`correo` (leer vs
enviar) se resuelve con el verbo que lo acompaña (`read`/`leer` → P+U; `send`/`enviar` → E); sin verbo,
cuenta para las dos.

## Reglas del proyecto revisadas
- Módulo por dominio: `triada` no importa nada de otros módulos de dominio; `main` solo usa
  `triada.router`. Sin acceso a la base, así que la regla de `asyncpg` sigue intacta.
- Pydantic en todos los endpoints, mypy `strict`, sin IA ni red en el análisis.
- Nunca se refleja contenido del manifiesto más allá de nombres y tokens (RF-07).
- **Sin excepciones a las reglas.**

## Validación
1. `pytest`: reglas una por una (activa / no activa), normalizadores MCP y propio, severidades
   E1–E5, evidencia E6–E8, sin clasificar E12, anotaciones E13, límites 413/422, casos borde y los
   manifiestos de referencia. Prueba de rendimiento: 500 herramientas < 200 ms.
2. `npm test`: validación local del JSON, traducción de errores y etiquetas de severidad.
3. Manual con `docker compose`: pegar el ejemplo en `/modulos/triada` → **crítica**; un manifiesto MCP
   real de un servidor conocido (p. ej. el de sistema de archivos) → resultado razonable.
4. Las 5 capas en verde.

## Riesgos
| Categoría | Riesgo | Mitigación |
|---|---|---|
| Técnico | Reglas por palabras: falsos positivos y negativos. | Evidencia visible en cada pata, formato propio para corregir declarando, y una prueba por regla. El peor caso cubre lo que no calza. |
| Seguridad | Un manifiesto hostil (anidamiento, cadenas enormes) consume CPU. | Tope de 1 MB, 500 herramientas, profundidad 5 y 200 parámetros por herramienta; prueba de rendimiento. |
| Seguridad | El endpoint no tiene autenticación. | No guarda ni devuelve datos ajenos (D-03); la autenticación llega con la primera spec que guarde datos. |
| Mantenibilidad | Las reglas crecen sin orden. | Un solo archivo de datos, ids estables (`P-BD`, `E-URL`…) y cada regla con su prueba. |
