// Lógica pura del sistema de diseño «Tactical Terminal», compartida por las pantallas. Sin JSX ni DOM.

/** Verde solo para lo permitido, rojo solo para lo negado o bloqueado, ámbar para lo que espera
 * revisión, cian para la marca y lo informativo, gris para lo inactivo. */
export type Tono = "permitir" | "bloquear" | "alerta" | "marca" | "neutro";

/** Una cifra del resumen de una pantalla. */
export interface Cifra {
  id: string;
  titulo: string;
  valor: number | string;
  detalle: string;
  tono: Tono;
}

/** «1 regla», «3 reglas». */
export function plural(cantidad: number, singular: string, varias: string): string {
  return `${cantidad} ${cantidad === 1 ? singular : varias}`;
}

export function suma(conteo: Record<string, number>): number {
  return Object.values(conteo).reduce((total, n) => total + n, 0);
}

// ---------- Resaltado de JSON para el editor tipo terminal ----------

export type TipoFicha = "clave" | "cadena" | "numero" | "literal" | "puntuacion" | "texto";

export interface Ficha {
  tipo: TipoFicha;
  texto: string;
}

// Cadena con escapes (incluso sin cerrar, mientras se escribe), número, literal o puntuación.
const PATRON = /("(?:[^"\\\n]|\\.)*"?)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}[\]:,])/g;

/** Parte el texto en fichas para colorearlo. No valida: lo que no reconoce queda como «texto», y
 * concatenar las fichas devuelve exactamente el texto original (el resaltado no puede desalinearse
 * del área de texto que está debajo). */
export function fichasJson(texto: string): Ficha[] {
  const fichas: Ficha[] = [];
  let ultimo = 0;
  for (const encontrado of texto.matchAll(PATRON)) {
    const inicio = encontrado.index;
    if (inicio > ultimo) fichas.push({ tipo: "texto", texto: texto.slice(ultimo, inicio) });
    const [completo, cadena, numero, literal] = encontrado;
    let tipo: TipoFicha = "puntuacion";
    if (cadena !== undefined) {
      tipo = /^\s*:/.test(texto.slice(inicio + completo.length)) ? "clave" : "cadena";
    } else if (numero !== undefined) {
      tipo = "numero";
    } else if (literal !== undefined) {
      tipo = "literal";
    }
    fichas.push({ tipo, texto: completo });
    ultimo = inicio + completo.length;
  }
  if (ultimo < texto.length) fichas.push({ tipo: "texto", texto: texto.slice(ultimo) });
  return fichas;
}

/** Cuántas líneas tiene el texto (al menos una, para el margen de números). */
export function contarLineas(texto: string): number {
  let lineas = 1;
  for (const caracter of texto) if (caracter === "\n") lineas += 1;
  return lineas;
}
