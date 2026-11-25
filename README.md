# AgentGuard

Proxy/middleware de seguridad que **protege agentes de IA en tiempo de ejecución**, con enfoque
Zero Trust y alineado con el Secure AI Framework (SAIF).

Con los agentes, la superficie de ataque crece: ya no basta con proteger datos, nube, API e
infraestructura, porque el propio modelo puede ser manipulado. El riesgo central es la **Tríada
Letal**: un agente que lee **datos privados**, ingiere **contenido no confiable** y tiene **salida
externa** puede ser llevado por una inyección de prompt a exfiltrar esos datos.

## Módulos
1. **Detector de la Tríada Letal:** revisa el manifiesto de herramientas de un agente y alerta si reúne las tres condiciones.
2. **Secret Broker:** inyecta las credenciales al ejecutar la acción; el modelo nunca ve el secreto.
3. **Sealed Tools y control de egresos (DLP):** herramientas acotadas y bloqueo (403) de cualquier destino fuera de la allowlist.
4. **Contención de prompt injection y rogue actions:** inspección en cada salto y ejecución aislada.
5. **Human-in-the-Loop Gate:** aprobación explícita antes de toda acción irreversible.

## Arquitectura
Monolito: un backend **FastAPI** (Python 3.12) que expone la API en `/api/v1` y sirve el build de
**React + Vite**, empaquetado en **una sola imagen Docker**, sobre **PostgreSQL 16**. Detalle y
reglas en [.claude/context.md](.claude/context.md).

## Cómo trabajamos
- Nada va directo a `main`: rama `feat/`, `fix/`, `docs/` o `chore/` y un PR.
- `main` está protegida: el PR se integra solo con las **5 capas** en verde (`backend-tests`,
  `frontend`, `integracion`, `imagen`, `gitleaks`) y la rama al día con `main`.
- Antes del primer commit en un clon: `pip install pre-commit && pre-commit install`.
- Variables de entorno: copia `.env.example` a `.env` (nunca se versiona).

## Claude Code
Skills del proyecto en `.claude/skills/`: `sdd-feature-workflow`, `sdd-bugfix-workflow`,
`swe-prompt`, `project_memory`, `report-pdf` y `graphify`. Estado del trabajo en
[.claude/PROGRESS.md](.claude/PROGRESS.md).
