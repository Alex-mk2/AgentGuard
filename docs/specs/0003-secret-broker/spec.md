# SPEC-0003 — Secret Broker

> Estado: **aprobada** (decisiones D-01 a D-03) · Autor: Alex · Fecha: 2026-11-25
> Módulo 2 de 5 (`app/secretos`). Rompe la pata de **datos privados** en lo que más duele: las
> credenciales. Primera funcionalidad que hace llamadas de red salientes.

## Objetivo
Que un agente pueda usar una API con credenciales **sin que el modelo vea nunca la credencial**.
Hoy lo común es poner la API key en el prompt, en una variable que una herramienta imprime, o en
el código que el modelo escribe: una inyección de prompt basta para que el modelo la repita o la
envíe afuera.

Con el Secret Broker el agente pide **«ejecuta la acción `github.crear_issue` con estos
parámetros»**. AgentGuard comprueba que ese agente puede usar esa acción, arma la petición HTTP
según una definición fija, **inyecta el secreto en el lugar declarado** (p. ej. la cabecera
`Authorization`), la ejecuta y devuelve la respuesta **limpia de cualquier rastro del secreto**. El
modelo solo conoce el nombre de la acción y sus parámetros.

```
Agente ──(acción + parámetros, con su token de agente)──▶ AgentGuard ──(petición + secreto)──▶ API externa
Agente ◀──────────(respuesta sin el secreto)──────────── AgentGuard ◀────────(respuesta)────────
```

## Historias de usuario

### H1 (P1) — El agente ejecuta una acción sin ver la credencial
Como agente, quiero pedir una acción por su nombre con parámetros, para usar una API sin manejar
su credencial.

- **E1.** `POST /api/v1/secretos/acciones/{accion}` con parámetros válidos y un token de agente
  autorizado → AgentGuard hace la petición declarada con el secreto inyectado y responde el código
  y el cuerpo de la API externa.
- **E2.** El secreto **no aparece** en la respuesta al agente: ni en el cuerpo, ni en las cabeceras,
  ni codificado (base64, URL), aunque la API externa lo devuelva (p. ej. un endpoint de depuración
  que repite las cabeceras). Si aparece, se reemplaza por `[SECRETO]`.
- **E3.** El secreto no aparece en ningún log ni en ningún error, tampoco cuando la API externa
  falla o no responde.

### H2 (P1) — Solo quien corresponde usa cada acción
Como responsable del despliegue, quiero que cada agente use solo sus acciones, para aplicar
mínimo privilegio.

- **E4.** Sin token de agente o con un token inválido → `401`. El tiempo de respuesta no revela si
  el agente existe (comparación en tiempo constante).
- **E5.** Agente válido pidiendo una acción que no tiene asignada → `403`, **exista o no**: así no
  se revela qué acciones existen.
- **E6.** Parámetros que no cumplen la definición (falta uno, sobra uno, no calza con su patrón o
  largo) → `422`, sin repetir el valor recibido.

### H3 (P1) — El modelo no puede desviar la petición
Como responsable, quiero que los parámetros del modelo no cambien a dónde va la credencial.

- **E7.** El esquema, el host y el método de cada acción son **fijos** en su definición: los
  parámetros solo rellenan huecos declarados (ruta, query o cuerpo JSON) y van codificados. Un
  parámetro con `../`, `@`, `?`, `#` o un host completo no cambia el destino (anti-SSRF).
- **E8.** Solo `https` (salvo una excepción explícita para `localhost` en desarrollo y pruebas). No
  se siguen redirecciones: un `3xx` se devuelve tal cual, sin enviar el secreto a otro host.
- **E9.** El texto `{secreto}` o el nombre de un secreto dentro de un parámetro **nunca** se
  reemplaza: la inyección solo ocurre en el lugar que declara la acción.
- **E10.** Timeout de la API externa (10 s por defecto) → `504`; error de red → `502`; respuesta de
  más de 1 MB → se corta y se responde `502`. Ninguno incluye el secreto ni la URL con query.

### H4 (P2) — Quien opera ve qué hay cargado, nunca los valores
- **E11.** `GET /api/v1/secretos/estado` (con el token de administración) lista las acciones, los
  agentes y los **nombres** de los secretos, indicando si cada secreto está cargado. Nunca los
  valores, ni un prefijo, ni su largo.
- **E12.** Una acción que referencia un secreto no cargado se marca **no disponible** y responde
  `503` si se pide.
- **E13.** La pantalla `/modulos/secretos` muestra ese estado; el módulo 2 pasa a «Activo».

### H5 (P2) — Auditoría
- **E14.** Cada ejecución deja un registro con fecha, agente, acción, código de la API externa y
  duración. **Sin** parámetros, cuerpo ni cabeceras (pueden traer datos privados).

### H6 (P1) — Si AgentGuard cae, el daño es acotado
Riesgo principal del patrón broker: AgentGuard concentra credenciales. Estas historias achican cuánto
vale robarlas y desde dónde se pueden robar (opciones 1, 2 y 3 de la revisión del 2026-11-25).

- **E15.** Un secreto usado por más de una acción aparece en `/estado` como **compartido**, con un
  aviso: lo recomendado es un token de alcance mínimo por acción (p. ej. un token *fine-grained* de
  GitHub limitado a un repositorio y a issues).
- **E16.** Cada agente tiene un límite de peticiones por minuto (30 por defecto, configurable). Al
  pasarlo → `429` con `Retry-After`, y la auditoría lo registra como advertencia.
- **E17.** El proceso no deja volcados de memoria (*core dumps*) ni permite que otro proceso del
  mismo usuario lea su memoria; corre con sistema de archivos de solo lectura, sin *capabilities* y
  sin poder ganar privilegios, y no necesita una shell para arrancar ni para su *healthcheck*.

## Requisitos funcionales
- **RF-01.** Configuración declarativa (D-02): acciones (id, descripción, método, URL con huecos,
  parámetros con tipo/patrón/largo, dónde va cada parámetro, secreto que usa y cómo se inyecta) y
  agentes (id, acciones permitidas). Se valida al arrancar; una configuración inválida no impide
  arrancar el resto de AgentGuard, pero el módulo queda deshabilitado con el error en el log.
- **RF-02.** Los secretos se cargan en memoria (D-01) como `SecretStr` y solo se leen en el
  momento de inyectarlos. Ningún `repr`, log, error ni respuesta los incluye.
- **RF-03.** Inyección soportada: cabecera (`Authorization: Bearer {secreto}`, `X-Api-Key:
  {secreto}`) y parámetro de query. No se soporta meter el secreto en el cuerpo (riesgo de que la
  API lo refleje en recursos creados, como el texto de un issue).
- **RF-04.** Los tokens de agente y de administración se guardan como hash (SHA-256) y se comparan
  en tiempo constante.
- **RF-05.** Limpieza de la respuesta (E2): cuerpo y cabeceras se revisan contra el valor del
  secreto en claro, en base64, en base64 URL y en URL-encoding. Las cabeceras de la API externa se
  filtran por allowlist (`content-type`, `retry-after`, `x-ratelimit-*`, …); `set-cookie` nunca pasa.
- **RF-06.** Tope de 1 MB a la petición del agente (el global de SPEC-0002) y a la respuesta externa.
- **RF-07.** Sin IA: el broker no decide nada con un modelo.
- **RF-08.** Los secretos se obtienen a través de una interfaz (`FuenteSecretos`). Esta spec trae la
  fuente de variables de entorno (D-01); un gestor externo o credenciales de vida corta se suman como
  otra fuente sin tocar el resto del broker.
- **RF-09.** Límite por agente en memoria (ventana deslizante de 60 s); vale porque la app corre en un
  solo proceso (SPEC-0001).
- **RF-10.** Endurecimiento: `RLIMIT_CORE = 0` y proceso no *dumpable* (`prctl(PR_SET_DUMPABLE, 0)`)
  al arrancar, en Linux; `docker-compose.yml` y la capa `imagen` del CI corren el contenedor con
  `--read-only`, `--tmpfs /tmp`, `--cap-drop ALL` y `--security-opt no-new-privileges`.

## Casos borde
- Dos acciones usan el mismo secreto; un agente con dos acciones; un agente sin acciones (todo `403`).
- Un secreto vacío cuenta como no cargado (E12).
- Un secreto muy corto (< 8 caracteres) se rechaza al cargar: limpiarlo de la respuesta borraría
  texto legítimo y además es débil.
- La API externa responde texto no JSON o binario: se devuelve como texto/base64 con su tipo, también
  limpio.
- El parámetro es un número o booleano en el cuerpo JSON: se respeta el tipo declarado.
- Petición del agente con cabeceras propias (`Authorization` hacia la API externa): se ignoran;
  solo pasan las que declara la acción.

## Criterios de éxito
- Ninguna prueba unitaria abre red: la API externa se simula con `httpx.MockTransport`.
- Hay una prueba por cada vía de fuga conocida: eco en el cuerpo, eco en cabeceras, eco codificado,
  error de red con la URL, excepción con el valor, log, `repr` de la configuración, redirección a
  otro host y SSRF por parámetro.
- Las 5 capas en verde; la imagen sigue arrancando sin configuración del broker, ahora con solo
  lectura y sin *capabilities*.

## Supuestos
- El agente (o su runtime de herramientas, p. ej. un servidor MCP) llama a AgentGuard por HTTP con
  su token. Exponer las acciones como herramientas MCP queda para después.
- El control de egresos general (allowlist global, DLP del cuerpo) es del **módulo 3**; aquí el
  único destino posible es el host fijo de cada acción.
- Rotar un secreto = cambiarlo en su origen y reiniciar AgentGuard (D-01).
- **Fuera de esta spec, como specs futuras:** separar el broker en un proceso propio sin el resto de
  la superficie (opción 6, la que resuelve de verdad la concentración), un gestor de secretos externo
  (opción 5) y credenciales de vida corta (opción 4). También quitar el binario de la shell de la
  imagen (base *distroless*), que exige rehacer las verificaciones de la capa `imagen`.

## Decisiones (D-01 a D-03, antes preguntas abiertas; aprobadas por Alex el 2026-11-25)
- **D-01 → secretos desde variables de entorno al arrancar** (`AGENTGUARD_SECRETO_<NOMBRE>`), en
  memoria mientras corre. Estándar 12-factor; compatible con los gestores de secretos de cualquier
  plataforma; AgentGuard no custodia secretos en disco ni en la base.
- **D-02 → acciones y agentes en un archivo JSON versionado**, validado al arrancar: cada permiso
  nuevo pasa por un PR.
- **D-03 → auditoría en el log estructurado** por ahora; la tabla queda para la spec de historial
  (la misma que espera SPEC-0002 D-03).
