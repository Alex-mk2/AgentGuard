---
name: sdd-feature-workflow
description: Implementa funcionalidades nuevas con Desarrollo Guiado por Especificación (SDD): especificación, plan, tareas, implementación, pruebas y validación, con una aprobación explícita entre fases. Úsala cuando se pida una funcionalidad, módulo o componente nuevo ("quiero agregar X", "implementa la funcionalidad Y", "desarrolla el módulo Z") en un proyecto que use GitHub Spec Kit o que acepte specs, plan y tareas versionados. No saltes fases ni implementes sin spec y plan aprobados.
---

# Funcionalidades con Desarrollo Guiado por Especificación

Evita la implementación prematura y deja trazabilidad completa: requisito, especificación, plan, tareas, código y pruebas.

**Nunca avances de fase sin aprobación explícita de la persona.**

## Antes de empezar

- Crea la rama de la funcionalidad **antes de editar nada**; no trabajes sobre la rama que esté activa.
- Si el proyecto usa GitHub Spec Kit, usa sus comandos en cada fase (`specify`, `plan`, `tasks`, `implement`). Si un comando no está disponible, detén el flujo e informa. Si el proyecto no usa Spec Kit, escribe los mismos documentos a mano en una carpeta `specs/<número>-<nombre>/`.

## Fases

### Fase 1. Especificación

1. Genera la especificación: historias de usuario con prioridad, escenarios de aceptación, casos borde, requisitos funcionales verificables, criterios de éxito medibles y supuestos.
2. Marca como pregunta abierta lo que cambie el alcance y no tenga un valor razonable por defecto (máximo 3).
3. Presenta la especificación. **Espera aprobación.**

### Fase 2. Plan

1. Genera el plan: contexto técnico, estructura de código, decisiones con su justificación y alternativas, modelo de datos, contratos de interfaz y guía de validación.
2. Revisa las reglas del proyecto (convenciones, arquitectura, seguridad) y justifica cualquier excepción.
3. Presenta el plan. **Espera aprobación.**

### Fase 3. Tareas

1. Genera las tareas ordenadas por historia de usuario, cada una con su ruta de archivo y sus dependencias.
2. Analízalas e identifica: dependencias, bloqueos, omisiones, tareas demasiado grandes para dividir y tareas que pueden ir en paralelo.
3. Entrega la ruta del archivo de tareas. **Espera aprobación.**

### Fase 4. Implementación

Implementa las tareas en orden, fase por fase, y marca cada una como hecha al terminarla. Las tareas que tocan el mismo archivo van en secuencia.

### Fase 5. Pruebas

1. **Identifica las pruebas existentes** que cubren el código modificado, antes de ejecutar nada.
2. **Ejecuta la suite completa** con el comando de pruebas del proyecto y clasifica cada falla:

   | Tipo de falla | Señal | Acción |
   |---|---|---|
   | Regresión | La prueba cubría algo que no debía cambiar | Corrige la implementación, no la prueba |
   | Cambio intencional | La prueba afirmaba el comportamiento que la funcionalidad reemplaza | Actualiza la prueba y deja un comentario corto |

   Nunca elimines una prueba que falla sin entender por qué falla.
3. **Agrega pruebas nuevas:** casos felices, casos borde de la especificación y casos de error esperados.
4. No marques ninguna tarea como terminada si hay pruebas fallando.

### Fase 6. Validación

Comprueba que se cumplen **todos** los criterios de aceptación, que todas las pruebas pasan, que no hay errores de compilación ni advertencias críticas, y que no quedan pendientes sin resolver.

### Fase 7. Definición de terminado y reporte

Verifica la definición de terminado del proyecto y genera el reporte:

```
REPORTE DE VALIDACIÓN

Criterios de aceptación:
✅ [criterio 1]
✅ [criterio 2]

Pruebas:
✅ [suite o caso]

Riesgos:
⚠️ [riesgo identificado, si aplica]

Notas:
[observaciones]
```

## Reglas

- No implementes antes de que se apruebe la especificación y el plan.
- No te saltes ninguna fase.
- No asumas comportamiento implícito: todo debe estar especificado.
- Genera las pruebas antes de cerrar cada tarea.
- Ante un requisito ambiguo: detente, haz preguntas concretas y espera la respuesta.

## Riesgos que debes evaluar siempre

| Categoría | Qué revisar |
|---|---|
| Técnico | Complejidad, deuda técnica, dependencias externas |
| Rendimiento | Latencia, volumen, consumo de recursos |
| Seguridad | Superficies de ataque, autenticación, datos sensibles |
| Mantenibilidad | Legibilidad, cobertura de pruebas, documentación |
