# SPEC-0006 — Human-in-the-Loop Gate

> Estado: **aprobada** (decisiones D-01 a D-03) · Autor: Alex · Fecha: 2026-11-26
> Módulo 5 de 5 (`app/aprobacion`). Construye sobre la contención (SPEC-0005), el Secret Broker
> (SPEC-0003) y el egreso web (SPEC-0004).

## Objetivo
Que una acción **irreversible**, que **modifique el plano de control** o que pida una sesión
**contaminada** no se ejecute sin que una persona la vea y la apruebe, y que esa aprobación sirva
**solo para esa acción exacta y una sola vez**.

Hoy, en una sesión contaminada, una acción con efecto termina en `403` (SPEC-0005 E8). Eso es
seguro, pero deja al agente sin salida aunque la acción sea legítima. Con este módulo, ese `403`
pasa a ser una **solicitud de aprobación**: si nadie decide, vence y se niega, así que la garantía
no baja.

```
acción ──▶ ¿necesita aprobación? ──no──▶ sigue como hoy
               │ sí
               ▼
          202 + solicitud ──▶ persona ve agente, acción, destino, parámetros y motivo
               │                      │ aprueba            │ niega / vence
               ▼                      ▼                    ▼
   runtime reintenta con   boleto de un solo uso,     403 (sin ejecutar)
   X-AgentGuard-Aprobacion  atado a esa acción exacta ──▶ se ejecuta una vez
```

«Plano de control» aquí es el de los **sistemas destino** (permisos, IAM, claves, webhooks,
configuración de un repo). El de AgentGuard (sus archivos de configuración, cerrar sesiones) ya no
lo alcanza el agente: va por PR o con el token de administración.

## Historias de usuario

### H1 (P1) — Una acción que necesita aprobación queda en pausa, no se ejecuta
Como responsable del despliegue, quiero que las acciones riesgosas esperen una decisión humana en
vez de ejecutarse o fallar sin más.

- **E1.** Cada acción declara en `acciones.json` cuándo necesita aprobación:
  `"aprobacion": "siempre" | "si_contaminada" | "nunca"`. Por defecto `si_contaminada`.
  - `siempre`: irreversibles o del plano de control (borrar un repo, cambiar permisos, rotar una
    clave), aunque la sesión esté limpia.
  - `si_contaminada`: el comportamiento de SPEC-0005 E8, pero en vez de `403`, una solicitud.
  - `nunca`: la sesión contaminada vuelve a dar `403` sin solicitud (para acciones que nadie va a
    estar mirando).
  Una acción sin efecto (`GET`) nunca pide aprobación; `siempre` en un `GET` es un error de
  configuración.
- **E2.** El egreso web (`POST` en sesión contaminada) sigue la misma regla, con
  `"web_aprobacion": "si_contaminada" | "nunca"` en cada agente de `acciones.json`, junto a su
  allowlist `web` (por defecto `si_contaminada`).
- **E3.** Cuando hace falta aprobación, AgentGuard valida todo lo que validaría antes de enviar
  (acción del agente, sesión, parámetros, allowlist y DLP) y, si pasa, responde
  `202` con `{"aprobacion": {"id": "...", "estado": "pendiente", "vence": "<ISO 8601>"}}` y
  `Retry-After: 5`, **sin enviar nada**. El runtime consulta con E10 respetando `Retry-After` y
  reintenta la acción con el boleto al quedar aprobada (D-02; el README trae el bucle de ejemplo). Lo que el DLP o la allowlist bloquearían se bloquea como hoy: no se le pide a
  una persona que apruebe algo que igual no saldría.
- **E4.** Una solicitud idéntica (mismo agente, sesión, acción y valores) mientras otra está
  pendiente devuelve la misma solicitud, no una nueva: un agente en bucle no llena la bandeja.

### H2 (P1) — Una persona decide viendo exactamente qué se va a hacer
Como aprobador, quiero ver qué acción se pide, hacia dónde y con qué datos, y por qué se me pide,
para decidir con información y no a ciegas.

- **E5.** `GET /api/v1/aprobacion/solicitudes` (token de administración) lista las pendientes y las
  últimas decididas: agente, sesión abreviada, acción, método, host de destino, **parámetros del
  agente** (cada valor truncado a 2 KB), el motivo (`siempre` o `sesion_contaminada` con su
  origen) y las señales de inyección vistas en la sesión (ids y conteos, nunca contenido).
  Nunca el secreto: se inyecta recién al ejecutar (SPEC-0003).
- **E6.** `POST /api/v1/aprobacion/solicitudes/{id}/decision` (token de administración) con
  `{"decision": "aprobar" | "negar", "nota": "..."}`. Solo una solicitud `pendiente` y no vencida se
  decide; otra cosa → `409`. El token de un agente → `401`: **el agente no puede aprobarse a sí
  mismo**.
- **E7.** La pantalla `/modulos/aprobacion` muestra la bandeja y permite aprobar o negar. Los
  parámetros vienen del agente y pueden traer la inyección: se muestran como texto plano, nunca
  como enlace ni HTML, con un aviso visible cuando la sesión está contaminada.

### H3 (P1) — La aprobación sirve una vez y solo para esa acción
Como responsable, quiero que una aprobación no se pueda reusar ni estirar a otra acción.

- **E8.** Aprobada la solicitud, el runtime reintenta la misma llamada con la cabecera
  `X-AgentGuard-Aprobacion: <id>`. AgentGuard ejecuta solo si coinciden el agente, la sesión y la
  **huella** (SHA-256 de la acción o host, el método y los valores canónicos) con lo aprobado, y si
  el boleto no se usó ni venció. Se consume **antes** de enviar: dos reintentos simultáneos no
  ejecutan dos veces.
- **E9.** Cualquier diferencia (otro parámetro, otra sesión, otro agente, boleto usado, negado o
  vencido) → `403 Aprobación no válida para esta acción`, sin decir cuál de las condiciones falló.
- **E10.** `GET /api/v1/aprobacion/solicitudes/{id}` con el token del agente dueño devuelve solo
  `estado` y `vence` (para esperar sin bloquear la conexión); de otro agente → `404`.
- **E11.** Vencimientos: 15 min para decidir y 5 min para usar el boleto aprobado (configurables).
  Cerrar la sesión (SPEC-0005 E9) cancela sus solicitudes pendientes.
- **E12.** Aprobar no limpia la sesión: la siguiente acción con efecto de una sesión contaminada
  pide su propia aprobación.

### H4 (P2) — Quien aprueba se entera sin estar mirando la pantalla
- **E13.** Opcional: `"notificar": "<id de acción>"` en `APROBACION_CONFIG` nombra una acción del
  broker (p. ej. un webhook de Slack) que AgentGuard ejecuta al crear cada solicitud, con el id, el
  agente, la acción y el motivo; **nunca los parámetros** (son del agente y pueden llevar datos o la
  inyección hacia el canal). Sale por el control de egresos como toda salida. Si falla, la
  solicitud queda igual y el fallo va al log.

### H5 (P2) — Queda registro de quién aprobó qué
- **E14.** Cada solicitud guarda agente, sesión abreviada, acción, huella, motivo, estado, quién
  decidió (`admin`), la nota y las horas de creación, decisión y uso. Los **parámetros** se borran
  al decidir o vencer: el registro guarda la huella, no los datos.
- **E15.** `GET /api/v1/aprobacion/estado` (admin): configuración, contadores (pendientes,
  aprobadas, negadas, vencidas, usadas) y avisos (`notificar` que no existe, acción `siempre` sin
  ningún agente que la use). El módulo 5 pasa a «Activo» en la portada.

## Requisitos funcionales
- **RF-01.** `APROBACION_CONFIG` declarativo y versionado (vencimientos, tope de pendientes,
  `notificar`). Sin archivo valen los valores por defecto; si es inválido, el resto arranca y el
  módulo responde `503`, y lo que pida aprobación se **niega** (`403`): sin aprobador no hay
  aprobación.
- **RF-02.** Tope de 20 pendientes por agente y 1 000 en total → `429`, contra llenar la bandeja
  (*approval fatigue*) o la memoria.
- **RF-03.** Dependencias en un solo sentido: `secretos → aprobacion`, `egresos → aprobacion`,
  `aprobacion → agentes`. `aprobacion` no importa el broker ni hace red: la notificación (E13) la
  ejecuta el broker por una función que recibe.
- **RF-04.** Valores canónicos para la huella: JSON con claves ordenadas, sin espacios y en UTF-8;
  la misma llamada da siempre la misma huella.
- **RF-05.** Los parámetros mostrados al aprobador son entrada hostil: largo acotado, sin
  invisibles (mismo saneado que SPEC-0005 E2) y, en las respuestas `422`, sin reflejar valores.

## Casos borde
- El agente reintenta con el id de una solicitud **pendiente** → `403` (aún no aprobada), no queda
  en espera.
- El agente reintenta con un boleto aprobado pero cambia un parámetro → `403` (E9).
- Dos reintentos simultáneos con el mismo boleto → uno se ejecuta y el otro `403`.
- Un parámetro con un `<script>`, un enlace o caracteres bidireccionales → texto plano y saneado.
- AgentGuard se reinicia con solicitudes pendientes (depende de P-01).
- La acción ejecutada tras aprobar devuelve contenido no confiable: contamina como siempre.
- Una acción `siempre` llamada por un agente con sesión limpia → solicitud con motivo `siempre`.
- La acción de `notificar` también necesitaría aprobación → configuración inválida.

## Criterios de éxito
- La prueba de SPEC-0005 «inyección sin señales bloquea el `POST` siguiente» pasa a esperar `202`
  y que **no salga ninguna petición** hasta aprobar; tras aprobar, sale exactamente una.
- Una prueba por cada condición de E9 y por el reintento simultáneo.
- Ninguna prueba abre red; las de Postgres van marcadas `integracion`.
- Las 5 capas en verde.

## Supuestos
- El runtime, no el modelo, guarda el id de la solicitud y reintenta (igual que el token y la
  sesión). El modelo puede ver «pendiente de aprobación», pero no puede aprobar.
- El aprobador es quien tiene el token de administración. Varios aprobadores con identidad propia
  y aprobación de a dos quedan fuera (necesitan autenticación de personas).
- **Fuera de esta spec:** aprobar desde el canal de notificación con un clic (callback firmado),
  reglas de aprobación automática, y la autenticación de personas en el dashboard.

## Decisiones (D-01 a D-03, antes preguntas abiertas; aprobadas por Alex el 2026-11-26)
- **D-01 → las solicitudes viven en PostgreSQL** (primera migración, `001`). Es un registro de
  auditoría de quién aprobó qué y debe sobrevivir a un reinicio. Con la base caída, lo que pide
  aprobación responde `503` (no se ejecuta) y lo demás sigue igual. Se descartó guardarlas en
  memoria como las sesiones: se pierde la auditoría al reiniciar. Se mantiene una sola base
  (context.md §2): no se suma MySQL.
- **D-02 → `202` + reintento con boleto** (E3, E8, E10). No deja conexiones colgadas durante
  minutos y AgentGuard no guarda la petición para ejecutarla después. Se descartaron mantener la
  conexión abierta hasta la decisión (frágil ante los timeouts de los proxies) y ejecutar al
  aprobar (obliga a guardar parámetros y respuestas).
- **D-03 → la notificación por webhook entra en esta spec**, en la forma de E13: reutiliza una
  acción del broker, sin parámetros y sin callback. Aprobar desde el canal con un clic queda para
  otra spec.
