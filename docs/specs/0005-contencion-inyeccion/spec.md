# SPEC-0005 — Contención de prompt injection y rogue actions

> Estado: **aprobada** (decisiones D-01 a D-03) · Autor: Alex · Fecha: 2026-11-26
> Módulo 4 de 5 (`app/inyeccion`). Ataca la pata de **contenido no confiable** de la Tríada Letal y,
> sobre todo, lo que pasa *después* de que una inyección entra al contexto. Construye sobre el
> Secret Broker (SPEC-0003) y el control de egresos (SPEC-0004), que ya marca sus respuestas como
> `"origen": "no_confiable"`.

## Objetivo
Que una inyección de prompt que llega en una página, un correo, un documento, la memoria u otro
agente **no pueda convertirse en una acción con efecto**, aunque el modelo la obedezca.

Detectar inyecciones con reglas es un freno útil, pero no basta: el atacante puede reescribir el
texto hasta que ninguna regla calce, y un clasificador con LLM es atacable con la misma inyección
(SPEC-0002 D-02). Por eso esta spec tiene dos capas, y la garantía está en la segunda:

1. **Inspección** (freno): cada salto de contenido hacia el modelo pasa por reglas deterministas que
   quitan lo invisible, marcan las señales de inyección y envuelven el contenido como dato.
2. **Contención** (garantía): AgentGuard sabe qué sesiones ingirieron contenido no confiable. Una
   sesión **contaminada** pierde las acciones con efecto, se haya detectado la inyección o no. Así
   la tríada se rompe en tiempo de ejecución: la misma sesión no puede leer lo no confiable y además
   escribir hacia afuera.

```
contenido ──▶ inspección ──▶ sesión contaminada ──▶ ¿acción con efecto? ──▶ 403 (módulo 5: aprobación)
 (web, correo,   │ invisibles fuera                        │ solo lectura ──▶ permitida
  memoria, A2A)  │ señales + envoltorio
```

## Historias de usuario

### H1 (P1) — El contenido no confiable llega limpio, marcado y envuelto
Como quien integra un agente, quiero pasar por AgentGuard todo texto que vaya a entrar al contexto
del modelo, para quitarle lo que el modelo lee pero una persona no ve y señalar lo que parece una
instrucción.

- **E1.** `POST /api/v1/inyeccion/inspeccion` (token del agente) con
  `{"contenido": "...", "origen": "web|correo|documento|memoria|agente|herramienta", "tipo": "texto|html|markdown"}`
  → `{"contenido": <saneado>, "marcado": <envuelto>, "senales": [{"regla", "conteo"}], "nivel": "ninguna|sospechosa|alta", "saneado": bool}`.
  Sirve para los saltos que AgentGuard no ve pasar: lecturas de memoria, mensajes de otro agente,
  documentos y fragmentos de RAG.
- **E2.** Reglas deterministas, cada una con su id:
  - `iny.invisible`: caracteres que el modelo lee y una persona no ve, como el bloque de etiquetas
    Unicode (U+E0000–E007F), los de ancho cero y los controles bidireccionales. **Se eliminan
    siempre**: no tienen uso legítimo en el contenido que lee un agente.
  - `iny.rol`: marcas de plantilla o de rol (`<|im_start|>`, `[INST]`, `<<SYS>>`, `<system>`,
    `Assistant:` al inicio de una línea, etc.).
  - `iny.instruccion`: frases de secuestro en español e inglés («ignora las instrucciones
    anteriores», «ignore previous instructions», «ahora eres», «no se lo digas al usuario», etc.).
  - `iny.herramienta`: texto que imita una llamada a herramienta (`tool_calls`, `<function_calls>`,
    JSON `{"name": …, "arguments": …}`) o que nombra acciones del propio agente.
  - `iny.exfil_markdown`: imágenes Markdown o HTML hacia una URL externa con query; un cliente que
    las renderiza filtra datos sin que el agente llame a ninguna herramienta.
  - `iny.oculto` (solo `html`): texto dentro de comentarios, `display:none`, `visibility:hidden`,
    `font-size:0` o con el mismo color que el fondo.
  - `iny.marcador`: frases propias de la configuración.
- **E3.** El envoltorio (*spotlighting*): `marcado` trae el contenido entre delimitadores con un id
  aleatorio por llamada (`«no_confiable:7f3a…»` … `«/no_confiable:7f3a…»`), y se neutraliza
  cualquier delimitador que imite al real dentro del contenido. El runtime lo pone en el contexto en
  vez del texto plano y le indica al modelo que lo que está entre esos delimitadores es un dato.
- **E4.** La respuesta y la auditoría muestran solo los ids de las reglas y sus conteos, **nunca** el
  fragmento que calzó. Repetirle la inyección al agente no sirve de nada y el registro tampoco debe
  guardarla.
- **E5.** Qué hace cada regla al calzar se configura por regla: `marcar` (señal y sigue), `bloquear`
  (el contenido no se entrega) u `observar` (solo auditoría). Por defecto todas `marcar` (D-01).

### H2 (P1) — Una sesión que leyó contenido no confiable pierde las acciones con efecto
Como responsable del despliegue, quiero que una sesión que ingirió contenido no confiable no pueda
ejecutar acciones con efecto, para que una inyección no detectada tampoco llegue a hacer daño.

- **E6.** Sesiones: `POST /api/v1/inyeccion/sesiones` (token del agente) abre una sesión y devuelve
  su id. El runtime lo manda en la cabecera `X-AgentGuard-Sesion` en el broker, en el egreso web y en
  la inspección. Sin la cabecera, el agente entero cuenta como una sola sesión implícita. Un id
  desconocido, vencido o de otro agente → `409 Sesión desconocida`, **sin** cambiar a la implícita
  (falla cerrada: un reinicio de AgentGuard no limpia una sesión contaminada).
- **E7.** La sesión queda **contaminada** apenas entra a ella contenido no confiable:
  - respuestas del egreso web (SPEC-0004 E13);
  - respuestas de acciones del broker, salvo las declaradas `"respuesta": "confiable"` en la
    configuración (por defecto todas son no confiables: un issue de GitHub o un correo los escribe
    cualquiera);
  - inspecciones (E1) con un `origen` que la configuración del agente no marque como confiable.

  Se contamina por el origen del contenido, **no** por las señales: una inyección que ninguna regla
  detecta contamina igual.
- **E8.** En una sesión contaminada, una acción con efecto → `403` con
  `{"detail": {"mensaje": "Sesión contaminada: acción con efecto bloqueada", "origen": "web"}}`.
  Acción con efecto: en el broker, todo método distinto de `GET`; en el egreso web, `POST`. Las
  lecturas siguen permitidas (D-02). El módulo 5
  reemplazará este `403` por una solicitud de aprobación humana.
- **E9.** La contaminación no se limpia desde el agente: solo cerrando la sesión
  (`DELETE /api/v1/inyeccion/sesiones/{id}`, el runtime al descartar ese contexto), por inactividad
  (TTL configurable, 30 min por defecto) o por un administrador. La sesión implícita se limpia solo
  por TTL o por un administrador.

### H3 (P2) — Cada sesión solo puede usar las acciones de su tarea
Como responsable, quiero acotar una sesión a las acciones que su tarea necesita, para que un agente
secuestrado no use el resto de su catálogo.

- **E10.** Al abrir la sesión, el runtime puede declarar `{"acciones": [...]}`, un subconjunto de
  las del agente. Fuera de ese subconjunto → `403 Acción fuera de la sesión`, aunque el agente la
  tenga. El catálogo MCP (SPEC-0004 E10) pedido con la cabecera de sesión lista solo esas acciones.
- **E11.** Lo mismo para el egreso web: `{"hosts": [...]}` como subconjunto de la allowlist del agente.

### H4 (P2) — Quien opera ve qué entra y qué se contuvo
- **E12.** `GET /api/v1/inyeccion/estado` (token de administración): las reglas con su modo, los
  orígenes confiables por agente, las sesiones activas y contaminadas (id, agente, origen de la
  contaminación y hora; nunca contenido) y los contadores desde el arranque por regla y por bloqueo.
- **E13.** La pantalla `/modulos/inyeccion` muestra ese estado; el módulo 4 pasa a «Activo».

## Requisitos funcionales
- **RF-01.** Configuración declarativa y versionada (`INYECCION_CONFIG`, mismo criterio que
  SPEC-0004 RF-01): modo por regla, marcadores, orígenes confiables por agente y TTL de sesión. Si
  es inválida, el resto de AgentGuard arranca igual y el módulo responde `503`. **Sin configuración
  el módulo funciona con los valores por defecto**: la contención no depende de que alguien la active.
- **RF-02.** Inspección determinista y sin IA (SPEC-0002 D-02), en tiempo lineal y como máximo
  sobre el tope de 1 MB. Antes de aplicar las reglas, el texto se normaliza (NFKC, sin invisibles,
  minúsculas, espacios colapsados) para que «i g n o r a» o los homoglifos de ancho completo no las
  esquiven. El contenido entregado es el saneado, no el normalizado.
- **RF-03.** Dependencias en un solo sentido: `secretos` y `egresos` llaman a `app.inyeccion`, que
  solo usa `app.agentes`. `app/inyeccion` no hace red ni importa `httpx`.
- **RF-04.** El estado de las sesiones vive en memoria del proceso. Lo que no se encuentra falla
  cerrado (E6), así que perderlo nunca reabre una sesión contaminada.
- **RF-05.** La sesión no viaja en el contexto del modelo: la pone el runtime en una cabecera, como
  el token. Que el modelo no la pueda elegir es un supuesto del despliegue, igual que el token.

## Casos borde
- Frases de inyección con homoglifos (ｉｇｎｏｒｅ), separadas por invisibles o por saltos de línea.
- Etiquetas Unicode que codifican texto ASCII completo («ASCII smuggling»).
- Un artículo legítimo sobre prompt injection que cita «ignore previous instructions»: falso
  positivo esperado; por eso existen `marcar` y `observar`.
- Un delimitador de envoltorio falso dentro del contenido, con el formato correcto y un id inventado.
- HTML con la inyección en `alt`, `title` o un `aria-label`.
- Contenido que llega en partes: cada parte contamina por su origen, no hace falta unirlas.
- Una acción `GET` con parámetros en una sesión contaminada: puede llevar datos en la query hacia
  un host permitido. El DLP sigue aplicando y el riesgo residual queda documentado (D-02).

## Criterios de éxito
- Una prueba por regla y por cada evasión de los casos borde, y una prueba de que una inyección
  **sin señales** también contamina y bloquea la acción con efecto siguiente.
- Inspección de 1 MB en menos de 100 ms en el CI.
- Ninguna prueba abre red (mismos dobles de SPEC-0004).
- Las 5 capas en verde.

## Supuestos
- El runtime del agente, no el modelo, guarda el token y la sesión y es quien llama a AgentGuard.
  Un runtime comprometido queda fuera del modelo de amenaza (igual que en SPEC-0003).
- Para que H1 cubra la memoria y el agente a agente, el runtime tiene que pasar ese contenido por
  la inspección. AgentGuard ve solo el egreso web y el broker por sí mismo.
- **Fuera de esta spec:** la aprobación humana (módulo 5), un clasificador con modelo que sume
  señales, la persistencia de sesiones en Postgres y la inspección de las salidas del modelo al
  usuario final.

## Decisiones (D-01 a D-03, antes preguntas abiertas; aprobadas por Alex el 2026-11-26)
- **D-01 → todas las señales `marcar` por defecto**; `iny.invisible` se elimina siempre. La garantía
  es la contaminación (H2), no la detección: bloquear por señales perdería contenido legítimo (un
  artículo que cita «ignore previous instructions») sin cerrar el riesgo. Cada regla puede subir a
  `bloquear` en la configuración.
- **D-02 → una sesión contaminada pierde las acciones con efecto** (no `GET` en el broker, `POST` en
  el egreso web); las lecturas siguen. Cortar toda salida dejaría inútil a un agente que navega tras
  la primera página. Riesgo residual documentado: un `GET` con datos en la query hacia un host
  permitido; lo acotan la allowlist, los parámetros sellados y el DLP.
- **D-03 → el sandbox de ejecución de código va en una spec propia.** Lanzar contenedores exige el
  socket de Docker, que le daría a AgentGuard más poder del que protege; encaja mejor como servicio
  aparte. En esta spec, «acceso desactivado por defecto» lo cumplen H2 (contención) y H3 (acciones
  por sesión).
