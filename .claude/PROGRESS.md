# AgentGuard — Bitácora de trabajo

> Estado volátil del proyecto. Arquitectura estable → CLAUDE.md / context.md. Estructura de
> código → `graphify query`. Esta bitácora → en qué vamos y por qué.

## Estado actual
- `chore/fundacion` mergeada (#1, integrada por Alex) — base del repo tomada de CondorForge: skills, hooks, gitleaks, CI con las 5 capas, Dependabot y protección de `main`. — Alex, 2026-11-24
- `docs/que-es-agentguard` mergeada (#2, integrada por Alex) — qué es AgentGuard y sus 5 módulos en `context.md` §1 y el README. — Alex, 2026-11-25
- `feat/esqueleto-monolito` mergeada (#3, integrada por Alex) — [SPEC-0001](../docs/specs/0001-esqueleto-monolito/spec.md): `crear_app`, health/readiness, errores 503/500 + `id_error`, pool de Postgres, página de estado en React + TypeScript, Dockerfile multi-etapa y compose. Las 5 capas dejaron de omitirse. — Alex, 2026-11-25
- `feat/contencion-inyeccion` (Alex) — [SPEC-0005](../docs/specs/0005-contencion-inyeccion/spec.md), módulo 4: una sesión que ingirió contenido no confiable (web, respuesta de una acción, memoria, otro agente) pierde las acciones con efecto, se detecte o no la inyección (D-02); inspección determinista que solo marca por defecto (D-01), quita invisibles y envuelve; sesiones por `X-AgentGuard-Sesion`, implícita por agente, id desconocido → 409 (falla cerrado). Sandbox de código fuera (D-03). PR abierto, 5 capas en local en verde y 17/17 casos manuales con red real. — Alex, 2026-11-26
- `feat/sealed-tools` mergeada (#7, integrada por Alex) — [SPEC-0004](../docs/specs/0004-sealed-tools-egresos/spec.md), módulo 3: `app/egresos` es la única salida de red (allowlist → DLP → solo IP públicas → conexión a la IP verificada); sin `EGRESOS_CONFIG` no sale nada (D-01); DLP bloquea por defecto con modo observar (D-02); egreso web por agente (D-03); acciones sin credencial y catálogo MCP. Nuevo paquete compartido `app/agentes`. — Alex, 2026-11-25
- `feat/secret-broker` mergeada (#6, integrada por Alex) — [SPEC-0003](../docs/specs/0003-secret-broker/spec.md), módulo 2: el agente pide una acción y AgentGuard inyecta la credencial; el modelo nunca la ve. Mitigaciones del riesgo de concentración: tokens de alcance mínimo con aviso de compartidos, límite por agente, sin core dumps, no dumpable, solo lectura y sin capabilities. Probado con la imagen endurecida contra httpbin real: la cabecera reflejada llega como `[SECRETO]`, 0 apariciones en respuesta y logs. — Alex, 2026-11-25
- `docs/readme-diagramas` mergeada (#5, integrada por Alex) — README pensado para el repo público: la Tríada Letal, los módulos y su estado, arquitectura, flujo del detector con ejemplo real, puesta en marcha y CI, con 5 diagramas Mermaid (validados con el parser de mermaid 11). Sale «Cómo trabajamos» y «Claude Code»: eso vive en `context.md`. Al terminar cada módulo, actualizar su fila y los diagramas. — Alex, 2026-11-25
- `feat/detector-triada` mergeada (#4, integrada por Alex) — [SPEC-0002](../docs/specs/0002-detector-triada/spec.md), módulo 1: `POST /api/v1/triada/analisis` (MCP `tools/list` y formato propio), 23 reglas por palabras con evidencia, peor caso para lo sin clasificar, tope global de 1 MB y pantalla `/modulos/triada`. Probado con la imagen: los 6 manifiestos de referencia, 422/413, y servidores MCP reales (filesystem → baja, fetch → media, juntos → crítica). — Alex, 2026-11-25

## Decisiones
- 2026-11-25 — AgentGuard pasa a **público**. Por qué: en repos públicos Actions no consume la cuota de minutos, y el proyecto sirve de portafolio. Antes se revisó el historial: gitleaks sin hallazgos; el correo USACH de 6 commits ya era público en otros 12 repos de cursos, así que no se reescribió el historial; los commits nuevos usan el correo noreply (config local del repo). Las menciones técnicas a CondorForge se dejan (CondorForge sigue privado). Se activaron el escaneo de secretos y la push protection de GitHub. — Alex
- 2026-11-25 — CI y Secretos solo en PR, con `concurrency` que cancela la corrida vieja del mismo PR; igual que CondorForge (#98). Por qué: aviso de 2.700 de 3.000 minutos de Actions usados en la cuenta (cuota compartida con CondorForge y OptiVeil-v2), y ~40 % se iba en repetir el CI tras el merge, cuando `main` exige la rama al día y no admite push directo. Antes de cada push se corren las 5 capas en local. — Alex
- 2026-11-24 — Monolito: FastAPI sirve la API y el build de React en una sola imagen, con PostgreSQL. Por qué: un solo despliegue y un solo pipeline bastan para el tamaño del proyecto; los módulos por dominio dejan el corte hecho si algún día hay que separar. — Alex
- 2026-11-25 — AgentGuard es un proxy/middleware de seguridad para agentes de IA (SAIF, Tríada Letal), separado de OptiVeil v2, que se queda con infraestructura, redes y postura cloud. Por qué: son dos superficies de ataque distintas. Los controles de Google Cloud se construyen como equivalentes propios. — Alex
- 2026-11-24 — Mismas 5 capas y misma protección de `main` que CondorForge. Por qué: es el flujo ya probado allá. — Alex
- 2026-11-26 — Módulo 4: la garantía es la contención por origen, no la detección; las reglas solo marcan por defecto y las respuestas de acciones contaminan salvo `respuesta: confiable`. Por qué: una inyección reescrita esquiva cualquier regla, y un clasificador con LLM es atacable igual (SPEC-0005 D-01, D-02). — Alex
- 2026-11-25 — La prueba de rendimiento de SPEC-0002 (500 herramientas < 200 ms) solo exige el tiempo en el CI. Por qué: en local con Docker y CondorForge corriendo varió entre 190 y 380 ms en corridas seguidas; una prueba que falla al azar es peor que no tenerla. — Alex

## Pendientes
- [ ] Spec futura: historial de análisis de la Tríada (exige autenticación y retención; SPEC-0002 D-03).
- [ ] Idea futura: modelo local como segunda opinión del Detector, que solo pueda sumar patas (SPEC-0002 D-02).
- [ ] Spec futura: separar el Secret Broker en un proceso propio, sin la superficie del resto (opción 6 de la revisión de riesgos del 2026-11-25; la que resuelve la concentración de credenciales).
- [ ] Spec futura: gestor de secretos externo (Vault / Secret Manager) y credenciales de vida corta como nuevas `FuenteSecretos` (opciones 5 y 4).
- [ ] Chore futuro: imagen sin shell (base distroless) y verificaciones de la capa `imagen` sin `docker exec … test`.
- [ ] CD (despliegue automático desde `main`) cuando el flujo de CI esté internalizado.
- [ ] Spec futura: servidor MCP completo (JSON-RPC) delante de las herramientas selladas; hoy hay catálogo MCP y ejecución por REST (SPEC-0004).
- [ ] Ejemplo de despliegue donde el runtime del agente solo alcanza a AgentGuard por la red (supuesto de SPEC-0004).
- [ ] Spec futura: sandbox de ejecución de código como servicio aparte, sin el socket de Docker en AgentGuard (SPEC-0005 D-03).
- [ ] Módulo 5 (Human-in-the-Loop): convertir el `403` de sesión contaminada en una solicitud de aprobación (SPEC-0005 E8).
- [ ] Idea futura: persistir sesiones en Postgres; hoy viven en memoria y lo desconocido falla cerrado (SPEC-0005 RF-04).

## Trampas conocidas
- La herramienta de escritura de archivos decodifica los escapes `\uXXXX`: un `"\u200b"` termina como el carácter invisible literal en el fuente (bandit B613, *Trojan Source*). Para caracteres invisibles o ambiguos, usar `chr()` o reescribir con un script que emita `\\u`; después buscarlos en los archivos cambiados. — Alex, 2026-11-26
- Toda expresión regular que corre sobre contenido de un agente se prueba contra entradas armadas de 1 MB (`test_spec0005_peor_caso_acotado`): `<!--(.*?)-->`, `<img[^>]{0,1000}?…` y `[a-z._-]{1,127}[({]` eran cuadráticas (de 5 a 78 s). Preferir recorridos guiados por `find`. — Alex, 2026-11-26
- En Windows, `Path.write_text` escribe CRLF; con `core.autocrlf=true` git lo normaliza al hacer commit, así que el diff no cambia. — Alex, 2026-11-26
- Git Bash altera las barras invertidas de los heredocs: un `\\1` de una regex terminó como el carácter 0x01 y un `\\b` como 0x08. Para editar con scripts, escribir el `.py` con la herramienta de archivos y correrlo; después buscar caracteres de control. — Alex, 2026-11-25
- En `re` de Python, una alternativa con `\b` o un `(?:\d[ -]?){12,18}` sobre 1 MB cuesta cientos de ms: prefiltrar con `in` y usar formatos concretos (ver `app/egresos/dlp.py`). — Alex, 2026-11-25
- `httpx.Response(content=...)` en `MockTransport` llega ya leída: `aiter_raw()` lanza `StreamConsumed`. Usar `aiter_bytes()`, que además descomprime (necesario para limpiar secretos). — Alex, 2026-11-25
- Bandit lee como ids de prueba las palabras escritas después de `# nosec`: el motivo va en la línea de arriba. — Alex, 2026-11-25
- En Windows, `StaticFiles` entrega la ruta con `\`: para saber si una ruta es de la API se mira `scope["path"]`, no el `path` del método (lo detectó `test_spec0001_e10_api_gana_al_frontend`). — Alex, 2026-11-25
- `FRONTEND_DIST=` vacío en el `.env` apunta a la carpeta actual: déjalo comentado si no lo usas.
- Puertos en el equipo de Alex: 5432 = PostgreSQL instalado, 5433 = Postgres de CondorForge, 8000 = uvicorn de CondorForge en desarrollo. AgentGuard publica Postgres en el **5434** (`POSTGRES_PUERTO`) y la app en `APP_PUERTO` (8000 por defecto; usar otro si CondorForge está corriendo). — Alex, 2026-11-25
- `docker compose build` falla en Git Bash con «failed to execute bake: exit status 1»; en PowerShell funciona. Desde Git Bash: `docker build -t agentguard-app .` y luego `docker compose up -d --no-build`. — Alex, 2026-11-25
- Reglas de la Tríada: una palabra exacta siempre calza (`drive_car` → P-NUBE). Es la limitación conocida de las reglas por palabras; se corrige declarando las patas en el formato propio. Al sumar una regla, sumar su caso en `test_spec0002_reglas.py` (una prueba lo exige). — Alex, 2026-11-25
