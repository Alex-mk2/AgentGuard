#!/usr/bin/env node
/**
 * report-pdf · Markdown con front-matter -> PDF A4 con una plantilla única.
 *
 * Uso:
 *   node render.js <entrada.md> [-o salida.pdf] [--html salida.html] [--skip-verify]
 *
 * Flujo:
 *   1. Valida el front-matter (título, autor y fecha YYYY-MM-DD real).
 *   2. Convierte el Markdown con las convenciones de la plantilla (ver SKILL.md).
 *   3. Renderiza con Chrome o Edge instalado (puppeteer-core) en dos pasadas:
 *      la primera ubica en qué página cae cada sección para armar el índice.
 *   4. Verifica el PDF (sin rutas locales, fuentes embebidas) en una carpeta
 *      temporal y solo entonces lo copia al destino.
 *
 * Códigos de salida: 0 ok · 1 uso o validación · 2 verificación fallida · 3 error de render.
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const matter = require('gray-matter');
const { Marked } = require('marked');
const puppeteer = require('puppeteer-core');

const ROOT = __dirname;
const REQUIRED = ['title', 'author', 'date'];
const BROWSERS = [
  process.env.REPORT_PDF_BROWSER,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].filter(Boolean);
// Rutas locales que nunca deben aparecer en un documento que se comparte.
const LOCAL_PATH_RE = /(file:\/\/|\b[A-Za-z]:[\\/]|[\\/]Users[\\/]|[\\/]home[\\/][a-z]|AppData)/i;

class UsageError extends Error {}
class VerifyError extends Error {}

// ---------------------------------------------------------------- utilidades
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const norm = (s) => String(s).normalize('NFC').replace(/\s+/g, ' ').trim().toLowerCase();

function hasTool(cmd) {
  try {
    execFileSync(cmd, ['-v'], { stdio: 'ignore' });
    return true;
  } catch (e) {
    // Algunas versiones de poppler devuelven un código distinto de 0 con -v: existen igual.
    return Boolean(e && e.status !== undefined && e.code !== 'ENOENT');
  }
}

function parseArgs(argv) {
  const args = { input: null, output: null, html: null, skipVerify: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-o' || a === '--out') args.output = argv[++i];
    else if (a === '--html') args.html = argv[++i];
    else if (a === '--skip-verify') args.skipVerify = true;
    else if (a.startsWith('-')) throw new UsageError(`Opción desconocida: ${a}`);
    else if (!args.input) args.input = a;
    else throw new UsageError(`Argumento extra: ${a}`);
  }
  if (!args.input) throw new UsageError('Falta el archivo .md de entrada.');
  if (!fs.existsSync(args.input)) throw new UsageError(`No existe: ${args.input}`);
  if (!args.output) args.output = args.input.replace(/\.md$/i, '') + '.pdf';
  return args;
}

// ---------------------------------------------------------------- front-matter
function validateMeta(data) {
  const missing = REQUIRED.filter((k) => data[k] === undefined || data[k] === null || String(data[k]).trim() === '');
  if (missing.length) throw new UsageError(`Front-matter incompleto, faltan: ${missing.join(', ')}`);

  const meta = {};
  for (const [k, v] of Object.entries(data)) {
    // YAML convierte las fechas sin comillas en objetos Date.
    meta[k] = v instanceof Date ? v.toISOString().slice(0, 10) : String(v).trim();
  }
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(meta.date);
  const d = m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null;
  if (!m || d.getUTCFullYear() !== +m[1] || d.getUTCMonth() !== +m[2] - 1 || d.getUTCDate() !== +m[3]) {
    throw new UsageError(`Fecha inválida "${meta.date}": usa YYYY-MM-DD con una fecha real.`);
  }
  meta.dateDisplay = `${m[3]}-${m[2]}-${m[1]}`;
  meta.summary_title = meta.summary_title || 'Resumen';
  for (const [k, v] of Object.entries(meta)) {
    if (LOCAL_PATH_RE.test(v)) throw new UsageError(`El campo "${k}" contiene algo que parece una ruta local.`);
  }
  return meta;
}

// ---------------------------------------------------------------- markdown
const CALLOUTS = { LEAD: ['lead', ''], NOTE: ['note', 'Nota'], SUCCESS: ['success', 'Resultado'],
                   WARNING: ['warning', 'Atención'], DANGER: ['danger', 'Riesgo'] };
const PILL_ALIASES = { 'sí': 'ok', 'si': 'ok', 'parcial': 'warn', 'no': 'bad' };

/** Divide el documento en resumen (antes del primer "## ") y cuerpo, ignorando bloques de código. */
function splitSummary(md) {
  const lines = md.split(/\r?\n/);
  let fence = false;
  for (let i = 0; i < lines.length; i++) {
    if (/^\s*(```|~~~)/.test(lines[i])) fence = !fence;
    if (!fence && /^##\s+\S/.test(lines[i])) return [lines.slice(0, i).join('\n'), lines.slice(i).join('\n')];
  }
  return [md, ''];
}

function buildMarked(toc) {
  const marked = new Marked({ gfm: true, breaks: false });
  let count = 0;
  marked.use({
    renderer: {
      heading(text, level) {
        if (level !== 2) return `<h${level}>${text}</h${level}>\n`;
        count += 1;
        const id = `s${count}`;
        toc.push({ id, num: count, text: text.replace(/<[^>]+>/g, '') });
        return `<h2 id="${id}"><span class="num">${count}</span>${text}</h2>\n`;
      },
      code(code, lang) {
        if ((lang || '').trim() === 'kpis') return renderKpis(code);
        return `<pre><code>${esc(code)}</code></pre>\n`;
      },
      blockquote(quote) {
        const m = /^<p>\[!(LEAD|NOTE|SUCCESS|WARNING|DANGER)\](?:[ \t]+([^\n<]*))?\n?/.exec(quote);
        if (!m) return `<blockquote>${quote}</blockquote>\n`;
        const [cls, defaultTitle] = CALLOUTS[m[1]];
        const title = (m[2] || '').trim() || defaultTitle;
        const body = quote.slice(m[0].length).replace(/^<\/p>\s*/, '<p>').replace(/^<p>\s*<\/p>/, '');
        const head = title ? `<div class="callout-title">${title}</div>` : '';
        return `<div class="callout callout-${cls}">${head}${body.startsWith('<p>') ? body : `<p>${body}`}</div>\n`;
      },
    },
  });
  return marked;
}

function renderKpis(code) {
  const rows = code.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (rows.length < 1 || rows.length > 6) throw new UsageError('Un bloque `kpis` lleva entre 1 y 6 líneas.');
  const cards = rows.map((row) => {
    const parts = row.split('|').map((p) => p.trim());
    if (parts.length < 2 || parts.length > 3 || !parts[0] || !parts[1]) {
      throw new UsageError(`Línea de kpis inválida: "${row}" (usa "valor | etiqueta" o "valor | etiqueta | alt").`);
    }
    const alt = parts[2] === 'alt' ? ' alt' : '';
    return `<div class="kpi${alt}"><div class="kpi-value">${esc(parts[0])}</div><div class="kpi-label">${esc(parts[1])}</div></div>`;
  });
  return `<div class="kpis kpis-${cards.length}">${cards.join('')}</div>\n`;
}

/** Aplica estados, anchos de columna, filas de grupo y saltos de página sobre el HTML ya convertido. */
function postProcess(html) {
  let out = html.replace(/\[\[([^\]]+)\]\]/g, (all, inner) => {
    const m = /^(ok|warn|bad|info):(.+)$/.exec(inner.trim());
    if (m) return `<span class="pill pill-${m[1]}">${m[2].trim()}</span>`;
    const alias = PILL_ALIASES[inner.trim().toLowerCase()];
    if (alias) return `<span class="pill pill-${alias}">${inner.trim()}</span>`;
    throw new UsageError(`Estado desconocido: [[${inner}]]. Usa [[Sí]], [[Parcial]], [[No]] o [[ok|warn|bad|info:texto]].`);
  });

  out = out.replace(/<!--\s*cols:\s*([\d,\s]+?)\s*-->\s*<table>/g, (all, spec) => {
    const parts = spec.split(',').map((n) => Number(n.trim())).filter((n) => n > 0);
    const total = parts.reduce((a, b) => a + b, 0);
    const cols = parts.map((n) => `<col style="width:${((n / total) * 100).toFixed(2)}%">`).join('');
    return `<table class="fixed"><colgroup>${cols}</colgroup>`;
  });

  out = out.replace(/<tr>\s*<td([^>]*)>::\s*([^<]*)<\/td>([\s\S]*?)<\/tr>/g, (all, attrs, label, rest) => {
    const cells = (rest.match(/<td/g) || []).length + 1;
    return `<tr class="group"><td colspan="${cells}">${label.trim()}</td></tr>`;
  });

  return out.replace(/<!--\s*pagebreak\s*-->/g, '<div class="pagebreak"></div>');
}

function renderMarkdown(md, toc) {
  const marked = buildMarked(toc);
  return postProcess(marked.parse(md));
}

// ---------------------------------------------------------------- HTML
function buildHtml(meta, summaryHtml, bodyHtml, toc, pages) {
  const css = fs.readFileSync(path.join(ROOT, 'templates', 'report.css'), 'utf8');
  const tpl = fs.readFileSync(path.join(ROOT, 'templates', 'report-template.html'), 'utf8');
  const metaRows = [
    ['Autor', meta.author], ['Fecha', meta.dateDisplay], ['Código', meta.doc_id],
    ['Versión', meta.version], ['Clasificación', meta.classification],
  ].filter(([, v]) => v);
  const tocHtml = toc.map((t) => {
    const page = pages ? pages[t.id] : null;
    return `<li><span class="toc-num">${t.num}</span><span class="toc-text">${esc(t.text)}</span>` +
           `<span class="toc-page">${page || ''}</span></li>`;
  }).join('');
  const footerParts = [meta.classification, meta.doc_id && `${meta.doc_id}${meta.version ? ' v' + meta.version : ''}`]
    .filter(Boolean).join(' · ');
  const map = {
    TITLE: esc(meta.title),
    TITLE_CSS: JSON.stringify(meta.title).replace(/[\r\n]+/g, ' '),
    FOOTER_CSS: JSON.stringify(footerParts).replace(/[\r\n]+/g, ' '),
    SUBTITLE: meta.subtitle ? `<p class="cover-subtitle">${esc(meta.subtitle)}</p>` : '',
    CATEGORY: meta.category ? `<div class="cover-category">${esc(meta.category)}</div>` : '',
    META: metaRows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join(''),
    SUMMARY_TITLE: esc(meta.summary_title),
    SUMMARY: summaryHtml,
    TOC: toc.length ? `<div class="toc-title">Contenido</div><ol class="toc">${tocHtml}</ol>` : '',
    BODY: bodyHtml,
    CSS: css,
  };
  return tpl.replace(/\{\{(\w+)\}\}/g, (all, key) => (key in map ? map[key] : all));
}

// ---------------------------------------------------------------- PDF
function findBrowser() {
  const found = BROWSERS.find((b) => fs.existsSync(b));
  if (!found) throw new Error('No encontré Chrome ni Edge. Define REPORT_PDF_BROWSER con la ruta del ejecutable.');
  return found;
}

async function printPdf(html, file) {
  const browser = await puppeteer.launch({ executablePath: findBrowser(), headless: 'new' });
  try {
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'load' });
    await page.pdf({ path: file, format: 'A4', printBackground: true, preferCSSPageSize: true });
  } finally {
    await browser.close();
  }
}

/** Texto de cada página del PDF, para ubicar en qué página cae cada sección. */
function pageTexts(pdf) {
  const text = execFileSync('pdftotext', ['-layout', '-enc', 'UTF-8', pdf, '-'], { encoding: 'utf8', maxBuffer: 1 << 26 });
  return text.split('\f').map(norm);
}

function locateSections(pdf, toc) {
  const pages = {};
  const texts = pageTexts(pdf);
  let from = 2; // la portada y el resumen ocupan las dos primeras páginas
  const missing = [];
  for (const t of toc) {
    const needle = norm(t.text);
    let at = -1;
    for (let i = from; i < texts.length; i++) {
      if (texts[i].includes(needle)) { at = i; break; }
    }
    if (at < 0) missing.push(t.text);
    else { pages[t.id] = at + 1; from = at; }
  }
  if (missing.length) console.warn(`Aviso: no ubiqué la página de: ${missing.join(' | ')}`);
  return pages;
}

function verifyPdf(pdf) {
  if (!hasTool('pdftotext') || !hasTool('pdffonts')) {
    throw new VerifyError('Faltan pdftotext o pdffonts (poppler). Instálalos o usa --skip-verify y avísalo al entregar.');
  }
  const text = execFileSync('pdftotext', ['-layout', pdf, '-'], { encoding: 'utf8', maxBuffer: 1 << 26 });
  const hit = LOCAL_PATH_RE.exec(text);
  if (hit) throw new VerifyError(`El PDF contiene algo que parece una ruta local: "${hit[0]}".`);
  const fonts = execFileSync('pdffonts', [pdf], { encoding: 'utf8' }).split(/\r?\n/).slice(2).filter((l) => l.trim());
  // Columnas de pdffonts: nombre, tipo, codificación, emb, sub, uni, objeto, generación.
  const notEmbedded = fonts.filter((l) => {
    const cols = l.trim().split(/\s+/);
    return cols[cols.length - 5] !== 'yes';
  });
  if (notEmbedded.length) throw new VerifyError(`Hay fuentes sin embeber: ${notEmbedded.join(' | ')}`);
  return { pages: text.split('\f').length - 1, fonts: fonts.length };
}

// ---------------------------------------------------------------- principal
async function main() {
  const args = parseArgs(process.argv.slice(2));
  let parsed;
  try {
    parsed = matter(fs.readFileSync(args.input, 'utf8'));
  } catch (e) {
    throw new UsageError(`El front-matter no es YAML válido: ${String(e.message).split('\n')[0]}`);
  }
  const meta = validateMeta(parsed.data);

  const [summaryMd, bodyMd] = splitSummary(parsed.content);
  const toc = [];
  const summaryHtml = renderMarkdown(summaryMd, []);
  const bodyHtml = renderMarkdown(bodyMd, toc);

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'report-pdf-'));
  const first = path.join(tmp, 'pass1.pdf');
  const final = path.join(tmp, 'final.pdf');
  const canLocate = hasTool('pdftotext');
  try {
    let pages = null;
    if (toc.length && canLocate) {
      await printPdf(buildHtml(meta, summaryHtml, bodyHtml, toc, null), first);
      pages = locateSections(first, toc);
    } else if (toc.length) {
      console.warn('Aviso: sin pdftotext (poppler) el índice no lleva números de página.');
    }
    const html = buildHtml(meta, summaryHtml, bodyHtml, toc, pages);
    if (args.html) fs.writeFileSync(args.html, html, 'utf8');
    await printPdf(html, final);

    let note = 'sin verificar';
    if (!args.skipVerify) {
      const r = verifyPdf(final);
      note = `verificado (sin rutas locales, ${r.fonts} fuentes embebidas)`;
    }
    fs.mkdirSync(path.dirname(path.resolve(args.output)), { recursive: true });
    fs.copyFileSync(final, args.output);
    console.log(`OK · ${args.output} · ${note}`);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

main().catch((e) => {
  console.error(e.message);
  process.exit(e instanceof UsageError ? 1 : e instanceof VerifyError ? 2 : 3);
});
