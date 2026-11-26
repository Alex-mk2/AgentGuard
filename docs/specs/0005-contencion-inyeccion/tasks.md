# SPEC-0005 — Tareas

| # | Tarea | Archivos | Depende de | Historia | Hecha |
|---|---|---|---|---|---|
| T1 | Saneado y normalización (invisibles, NFKC, homoglifos, tildes, letras sueltas) | `app/inyeccion/normalizar.py` | — | E2, RF-02 | ✅ |
| T2 | Las 7 reglas con prefiltro e índice de frases | `app/inyeccion/reglas.py` | T1 | E2 | ✅ |
| T3 | Envoltorio con id aleatorio y delimitadores falsos neutralizados | `app/inyeccion/envoltorio.py` | — | E3 | ✅ |
| T4 | Inspector: texto o JSON, modos por regla, nivel, sin fragmentos | `app/inyeccion/inspector.py` | T2, T3 | E1, E4, E5, D-01 | ✅ |
| T5 | Configuración `INYECCION_CONFIG` y settings | `app/inyeccion/config.py`, `app/core/config.py` | T4 | RF-01 | ✅ |
| T6 | Sesiones: implícita, explícitas, TTL, topes, falla cerrado | `app/inyeccion/sesiones.py` | — | E6, E9, RF-04 | ✅ |
| T7 | Fachada `Contencion`: autorizar, ingerir, estado, auditoría | `app/inyeccion/contencion.py` | T4–T6 | H2, H3, E12, D-02 | ✅ |
| T8 | Rutas: inspección, sesiones, estado | `app/inyeccion/rutas.py`, `app/main.py` | T7 | E1, E6, E9, E12 | ✅ |
| T9 | Broker: sesión, autorizar, `respuesta: confiable`, ingerir; catálogo filtrado | `app/secretos/{config,broker,rutas}.py` | T7 | E7, E8, E10 | ✅ |
| T10 | Egreso web: sesión, hosts de la sesión, POST con efecto, ingerir | `app/egresos/{web,rutas}.py` | T7 | E7, E8, E11 | ✅ |
| T11 | Pruebas: reglas y evasiones, peor caso, sesiones, punta a punta; arquitectura ampliada | `backend/tests/test_spec0005_*.py`, `test_spec0004_sistema.py` | T1–T10 | todas | ✅ |
| T12 | Frontend: pantalla de contención, módulo 4 activo | `frontend/src/**` | T8 | E13 | ✅ |
| T13 | Ejemplo, `.env.example`, compose, `context.md`, README, `PROGRESS.md`, validación manual | `config/*`, docs | T11, T12 | — | ✅ |

> Ajustes durante la implementación (detalle en el plan, «Desviaciones al implementar»):
> 1. **Rendimiento:** la primera versión tardaba ~200 ms sobre 1 MB de texto común. Se pasó a
>    `bytes.translate` + `split` para las palabras (la expresión `[^a-z0-9]+` costaba 120 ms), tildes
>    con una tabla Latin-1 en vez de NFKD, homoglifos solo si aparece alguno y un índice de frases por
>    sus dos primeras palabras filtrado por el vocabulario del texto: ~88 ms en un equipo con carga.
> 2. **Peor caso:** tres expresiones eran cuadráticas con entradas armadas (comentarios HTML sin
>    cerrar, 78 s; `<img` repetido, 9 s; palabra larguísima tras el nombre de una acción, 5 s). Se
>    reescribieron con recorridos guiados por `find`; ninguna de las 15 entradas de la prueba pasa de
>    0,3 s.
> 3. **Pruebas de SPEC-0003 que cambian a propósito:** tres repetían un `POST` en la misma sesión
>    implícita, que ahora queda contaminada tras la primera respuesta (D-02). Abren una sesión por
>    llamada (`sesion_nueva`), como un runtime con una sesión por tarea, y la de igualdad exacta
>    revisa los campos nuevos (`origen`, `inspeccion`, `marcado`).
> 4. **La prueba manual encontró HTML servido como `text/plain`** (httpbin `/base64`), que se
>    saltaba `iny.oculto`: el atacante elige el `content-type`. `tipo_de` ahora mira también el
>    comienzo del cuerpo.
> 5. **Caracteres invisibles literales en el fuente:** la herramienta de escritura decodificó los
>    escapes `\u200b` y bandit (B613, *Trojan Source*) lo detectó. Se reescribieron como escapes y una
>    búsqueda confirma que no queda ninguno en `app/` ni en `tests/`.
