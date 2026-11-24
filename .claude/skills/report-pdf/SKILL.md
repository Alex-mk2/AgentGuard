---
name: report-pdf
description: Genera informes PDF A4 con una plantilla única a partir de Markdown con front-matter. Úsala cuando pidan un informe, reporte, documento entregable o "PDF con formato", o cuando quieras convertir un análisis o una investigación en un documento para compartir. Incluye portada, resumen con índice, avisos, indicadores, tablas con estados y verificación del PDF.
---

# Informes PDF desde Markdown

Estructura de "sistema de diseño + plantilla + renderizador": el contenido se escribe en Markdown y toda la presentación vive en una sola plantilla. El PDF se genera con Chrome o Edge sin interfaz, así que no hay diálogo de impresión, ni encabezados del navegador, ni rutas locales en el pie.

## Archivos

| Ruta | Para qué |
|---|---|
| `render.js` | Markdown → HTML → PDF, con índice en dos pasadas y verificación |
| `templates/report.css` | **Única fuente de estilos**: colores y tipografía en `:root`, página A4, portada, tablas, avisos, indicadores y estados |
| `templates/report-template.html` | Estructura: portada, resumen con índice y cuerpo |
| `examples/ejemplo.md` | Muestra de todos los componentes, con datos inventados |

## Requisitos

- Node.js y `npm install` dentro de esta carpeta (una sola vez).
- Chrome o Edge instalado. Si no se encuentra, define `REPORT_PDF_BROWSER` con la ruta del ejecutable.
- Poppler (`pdftotext` y `pdffonts`): se usa para poner los números de página en el índice y para verificar el PDF. Sin él, el índice sale sin números y la verificación falla; usa `--skip-verify` solo en ese caso y avísalo al entregar.

## Cómo generar un informe

1. Escribe el `.md` **fuera de esta carpeta**: los datos de cada informe no viven en la skill. Copia `examples/ejemplo.md` como punto de partida.
2. Renderiza:
   ```bash
   node render.js <informe.md> -o <salida.pdf>
   ```
   Opciones: `--html <archivo.html>` guarda el HTML intermedio para depurar; `--skip-verify` omite la verificación.
3. **Revisa el PDF visualmente, página por página**, antes de entregarlo. La verificación automática no detecta problemas de diseño.
4. Al entregar, indica cuántas páginas tiene y qué se verificó.

## Front-matter

Obligatorios: `title`, `author`, `date` (`YYYY-MM-DD`, una fecha real; se muestra como `DD-MM-YYYY`).

Opcionales: `subtitle`, `category`, `doc_id` (código libre, por ejemplo `INF-2026-001`), `version`, `classification` y `summary_title` (por defecto "Resumen").

El renderizador rechaza el documento si falta un campo obligatorio, si la fecha no es válida o si algún campo contiene algo que parece una ruta local.

## Convenciones de Markdown

- **Antes del primer `##`** va el resumen: queda en la página 2, junto al índice. Suele llevar un aviso `[!LEAD]` y un bloque `kpis`.
- **Cada `##` abre una página nueva**, se numera solo y aparece en el índice con su página. `###` marca una subsección dentro de la misma página.
- **Avisos:**
  ```markdown
  > [!LEAD]            → párrafo de apertura destacado
  > [!NOTE] Título     → nota (título opcional; por defecto "Nota")
  > [!SUCCESS]         → resultado positivo
  > [!WARNING]         → advertencia
  > [!DANGER]          → riesgo o incumplimiento
  ```
- **Indicadores:** un bloque de código `kpis` con entre 1 y 6 líneas `valor | etiqueta`. Agregar `| alt` pone el borde superior en verde.
- **Estados** en tablas o texto: `[[Sí]]`, `[[Parcial]]`, `[[No]]` y `[[ok:texto]]`, `[[warn:texto]]`, `[[bad:texto]]`, `[[info:texto]]`. Cualquier otro valor da error.
- **Ancho de columnas:** `<!-- cols: 8,52,20,20 -->` en la línea anterior a la tabla. Los números son proporciones.
- **Fila de grupo en una tabla:** la primera celda empieza con `::`, por ejemplo `| :: Seguridad | | |`.
- **Salto de página manual:** `<!-- pagebreak -->`.
- **Capturas:** HTML en bloque, sin líneas en blanco dentro, con la imagen embebida como `data:` URI (nunca una ruta de archivo):
  ```html
  <div class="figs" style="--fig-cols:2; --fig-h:120mm"><figure><img src="data:image/png;base64,…" alt="…"><figcaption>Pie</figcaption></figure></div>
  ```

## Reglas

- **Nunca rutas locales** en el contenido, en los metadatos ni en el pie. El renderizador lo verifica y falla con código 2 si las encuentra.
- **Fuentes embebidas:** el renderizador lo comprueba con `pdffonts`.
- **No imprimas desde el navegador:** usa siempre `render.js`.
- **Cada cifra del informe debe poder rastrearse** a una consulta o a una fuente; las fuentes van en la última sección.
- **Cambios de estilo:** edita solo `templates/report.css` y vuelve a generar el ejemplo para revisarlos.

## Problemas conocidos

- **Una tabla deja una o dos filas solas en otra página:** acorta los textos de las celdas, ajusta `cols` o pon un salto de página antes de la tabla.
- **Aviso "no ubiqué la página de…":** el título del `##` tiene un formato raro (enlaces, emojis o saltos de línea). Simplifícalo.
- **No encuentra el navegador:** define `REPORT_PDF_BROWSER`.
- **Códigos de salida:** 0 correcto · 1 uso o validación · 2 verificación fallida · 3 error de render.
