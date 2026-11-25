# SPEC-0002 — Detector de la Tríada Letal

> Estado: **aprobada** (decisiones D-01 a D-03) · Autor: Alex · Fecha: 2026-11-25
> Módulo 1 de 5 (`app/triada`). Análisis **estático**: revisa el manifiesto antes de que el agente
> corra. El análisis dinámico (lo que el agente invoca de verdad) necesita el proxy en tiempo de
> ejecución y queda para cuando existan los módulos 3 y 4.

## Objetivo
Dado el manifiesto de herramientas de un agente, decir si reúne la **Tríada Letal** y por qué:

1. **Datos privados (P):** alguna herramienta lee información que no debe salir (BD, archivos,
   correo, CRM, secretos).
2. **Contenido no confiable (U):** alguna herramienta mete en el contexto texto que un tercero
   controla (web, correos entrantes, issues, documentos subidos, respuestas de otra API).
3. **Salida externa (E):** alguna herramienta puede enviar datos fuera (webhooks, HTTP, correo,
   crear un issue público, **o pedir una URL que el atacante elige**).

Si las tres conviven en el mismo agente y la salida no está restringida, una inyección de prompt en
(U) puede hacer que el modelo lea (P) y lo saque por (E). El detector lo alerta como **crítico** y
dice qué pata conviene cortar. No usa IA: es determinista, explicable y probado con casos fijos.

## Historias de usuario

### H1 (P1) — Quien despliega un agente sabe si está expuesto
Como responsable de un agente, quiero enviar su manifiesto y recibir un veredicto, para saber si
reúne la tríada antes de ponerlo en producción.

- **E1.** Un manifiesto con herramientas que cubren P, U y E, sin control de egresos → severidad
  **crítica**.
- **E2.** El mismo manifiesto, con todas las herramientas de E restringidas a una allowlist de
  dominios → severidad **alta** (la tríada sigue ahí, pero la salida está acotada; una allowlist mal
  elegida aún filtra).
- **E3.** Dos de tres patas → **media**, indicando cuál falta («a una herramienta de la tríada»).
- **E4.** Una o ninguna → **baja** / **ninguna**.
- **E5.** El veredicto es igual para el mismo manifiesto sin importar el orden de las herramientas.

### H2 (P1) — El resultado se explica
Como responsable, quiero saber qué herramienta aporta cada pata y por qué, para decidir qué cambiar.

- **E6.** Para cada pata, el reporte lista las herramientas que la cubren y la **evidencia**: si fue
  declarada en el manifiesto o inferida (y de qué palabra, campo o anotación).
- **E7.** Una herramienta puede cubrir varias patas (p. ej. `fetch_url` es U **y** E: lee contenido
  del atacante y su URL puede llevar datos afuera). El reporte lo destaca: una sola herramienta así
  ya es media tríada.
- **E8.** El reporte incluye recomendaciones concretas según las patas presentes (quitar la
  herramienta, separar el agente en dos, pasar E por la allowlist del módulo 3, exigir aprobación
  humana del módulo 5).

### H3 (P1) — Manifiestos reales
Como responsable, quiero pegar lo que ya tengo, sin reescribirlo a un formato propio.

- **E9.** Acepta la respuesta de `tools/list` de un servidor **MCP** tal como viene (`name`,
  `description`, `inputSchema`, `annotations`).
- **E10.** Acepta el formato propio de AgentGuard, donde cada herramienta puede declarar sus patas
  explícitamente (`datos_privados`, `no_confiable`, `salida_externa`) y si su salida
  está restringida.
- **E11.** Lo declarado manda sobre lo inferido (D-02).

### H4 (P2) — Herramientas que no se pueden clasificar
- **E12.** Una herramienta sin declaración ni señales queda **sin clasificar**. El reporte lo dice y
  marca el análisis como **incompleto**, mostrando además la severidad en el **peor caso** (si las
  sin clasificar cubrieran todas las patas). Zero Trust: no se asume que una herramienta
  desconocida es inofensiva.
- **E13.** Las anotaciones MCP (`readOnlyHint`, `openWorldHint`, etc.) **no bajan** la severidad por
  sí solas: el estándar MCP las define como pistas no confiables que entrega el propio servidor. Solo
  pueden sumar patas, nunca quitarlas.

### H5 (P1) — Usar el detector desde la web
- **E14.** La pantalla `/modulos/triada` permite pegar el manifiesto (o cargar un archivo `.json`) y
  muestra la severidad, las tres patas con sus herramientas y evidencia, y las recomendaciones.
- **E15.** Un JSON inválido o con forma desconocida muestra el error en lenguaje claro, sin traza.
- **E16.** En la página de estado, el módulo 1 pasa de «Pendiente» a «Activo».

## Requisitos funcionales
- **RF-01.** `POST /api/v1/triada/analisis` recibe el manifiesto (E9 o E10) y responde el reporte.
  Es puro: **no guarda nada** ni llama a servicios externos (D-03).
- **RF-02.** El formato se detecta solo: objeto con `tools` (MCP) o con `herramientas` (propio).
  Ambos se normalizan al mismo modelo interno antes de analizar.
- **RF-03.** Clasificación por herramienta, en este orden: (1) patas declaradas; (2) anotaciones MCP
  (`openWorldHint: true` suma U y E); (3) reglas por palabras en nombre, descripción y nombres de
  parámetros (p. ej. `url`, `webhook`, `send`, `email`, `query`, `sql`, `file`, `read`, `search`,
  `browse`), en español e inglés. Cada regla tiene un identificador que aparece en la evidencia.
- **RF-04.** Las reglas viven en un archivo de datos versionado (`app/triada/reglas.py` o `.json`),
  no repartidas por el código, para poder sumarlas sin tocar la lógica.
- **RF-05.** Severidad: `critica` (P+U+E, alguna E sin restringir), `alta` (P+U+E, toda E
  restringida), `media` (dos patas), `baja` (una), `ninguna` (cero). Se calcula también la de peor
  caso cuando hay herramientas sin clasificar (E12).
- **RF-06.** Límites: hasta **500 herramientas** y **1 MB** por petición; más → `413` o `422` con
  mensaje claro. Un `inputSchema` muy anidado no debe colgar el análisis (se recorre con profundidad
  máxima).
- **RF-07.** El reporte nunca repite descripciones completas del manifiesto: solo nombre de la
  herramienta y el fragmento corto que activó la regla (una descripción puede traer una inyección o
  datos sensibles).
- **RF-08.** El veredicto es determinista (E5) y el reporte ordena herramientas y patas de forma estable.

## Casos borde
- Manifiesto vacío (`tools: []`) → `ninguna`, no error.
- Dos herramientas con el mismo nombre → `422` (el manifiesto es ambiguo).
- Una descripción con instrucciones («ignora lo anterior…») se trata como texto; nunca se ejecuta ni
  se refleja completa (RF-07).
- Herramienta declarada sin patas (`[]` explícito) cuenta como clasificada e inofensiva: el usuario
  lo afirmó, y queda indicado como «declarado».
- Allowlist declarada vacía (`[]`) equivale a sin salida permitida: esa E cuenta como restringida.
- Texto con mayúsculas, tildes o `snake_case`/`camelCase` (`sendEmail`, `enviar_correo`) activa
  las mismas reglas.

## Criterios de éxito
- Un conjunto de **manifiestos de referencia** versionado en las pruebas (agente de correo, agente
  de navegación, asistente de BD interno, agente de soporte con tickets públicos, agente solo
  lectura) da el veredicto esperado en cada caso.
- Cada regla de RF-03 tiene al menos una prueba que la activa y otra que no la activa por error.
- Las 5 capas en verde; ninguna prueba unitaria abre red.
- Analizar 500 herramientas tarda menos de 200 ms en el CI.

## Supuestos
- Sin autenticación todavía: el endpoint no guarda ni devuelve datos de otros usuarios, así que el
  riesgo es bajo. La autenticación llega con la primera spec que guarde datos.
- LangChain y otros formatos quedan fuera; se suman como un normalizador más.
- El análisis dinámico (contar qué herramientas usa el agente en una sesión) queda para después.

## Decisiones (D-01 a D-03, antes preguntas abiertas; aprobadas por Alex el 2026-11-25)
- **D-01 → MCP `tools/list` + formato propio de AgentGuard.** MCP es el estándar de facto; el
  formato propio es necesario porque permite declarar las patas y la allowlist, cosa que MCP no tiene.
- **D-02 → declarado > anotaciones > reglas por palabras**, con evidencia en cada paso, y sin
  clasificar = peor caso aparte (E12). Sin IA en esta spec: el veredicto debe ser determinista,
  gratis y no atacable con la misma inyección que se busca detectar. **Abierto a futuro:** un modelo
  local (sin enviar el manifiesto afuera) como segunda opinión, que **solo pueda sumar patas, nunca
  quitarlas**, igual que las anotaciones (E13).
- **D-03 → no se guardan los análisis en esta spec.** Queda como spec futura: historial de análisis,
  que exige autenticación y política de retención (un manifiesto revela la arquitectura interna).
