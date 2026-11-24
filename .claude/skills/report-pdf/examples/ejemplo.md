---
title: "Informe de ejemplo"
subtitle: "Muestra de todos los componentes de la plantilla, con datos inventados"
category: "Documentación · Ejemplo"
author: "Nombre Apellido"
date: "2026-01-15"
doc_id: "INF-2026-001"
version: "1.0"
classification: "Uso interno"
summary_title: "Resumen ejecutivo"
---

> [!LEAD]
> Este documento muestra cada componente de la plantilla: avisos, indicadores, tablas con estados y anchos de columna, filas de grupo, figuras y saltos de página. Todos los datos son inventados.

```kpis
128 | pruebas ejecutadas
97 % | pruebas en verde | alt
3 | riesgos abiertos
14 días | duración del proyecto
```

## Contexto y alcance

El resumen va antes del primer `##`. Cada `##` abre una página nueva, se numera solo y aparece en el índice con su página.

### Una subsección

Con `###` se marca una subsección dentro de la misma página. Puedes usar **negritas**, _cursivas_, `código` y [enlaces](https://example.com).

- Primer punto de una lista
- Segundo punto
  - Un subpunto

1. Un paso numerado
2. Otro paso

## Avisos y estados

> [!NOTE] Título opcional
> Una nota informativa. Si no pones título, se usa "Nota".

> [!SUCCESS]
> Un resultado positivo.

> [!WARNING]
> Una advertencia.

> [!DANGER]
> Un riesgo o un incumplimiento.

Estados dentro de una tabla, con ancho de columnas definido y una fila de grupo:

<!-- cols: 8,52,20,20 -->
| N° | Requisito | Cumple | Estado |
|:---:|---|:---:|:---:|
| :: Seguridad | | | |
| 1 | Los datos viajan cifrados | [[Sí]] | [[ok:Verificado]] |
| 2 | Hay registro de accesos | [[Parcial]] | [[warn:En curso]] |
| :: Operación | | | |
| 3 | Existe un plan de respaldo | [[No]] | [[bad:Pendiente]] |
| 4 | Se documentó el procedimiento | [[Sí]] | [[info:Revisión]] |

## Código y saltos de página

```bash
node render.js examples/ejemplo.md -o ejemplo.pdf
```

Un salto de página manual sirve para que una tabla larga empiece en una página nueva.

<!-- pagebreak -->

### Después del salto

Este párrafo empieza en una página nueva.

## Fuentes

| Dato | Fuente |
|---|---|
| Resultados de pruebas | Ejecución local del conjunto de pruebas |
| Plazos | Registro del proyecto |
