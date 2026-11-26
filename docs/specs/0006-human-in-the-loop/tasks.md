# SPEC-0006 — Tareas

| # | Tarea | Archivos | Depende de | Historia | Hecha |
|---|---|---|---|---|---|
| T1 | Consultas y migraciones en la base; la imagen copia `db/` | `app/base/{conexion,migraciones}.py`, `db/postgres/001_aprobaciones.sql`, `Dockerfile` | — | D-01 | ✅ |
| T2 | Configuración `APROBACION_CONFIG`, huella canónica y modelos | `app/aprobacion/{config,huella,modelos}.py`, `app/core/config.py` | — | RF-01, RF-04 | ✅ |
| T3 | `Almacen`: Postgres y doble en memoria con el mismo contrato | `app/aprobacion/almacen.py`, `tests/dobles/aprobaciones.py` | T1, T2 | E4, E8, E11, E14, RF-02 | ✅ |
| T4 | `Puerta`: exigir, decidir, consultar, listar, cancelar, notificar, estado | `app/aprobacion/puerta.py` | T3 | H1–H5 | ✅ |
| T5 | Contención: `Contenida` con motivo, señales por sesión, aviso al cerrar | `app/inyeccion/{contencion,sesiones}.py` | — | E5, E11 | ✅ |
| T6 | `Accion.aprobacion`, `Agente.web_aprobacion` y su validación | `app/secretos/config.py`, `app/agentes/modelo.py` | — | E1, E2 | ✅ |
| T7 | `salida.revisar` (allowlist + DLP sin enviar) | `app/egresos/salida.py` | — | E3 | ✅ |
| T8 | Broker: motivo, revisar, puerta, boleto; notificación interna | `app/secretos/{broker,rutas}.py` | T4–T7 | E1, E3, E8, E13 | ✅ |
| T9 | Egreso web: lo mismo para `POST` | `app/egresos/{web,rutas}.py` | T4, T5, T7 | E2, E3, E8 | ✅ |
| T10 | Rutas del módulo y armado en `main` | `app/aprobacion/rutas.py`, `app/main.py` | T4, T8, T9 | E5, E6, E10, E15 | ✅ |
| T11 | Pruebas unitarias, de arquitectura y cambios intencionales de SPEC-0005 | `tests/test_spec0006_*.py`, `test_spec0004_sistema.py`, `test_spec0005_api.py` | T1–T10 | todas | ✅ |
| T12 | Pruebas de integración contra Postgres | `tests/test_spec0006_integracion.py` | T3 | D-01, E8 | ✅ |
| T13 | Pantalla `/modulos/aprobacion` con lógica probada | `frontend/src/{aprobacion,aprobacion.test}.ts`, `src/paginas/Aprobacion.tsx` | T10 | E7, E15 | ✅ |
| T14 | Ejemplos, compose, README y bitácora | `config/*.ejemplo.json`, `docker-compose.yml`, `README.md`, `.claude/PROGRESS.md`, `context.md` | T1–T13 | — | ✅ |
