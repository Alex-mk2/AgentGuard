# Hoja de ruta de specs

> Specs candidatas después de los 5 módulos (SPEC-0001 a SPEC-0006). Autor: Alex · Fecha: 2026-11-28.
> El orden es una recomendación, no un compromiso. El número se asigna al abrir cada spec con el
> flujo `sdd-feature-workflow`; al abrirla o descartarla, se actualiza su fila aquí.

## Etapa 1 — Que AgentGuard proteja agentes reales

| Orden | Spec | Qué resuelve | Tamaño | Origen |
|---|---|---|---|---|
| 1 | **SPEC-0007 — Servidor MCP (JSON-RPC)** | Hoy un agente habla REST con AgentGuard. Con un servidor MCP (Streamable HTTP: `initialize`, `tools/list`, `tools/call`, `ping`), cualquier cliente MCP (Claude Desktop, Claude Code, Cursor o un agente propio) se conecta como a un servidor más, y cada llamada pasa por los 5 módulos. Decisión clave: cómo se ve una aprobación humana dentro de MCP (mantener la llamada abierta, devolver «pendiente» o usar tareas asíncronas). | Medio | SPEC-0004 (catálogo MCP sin ejecución JSON-RPC) |
| 2 | **Despliegue con red aislada** | Un `docker-compose` de ejemplo donde el runtime del agente solo alcanza a AgentGuard por la red. Demuestra que el control de egresos no se puede saltar saliendo directo. | Chico | Supuesto de SPEC-0004 |

## Etapa 2 — Cerrar huecos de seguridad

| Orden | Spec | Qué resuelve | Tamaño | Origen |
|---|---|---|---|---|
| 3 | **Identidad en el dashboard** | Hoy todo usa un único token de administración compartido. Con usuarios reales, cada decisión queda registrada con quién la tomó. Desbloquea la aprobación de a dos, el historial de análisis de la Tríada y el contador de pendientes en el menú. | Medio | SPEC-0006 (fuera de alcance), SPEC-0002 D-03 |
| 4 | **Secret Broker en su propio proceso** | Saca las credenciales de la superficie del resto del monolito. Es la mitigación que de verdad resuelve la concentración de credenciales, el riesgo abierto más serio. | Grande (toca la arquitectura) | Revisión de riesgos del 2026-11-25, opción 6 |
| 5 | **Gestor de secretos externo** | Vault o Secret Manager como nueva `FuenteSecretos`, con credenciales de vida corta. Conviene después de la 4. | Medio | Revisión de riesgos del 2026-11-25, opciones 4 y 5 |

## Etapa 3 — Integración con LLM

Rige la regla de `context.md`: sin IA en las decisiones de seguridad mientras puedan ser
deterministas. Un modelo puede **sumar** señales, nunca **quitarlas**. No tiene herramientas ni
acceso a secretos, devuelve una etiqueta acotada (nunca texto libre que algo ejecute) y, si falla o
responde algo inválido, todo sigue como sin él. Se prefiere un modelo local; una API externa es
opcional y explícita, porque envía a un tercero el contenido que leyó el agente.

| Orden | Spec | Qué resuelve | Tamaño | Origen |
|---|---|---|---|---|
| 6 | **Agente de referencia con LLM y batería de ataques** | Un agente real conectado por MCP que lee la web, crea issues y publica, más inyecciones armadas en páginas, respuestas de APIs y documentos. Demuestra de punta a punta que la sesión se contamina, que la acción pide aprobación y que el secreto nunca llega al modelo. Requiere la SPEC-0007. | Medio | — |
| 7 | **LLM como segunda opinión** | Primero en la Tríada: clasificar las herramientas que las reglas no reconocen (solo puede agregar patas). Después en Inyección: marcar contenido que las reglas no vieron (nunca limpia una sesión contaminada). Opcional: un resumen para quien aprueba, rotulado como opinión del modelo. | Medio | SPEC-0002 D-02 |

## Para más adelante

| Spec | Qué resuelve | Origen |
|---|---|---|
| Sandbox de ejecución de código | Ejecutar código del agente en un servicio aparte, sin el socket de Docker en AgentGuard. Grande y de riesgo alto. | SPEC-0005 D-03 |
| Sesiones en Postgres | Que las sesiones sobrevivan a un reinicio; hoy viven en memoria y lo desconocido falla cerrado. | SPEC-0005 RF-04 |
| Aprobar con un clic desde la notificación | Callback firmado desde el canal de aviso. Conviene después de la identidad (3). | SPEC-0006 (fuera de alcance) |
| CD | Despliegue automático desde `main`, cuando el flujo de CI esté internalizado. | Fundación |
