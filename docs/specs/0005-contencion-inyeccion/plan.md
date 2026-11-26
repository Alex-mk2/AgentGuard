# SPEC-0005 — Plan

> Estado: **aprobado** (Alex, 2026-11-26) · Spec: [spec.md](spec.md)

## Contexto técnico
- **Sin dependencias nuevas.** La normalización usa `unicodedata` (NFKC) y el HTML se recorre con
  búsquedas guiadas por `find` (ver «Desviaciones al implementar»).
- No toca Postgres ni la red: las sesiones y los contadores viven en memoria (un solo proceso,
  SPEC-0001), y lo que no se encuentra falla cerrado (RF-04).
- **Cambio de comportamiento visible:** desde este PR, las respuestas del broker y del egreso web
  contaminan la sesión, y en una sesión contaminada las acciones que no son `GET` responden `403`
  (D-02). Una acción cuya respuesta sea confiable (p. ej. un servicio interno propio) se declara con
  `"respuesta": "confiable"` en `acciones.json`. Las respuestas ganan campos (`origen`,
  `inspeccion`, `marcado`); ninguno existente cambia.

## Estructura

Dependencias en un solo sentido: `secretos → {egresos, inyeccion}`, `egresos → inyeccion`,
`inyeccion → agentes`. `inyeccion` no importa `egresos`, `secretos` ni `httpx`. La prueba de
arquitectura de SPEC-0004 se amplía con el módulo nuevo.

```
backend/app/
  inyeccion/                módulo 4
    __init__.py             exporta Contencion, Contenida, Resultado, crear_contencion, router
    config.py               INYECCION_CONFIG: modos por regla, marcadores, orígenes confiables por
                            agente, TTL de sesión (RF-01); sin archivo → valores por defecto
    normalizar.py           sanear (quita invisibles, E2) y normalizar para calzar: NFKC, casefold,
                            espacios colapsados, letras sueltas unidas («i g n o r a») (RF-02)
    reglas.py               las 7 reglas: prefiltro con `in` + expresiones de formato concreto
                            (la trampa de rendimiento de SPEC-0004 está en PROGRESS.md)
    envoltorio.py           spotlighting: id aleatorio (`secrets.token_hex(8)`) y neutraliza
                            delimitadores falsos (E3)
    inspector.py            Inspector.inspeccionar(contenido, tipo, marcadores) → Resultado
    sesiones.py             Sesiones: abrir, resolver (implícita o explícita), contaminar, cerrar,
                            vencer por TTL; reloj inyectable para las pruebas
    contencion.py           Contencion: la fachada que usan broker y egreso web (abajo)
    rutas.py                POST /inyeccion/inspeccion · POST /inyeccion/sesiones ·
                            DELETE /inyeccion/sesiones/{id} · GET /inyeccion/estado
  secretos/config.py        Accion gana `respuesta: "confiable" | "no_confiable"` (por defecto no)
  secretos/broker.py        ejecutar(…, sesion): resolver → autorizar → enviar → ingerir
  secretos/rutas.py         cabecera X-AgentGuard-Sesion; el catálogo MCP filtra por sesión (E10)
  egresos/web.py            pedir(…, sesion): igual, con hosts de la sesión (E11) y POST con efecto
  core/config.py            Settings.inyeccion_config
  main.py                   crea Contencion antes del broker y la pasa a broker y egreso web
frontend/src/modulos/inyeccion/   pantalla /modulos/inyeccion, lógica en .ts con pruebas (E13)
config/inyeccion.ejemplo.json     modos por defecto, un marcador y orígenes confiables de ejemplo
```

### La fachada `Contencion`
```python
class Contencion:
    def sesion(self, agente: Agente, cabecera: str | None) -> Sesion          # 409 si no existe
    def autorizar_accion(self, sesion: Sesion, accion: str, metodo: str) -> None   # 403
    def autorizar_web(self, sesion: Sesion, host: str, metodo: str) -> None        # 403
    def ingerir(self, sesion: Sesion, origen: Origen, contenido: str | None,
                tipo: Tipo) -> Resultado                                       # contamina + inspecciona
    def acciones_visibles(self, sesion: Sesion, acciones: Sequence[str]) -> list[str]  # E10

class Contenida(Exception):   # codigo (403 | 409 | 429) y detalle sin valores del agente
```
El broker y el egreso web traducen `Contenida` a sus propios errores, como ya hacen con
`Bloqueado`. `Contencion` no conoce el registro de agentes: recibe el `Agente` ya identificado, así
que se crea antes que el broker y no hay ciclos.

### Orden en el broker y en el egreso web
1. Token → agente (`401`), como hoy.
2. **Sesión** (`409` si el id es desconocido). Va antes que el resto para no revelar nada de la
   acción con una sesión ajena.
3. Acción del agente (`403`), como hoy.
4. **Autorizar**: fuera de la sesión (E10, E11) o con efecto en una sesión contaminada (E8) → `403`.
   Va antes del límite por minuto y de enviar: lo bloqueado no sale ni gasta cupo.
5. Límite, parámetros, allowlist, DLP y envío, como hoy.
6. **Ingerir** la respuesta: contamina (siempre en el egreso web; en el broker, salvo con
   `respuesta: confiable`) y, si es texto, la inspecciona. Un cuerpo binario contamina igual. Si una
   regla en modo `bloquear` calza → `403 Contenido bloqueado por inyección` con los ids.

Contaminar en el paso 6 aunque el contenido termine bloqueado es a propósito: es más simple de
razonar y falla del lado seguro.

### Detalles de las reglas
| Regla | Cómo calza | Nivel |
|---|---|---|
| `iny.invisible` | rangos de código: etiquetas U+E0000–E007F, U+200B–200F, U+2060–2064, U+FEFF, U+202A–202E, U+2066–2069 | alta si hay etiquetas; si no, sospechosa |
| `iny.rol` | lista cerrada de marcas (`<\|im_start\|>`, `[inst]`, `<<sys>>`, `<system>`, `### system`) y `assistant:`/`system:` al inicio de línea | alta |
| `iny.instruccion` | ~30 frases es/en sobre el texto normalizado | sospechosa |
| `iny.herramienta` | `tool_calls`, `<function_calls>`, `<tool_use>`, `{"name":…,"arguments"` y los ids de las acciones del agente seguidos de `(` o `{` | alta |
| `iny.exfil_markdown` | `![…](http…?…)` y `<img src="http…?…">` | sospechosa |
| `iny.oculto` | texto no vacío en lo que `html.py` marca como oculto | alta |
| `iny.marcador` | frases de la configuración | sospechosa |

`nivel` es el máximo de las señales. Es informativo: con D-01, por defecto todas solo marcan.

### Sesiones
- Ids con `secrets.token_urlsafe(24)`; se comparan con el agente dueño (el id de otro agente → `409`,
  igual que uno inexistente: no se revela que existe).
- Topes contra agotar la memoria: 100 sesiones abiertas por agente y 10 000 en total → `429`. Las
  vencidas se barren al abrir una nueva.
- La implícita se guarda por agente; si vence, la siguiente llamada empieza una limpia (no hay id
  que el runtime haya guardado).
- `DELETE` con el token del agente dueño cierra la suya; con el token de administración, cualquiera,
  también la implícita (`implicita:<agente>`).

## Decisiones de diseño
- **Una fachada en vez de un middleware.** Un middleware tendría que reconocer cada ruta y leer el
  cuerpo para saber la acción y el método; la fachada se llama donde ya se conocen. Alternativa
  descartada por frágil ante rutas nuevas.
- **Sesiones en memoria y no en Postgres.** Persistirlas no cambia la seguridad, porque lo
  desconocido ya falla cerrado, y agregaría la base al camino de cada llamada. Queda en Pendientes.
- **Normalizar una copia y entregar el saneado.** Entregar el texto normalizado cambiaría contenido
  legítimo (acentos, mayúsculas); solo se quitan los invisibles.
- **`html.parser` y no expresiones sobre el HTML.** Las expresiones sobre HTML anidado son frágiles y
  propensas a retroceso exponencial; el parser de la biblioteca estándar es lineal.

## Riesgos
- **Rendimiento:** NFKC y casefold sobre 1 MB caben con holgura; el riesgo son las frases. Se
  prefiltra con `in` sobre el texto normalizado y solo se corre la expresión si hay candidatos. La
  prueba de 1 MB < 100 ms lo vigila. Sobre 64 KB, la inspección corre en un hilo aparte (mismo
  criterio que el DLP).
- **Falsos positivos** de `iny.instruccion`: solo marcan (D-01).
- **Romper integraciones:** un runtime que escribía después de leer una página ahora recibe `403`.
  Es el objetivo de D-02; se documenta en el README con el ejemplo de `respuesta: confiable` y con
  cómo abrir una sesión nueva por tarea.

## Desviaciones al implementar
- **Sin `html.parser`:** recorrer 1 MB de HTML con él costaba más que el presupuesto de 100 ms. La
  regla `iny.oculto` vive en `reglas.py`: parte de cada `style`/`hidden`, guarda el próximo `>` y
  mira el texto hasta el cierre de la etiqueta (sin anidar), con un presupuesto de caracteres.
  Los atributos `alt`/`title` no necesitan trato aparte: su texto ya está en lo que se inspecciona.
- **Toda expresión se probó contra entradas armadas.** Tres eran cuadráticas y se reescribieron con
  `find`: comentarios sin cerrar (78 s sobre 1 MB), `<img` repetido (9 s) y una palabra de 1 MB tras
  el nombre de una acción (5 s). `test_spec0005_peor_caso_acotado` cubre 15 de esas entradas.
- **Frases por índice de dos palabras + vocabulario**, no un recorrido por frase: hay ~2 000
  combinaciones y contar cada una sobre 1 MB eran 2 000 recorridos del texto.
- **El cuerpo decide si es HTML**, no solo el `content-type`: quien controla el servidor elige la
  cabecera, y la prueba manual mostró HTML servido como `text/plain` (httpbin `/base64`) que se
  saltaba `iny.oculto`. Si el cuerpo empieza con `<!doctype html` o `<html`, se trata como HTML.
- **`ingerir_respuesta`** en la fachada: el broker y el egreso web le pasan el cuerpo decodificado y
  el `content-type`, y reciben los campos de la respuesta (`origen`, `inspeccion`, `marcado`).

## Validación
- **Unitarias:** cada regla con su caso feliz, su evasión (homoglifos, letras separadas,
  invisibles intercalados, ASCII smuggling, HTML en atributos) y su falso positivo esperado;
  envoltorio con delimitador falso; sesiones (TTL, tope, ajena, desconocida → 409); broker y egreso
  web con `MockTransport`: inyección **sin señales** que contamina y bloquea el `POST` siguiente,
  `respuesta: confiable` que no contamina, acciones fuera de la sesión, catálogo filtrado.
- **Arquitectura:** dependencias del módulo nuevo y `httpx` solo en `egresos/salida.py`.
- **Rendimiento:** 1 MB < 100 ms (exigido solo en el CI, como SPEC-0002).
- **Manual** con la imagen endurecida y red real: `httpbin.org/base64/<…>` devuelve texto con una
  inyección (frase, etiquetas Unicode y HTML oculto) → señales, invisibles fuera y envoltorio; el
  `POST` siguiente de la misma sesión → `403`; una sesión nueva → permitido.
