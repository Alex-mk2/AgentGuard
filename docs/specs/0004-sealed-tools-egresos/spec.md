# SPEC-0004 — Sealed Tools y control de egresos

> Estado: **aprobada** (decisiones D-01 a D-03) · Autor: Alex · Fecha: 2026-11-25
> Módulo 3 de 5 (`app/egresos`). Rompe la pata de **salida externa** de la Tríada Letal. Construye
> sobre el Secret Broker (SPEC-0003), que es hoy la única salida de red de AgentGuard.

## Objetivo
Que, aunque una inyección de prompt tome el control del modelo, **los datos privados no puedan salir
hacia un destino que nadie aprobó, ni dentro de los parámetros de una herramienta permitida**.

El módulo 2 ya trae la mitad «sealed»: cada acción tiene esquema, host y método fijos, y el modelo
solo rellena parámetros acotados. Faltan cuatro cosas, que son esta spec:

1. **Un control de egresos independiente de cada definición.** Hoy, si una acción mal revisada
   apunta a un host indebido, nada la frena. Una allowlist global, verificada en el único punto de
   salida y también contra la IP a la que resuelve el host, es una segunda llave.
2. **DLP sobre lo que sale.** Una acción permitida también sirve para exfiltrar: el modelo puede
   poner la base de clientes en el cuerpo de `github.crear_issue`. Hay que mirar el contenido.
3. **Herramientas selladas sin credencial y un catálogo por agente** que un runtime MCP o LangChain
   registre tal cual, para que el modelo solo vea funciones acotadas y nunca arme una URL.
4. **Un egreso controlado para agentes que necesitan la web** (D-03): en vez de darles salida
   libre, pasan por AgentGuard y lo que no está en su allowlist responde `403`.

```
Agente ──▶ AgentGuard ──▶ ¿host en la allowlist? ──▶ ¿IP pública? ──▶ ¿DLP limpio? ──▶ destino
                              │ no → 403                 │ no → 403        │ no → 403
```

## Historias de usuario

### H1 (P1) — Nada sale fuera de la allowlist
Como responsable del despliegue, quiero una lista única de destinos permitidos, para que ninguna
salida dependa solo de que cada definición esté bien escrita.

- **E1.** La allowlist vive en un JSON versionado (`EGRESOS_CONFIG`, mismo criterio que SPEC-0003
  D-02): hosts exactos (`api.github.com`) o subdominios (`*.ejemplo.com`, que **no** incluye
  `ejemplo.com` ni `ejemplo.com.atacante.cl`), con puerto `443` salvo que se declare otro. **Toda**
  petición saliente de AgentGuard, incluidas las del broker, se verifica en el único punto de salida.
  Fuera de la allowlist → `403 Destino no permitido`, sin abrir conexión, y queda en la auditoría.
- **E2.** Antes de conectar, el host se resuelve y **todas** sus IP deben ser públicas: loopback,
  privadas, *link-local* (incluida `169.254.169.254`, la metadata de la nube), CGNAT, multicast y
  reservadas → `403`, aunque el host esté en la allowlist. La conexión va a la IP ya verificada, sin
  una segunda resolución (contra *DNS rebinding*); el certificado TLS se sigue validando contra el
  nombre del host. La excepción de desarrollo `http_local` de SPEC-0003 se mantiene.
- **E3.** Una acción del broker cuyo host no está en la allowlist aparece **bloqueada por egresos**
  en `/secretos/estado` y en `/egresos/estado`, y responde `403` si se pide.
- **E4.** Sin allowlist configurada, **toda salida se bloquea** (D-01).

### H2 (P1) — Los datos privados no salen dentro de los parámetros (DLP)
Como responsable, quiero que AgentGuard revise lo que el agente envía, para que una herramienta
permitida no se convierta en un canal de exfiltración.

- **E5.** Antes de enviar se revisa lo que pone el agente (ruta, query, cuerpo; **no** la credencial
  que inyecta el broker) con reglas deterministas:
  - `dlp.secreto_cargado`: cualquiera de los secretos del broker, en todas sus variantes (SPEC-0003 RF-05).
  - `dlp.credencial`: formatos conocidos (clave privada PEM, AWS, GitHub, Slack, Google, Stripe, JWT).
  - `dlp.tarjeta`: número de tarjeta que cumple Luhn.
  - `dlp.rut`: RUT chileno con dígito verificador válido.
  - `dlp.marcador`: textos propios de la configuración, como etiquetas («CONFIDENCIAL») o
    *canary tokens* sembrados en los datos privados. Si un *canary* sale, es exfiltración segura.
- **E6.** Un hallazgo en una regla en modo `bloquear` → `403` con
  `{"detail": {"mensaje": "Salida bloqueada por DLP", "reglas": ["dlp.tarjeta"]}}`: solo los ids
  de las reglas, **nunca** el valor, un fragmento ni su posición. La auditoría registra agente,
  destino y reglas, tampoco el valor.
- **E7.** Una regla en modo `observar` deja pasar la petición y la registra como advertencia: sirve
  para medir falsos positivos antes de bloquear (D-02).
- **E8.** El DLP también revisa el contenido decodificado **una vez**: URL-encoding y los trozos
  largos (≥ 16 caracteres) en base64 o hex. Un modelo decidido puede cifrar el dato o repartirlo en
  muchas llamadas: el DLP es un freno, no la garantía. La garantía son los parámetros acotados
  (patrón y largo) y la allowlist. Queda documentado.

### H3 (P1) — Herramientas selladas, también sin credencial
Como responsable, quiero entregarle al agente solo funciones acotadas, para que el modelo nunca
arme el payload crudo.

- **E9.** Una acción puede no tener `secreto`: misma definición fija (esquema, host, método,
  parámetros), sin inyección. Sirve para APIs públicas o servicios internos expuestos. Pasa por la
  misma allowlist, el mismo DLP y la misma allowlist de cabeceras de respuesta.
- **E10.** `GET /api/v1/secretos/herramientas` (con el token del agente) devuelve **solo sus**
  acciones como herramientas MCP: `name`, `description`, `inputSchema` (JSON Schema derivado de los
  parámetros: tipo, `pattern`, `maxLength`, `required`, `additionalProperties: false`) y
  `annotations` (`readOnlyHint` en `GET`, `destructiveHint` en `DELETE`, `openWorldHint`). Un
  adaptador MCP o LangChain las registra tal cual.
- **E11.** El mismo catálogo con `?formato=triada` sale como manifiesto del Detector (módulo 1), con
  `egreso.allowlist` igual al host de cada acción: al analizarlo, su salida cuenta como restringida.

### H4 (P2) — Egreso controlado hacia la web (D-03)
Como responsable, quiero que un agente que necesita consultar sitios lo haga a través de AgentGuard,
para no darle salida libre a Internet.

- **E12.** `POST /api/v1/egresos/peticion` con el token del agente y `{"metodo", "url", "cuerpo"}`
  (solo `GET` o `POST`, solo `https`) → AgentGuard la hace si el host está en la allowlist **de ese
  agente** (un subconjunto de la global); si no, `403`. Pasa por E2 y por el DLP.
- **E13.** Sin credenciales ni cookies hacia el destino, sin redirecciones (un `3xx` vuelve tal cual),
  respuesta con tope de 1 MB y cabeceras por allowlist. La respuesta se marca
  `"origen": "no_confiable"`: es la pata U de la tríada, que el módulo 4 inspeccionará.
- **E14.** Comparte el límite por agente del broker (SPEC-0003 E16): un agente no lo esquiva
  repartiendo sus llamadas entre las dos rutas.

### H5 (P2) — Quien opera ve qué está permitido y qué se bloqueó
- **E15.** `GET /api/v1/egresos/estado` (token de administración): la allowlist global y la de cada
  agente, las reglas DLP con su modo, las acciones bloqueadas por egresos y los contadores de
  bloqueos desde el arranque, por regla. Nunca valores.
- **E16.** La pantalla `/modulos/egresos` muestra ese estado; el módulo 3 pasa a «Activo».

## Requisitos funcionales
- **RF-01.** Configuración declarativa y versionada: allowlist global, allowlist por agente, reglas
  DLP con modo (`bloquear` / `observar`) y marcadores. Se valida al arrancar; si es inválida, el resto
  de AgentGuard arranca igual y el módulo responde `503`.
- **RF-02.** Un **único punto de salida** de red: solo `app/egresos` importa `httpx` (hoy es
  `app/secretos/ejecutor.py`; se mueve). Lo verifica una prueba de arquitectura.
- **RF-03.** Hosts normalizados antes de comparar: minúsculas, sin punto final, IDN a punycode. Una
  URL con una IP literal como host se rechaza (la allowlist solo admite nombres).
- **RF-04.** El DLP es determinista y sin IA (mismo criterio que SPEC-0002 D-02). Revisa como máximo
  el tope de 1 MB y en tiempo lineal.
- **RF-05.** Ningún `403` revela qué parte del pedido disparó el bloqueo más allá del id de la regla.
- **RF-06.** La identidad de los agentes y su límite por minuto se comparten entre módulos (hoy viven
  dentro de `app/secretos`); los módulos 4 y 5 también los van a usar.

## Casos borde
- Host con mayúsculas, con punto final (`api.github.com.`), en Unicode, o con un puerto no declarado.
- IP escrita en decimal (`2130706433`), octal o como IPv6 que encapsula IPv4 (`::ffff:127.0.0.1`).
- Un host de la allowlist que resuelve a una IP pública y a otra privada → `403`.
- Un número de pedido de 16 dígitos que por azar cumple Luhn: falso positivo; por eso existe
  `observar`.
- RUT con y sin puntos (`12.345.678-5`, `12345678-5`) y con `k` minúscula.
- Un parámetro que contiene un secreto del broker en base64: lo detecta E8.
- Cuerpo JSON anidado: se revisan todos los textos, no solo el primer nivel.

## Criterios de éxito
- Ninguna prueba abre red ni resuelve DNS real: transporte y resolutor se reemplazan por dobles.
- Una prueba por cada evasión conocida: las de los casos borde de hosts e IP, *DNS rebinding*
  (primero resuelve a una IP pública y luego a una privada) y cada regla DLP con su variante codificada.
- Las credenciales falsas de las pruebas se arman en tiempo de ejecución (no quedan literales que
  confundan a gitleaks ni al *secret scanning* de GitHub).
- DLP sobre 1 MB en menos de 100 ms en el CI.
- Las 5 capas en verde.

## Supuestos
- El runtime del agente solo alcanza a AgentGuard por la red (p. ej. una red Docker interna). Si el
  agente tiene salida directa a Internet, se salta este módulo. Forzar eso a nivel de red es del
  despliegue, no de esta spec.
- Las herramientas selladas son las acciones del módulo 2: se ejecutan con
  `POST /api/v1/secretos/acciones/{accion}` y se definen en el mismo JSON.
- **Fuera de esta spec:** un servidor MCP completo (JSON-RPC) delante de las acciones, la inspección
  de las respuestas en busca de inyecciones (módulo 4), la aprobación humana (módulo 5) y un DLP con
  modelos (NER) que sume señales.

## Decisiones (D-01 a D-03, antes preguntas abiertas; aprobadas por Alex el 2026-11-25)
- **D-01 → sin allowlist configurada, se bloquea toda salida** (Zero Trust). El broker no sale hasta
  declarar sus hosts. Permitir por defecto los hosts de las acciones dejaría la allowlist sin efecto
  justo cuando nadie la configuró.
- **D-02 → el DLP bloquea por defecto**, con modo `observar` por regla mientras se aclara si un
  hallazgo es un falso positivo. Redactar y enviar igual cambiaría en silencio lo que recibe el
  destino y ocultaría el intento.
- **D-03 → el egreso controlado hacia la web (H4) entra en esta spec**: reutiliza el mismo punto de
  salida y hace aplicable «fuera de la allowlist → 403» a los agentes que navegan.
