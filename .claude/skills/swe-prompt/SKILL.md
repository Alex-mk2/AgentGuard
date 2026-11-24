---
name: swe-prompt
description: Úsala cuando alguien envía un pedido corto, vago o sin contexto para implementar una funcionalidad, corrección o cambio. Antes de tocar código, saca a la luz la intención de negocio, el impacto técnico, los casos borde y los criterios de aceptación.
---

# Prompt de ingeniería: de pedido vago a pedido implementable

## Idea central

Los pedidos suelen ser cortos y omiten consideraciones técnicas. Esta skill los convierte en un pedido estructurado y listo para implementar, sin exigirle a quien lo escribió que sepa de ingeniería.

**Nunca implementes desde un pedido ambiguo. Primero aclara, después construye.**

## Cuándo usarla

- El pedido tiene menos de 3 o 4 frases.
- Describe el resultado, pero no las restricciones ni los casos borde.
- No dice qué parte del sistema se toca.
- No hay criterios de aceptación, o son vagos ("que funcione bien", "que no falle").

No la omitas porque el pedido parezca simple: lo que parece simple suele esconder complejidad.

## Proceso

### Paso 1. Extraer la intención

Identifica, a partir del pedido:

- **Por qué:** qué quiere lograr realmente el negocio o el usuario.
- **Estado actual:** cómo se comporta hoy.
- **Estado deseado:** cómo debería comportarse.

Lo que falte pasa a las preguntas.

### Paso 2. Preguntas de aclaración (máximo 5)

Pregunta solo lo que no puedas inferir. En este orden de prioridad:

1. **Objetivo:** ¿por qué hay que cambiarlo?
2. **Alcance:** ¿qué usuarios, roles o contextos se ven afectados?
3. **Casos borde:** ¿qué debe pasar cuando algo falla o falta?
4. **Cómo se sabe que funciona:** ¿qué resultado verifica el equipo?
5. **Restricciones:** plazos, dependencias y lo que no debe cambiar.

Preséntalas como lista numerada y **espera las respuestas** antes de seguir.

### Paso 3. Mapear el impacto técnico

Con las respuestas, identifica:

- Qué capas o módulos del sistema se tocan.
- Qué servicios, repositorios o modelos intervienen.
- Qué podría romperse: endpoints existentes, consultas, integraciones externas.
- Si hacen falta migraciones, datos iniciales o cambios de documentación.
- Si el cambio introduce violaciones de diseño, o si un patrón conocido encaja.

Cuando se lo muestres a quien pidió el cambio, tradúcelo a lenguaje que pueda validar.

### Paso 4. Reformular el pedido

Entrega esta plantilla:

```
## Objetivo
[Meta de negocio en una frase]

## Contexto
[Comportamiento actual y restricciones relevantes]

## Cambios esperados
[Cambios concretos y observables, en viñetas]

## Criterios de aceptación
- [ ] [Condición verificable 1]
- [ ] [Condición verificable 2]
- [ ] [Condición verificable 3]

## Impacto técnico
- Capas o módulos afectados: [lista]
- Modelos o servicios: [lista]
- Riesgos posibles: [lista]
- Requiere migración: sí / no
```

### Paso 5. Confirmar antes de implementar

Muestra el pedido reformulado y pregunta: "¿Implementamos con este enfoque o hay algo que ajustar?"

**No empieces a implementar hasta que la persona confirme de forma explícita.**

## Errores comunes

| Error | Cómo evitarlo |
|---|---|
| Hacer más de 5 preguntas | Infiere lo que puedas; pregunta solo lo que bloquea |
| Implementar antes de la confirmación | Espera la aprobación explícita del pedido reformulado |
| Describir el impacto con jerga | Tradúcelo a algo que la persona pueda validar |
| Criterios de aceptación vagos | Cada criterio debe poder comprobarse: "el usuario ve X", no "funciona bien" |
| Saltarse la evaluación de diseño | El paso 3 la incluye aunque la respuesta sea "no aplica" |

## Ejemplo

**Pedido original:**

> "Quiero que cuando un pedido se cancele, no aparezca en el listado del cliente."

**Preguntas:**

1. ¿"Cancelado" es un estado concreto del sistema o hay otros nombres (anulado, inactivo)?
2. ¿Aplica solo al listado principal o también a reportes y exportaciones?
3. ¿Algún rol (por ejemplo, administración) debería seguir viéndolos?
4. ¿Se oculta solo en pantalla o se excluye desde la consulta?

**Pedido reformulado:**

```
## Objetivo
Excluir los pedidos cancelados del listado de pedidos de un cliente.

## Contexto
Hoy el listado devuelve todos los pedidos sin filtrar por estado, y los cancelados
aparecen mezclados con los activos.

## Cambios esperados
- El listado excluye los pedidos cancelados por defecto
- El total no cuenta los cancelados
- Administración puede verlos con un parámetro explícito

## Criterios de aceptación
- [ ] El listado no devuelve pedidos con estado "cancelado"
- [ ] El total refleja solo los pedidos no cancelados
- [ ] Con el parámetro explícito se devuelven todos, sin importar el estado
- [ ] Las pruebas existentes del listado siguen pasando

## Impacto técnico
- Capas afectadas: controlador del listado y repositorio de pedidos
- Modelos o servicios: Pedido, repositorio de pedidos
- Riesgos posibles: pruebas que asuman que se ven todos los pedidos
- Requiere migración: no
```
