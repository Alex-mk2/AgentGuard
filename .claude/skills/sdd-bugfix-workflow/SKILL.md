---
name: sdd-bugfix-workflow
description: Corrige errores con un enfoque basado en evidencia: análisis de causa raíz (RCA), validación de impacto y pruebas de regresión. Úsala siempre que se reporte un bug, una falla, un comportamiento inesperado, una excepción o un problema en producción o desarrollo ("hay un bug en X", "esto falla cuando Y", "corrige el error Z", "algo está roto"). Nunca modifica código sin validar antes una hipótesis de causa raíz y recibir aprobación explícita.
---

# Corrección de bugs basada en evidencia

El objetivo es resolver la **causa raíz** con el **menor cambio posible**, sin regresiones y con trazabilidad.

## Flujo

### Fase 1. Analizar el reporte

Revisa todo lo disponible: descripción, comportamiento actual frente al esperado, logs, trazas de error, capturas y comentarios.

Clasifica el diagnóstico:

- **Conocido:** hay una traza con una línea concreta, una causa evidente o una condición de reproducción clara. No investigues a fondo: pasa a validar la hipótesis.
- **Incierto:** error genérico, comportamiento intermitente, varias causas posibles o evidencia insuficiente. Investiga (Fase 3).

### Fase 2. Reproducir

Intenta reproducir el problema y documenta los pasos, las condiciones y el resultado observado.

Si no puedes reproducirlo: pide más información, detén el flujo y **no modifiques código**.

### Fase 3. Determinar la causa raíz

- **Causa ya identificada:** valida la hipótesis leyendo el código afectado y confirmando que coincide con el reporte.
- **Causa desconocida:** investiga los flujos involucrados, las dependencias, los logs, la configuración y el historial reciente de cambios. Usa herramientas de depuración solo cuando aporten valor real.

Documenta la causa raíz, los componentes afectados y los riesgos.

### Fase 4. Presentar el RCA

Entrega al usuario:

1. Resumen del problema
2. Pasos de reproducción
3. Causa raíz
4. Componentes afectados
5. Estrategia de corrección propuesta
6. Riesgos

**Espera aprobación explícita antes de modificar cualquier archivo.**

### Fase 5. Plan de corrección

Define los archivos afectados, los cambios necesarios, cómo se validará y, si aplica, cómo se revierte.

### Fase 6. Implementar

Haz **solo** los cambios necesarios para resolver la causa raíz. Evita refactors ajenos, mejoras cosméticas y cambios de arquitectura innecesarios.

### Fase 7. Pruebas

1. **Ejecuta la suite completa** con el comando de pruebas del proyecto y distingue:
   - pruebas que fallaban antes y ahora pasan: comportamiento correcto;
   - pruebas que pasaban y ahora fallan: posible regresión. Si aparecen fallas nuevas ajenas al bug, detente e investiga.
2. **Clasifica las pruebas afectadas:**

   | Tipo | Señal | Acción |
   |---|---|---|
   | Regresión introducida | Pasaba antes y falla tras el cambio | Corrige el cambio, no la prueba |
   | Prueba del comportamiento erróneo | Afirmaba el comportamiento incorrecto | Actualízala al comportamiento correcto |

   Nunca borres una prueba que falla sin entender por qué falla.
3. **Agrega una prueba de regresión** que reproduzca la condición exacta del bug y falle si se revierte el cambio. Nómbrala por el escenario que cubre.
4. Comprueba que existan pruebas para el caso que causaba el bug, el caso normal y los bordes que salieron en el análisis.

### Fase 8. Validar

Confirma que el bug desaparece, que se cumple el comportamiento esperado, que todas las pruebas pasan y que no aparecen errores secundarios. Verifica también los criterios de aceptación del ticket.

### Fase 9. Definición de terminado

- [ ] Bug corregido
- [ ] Causa raíz documentada
- [ ] Pruebas agregadas o actualizadas, y en verde
- [ ] Sin regresiones
- [ ] Alcance controlado
- [ ] Listo para revisión

## Entregables

**Antes de implementar:** resumen del problema, pasos de reproducción, causa raíz, estrategia y riesgos.

**Después de implementar:** cambios realizados, archivos modificados, pruebas agregadas o actualizadas, evidencia de validación, riesgos residuales y confirmación de la definición de terminado.

## Reglas

- No implementes sin entender el problema.
- No modifiques código sin una hipótesis de causa raíz validada.
- No corrijas solo el síntoma.
- No hagas refactors ajenos al bug.
- Si no se puede reproducir o falta información crítica, detente y pregunta.
- Prioriza la estabilidad y la seguridad sobre la velocidad.
