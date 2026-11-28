// Lógica pura de la página del Detector de la Tríada (SPEC-0002 H5), sin JSX ni DOM.

import type { Respuesta } from "./api/cliente.ts";

export type Pata = "datos_privados" | "no_confiable" | "salida_externa";
export type Severidad = "critica" | "alta" | "media" | "baja" | "ninguna";

export const PATAS: readonly Pata[] = ["datos_privados", "no_confiable", "salida_externa"];
export const MAX_BYTES = 1_048_576; // mismo tope que el backend (RF-06)

export interface Evidencia {
  herramienta: string;
  origen: "declarado" | "anotacion" | "regla";
  regla: string | null;
  fragmento: string | null;
}

export interface ResumenHerramienta {
  nombre: string;
  patas: Pata[];
  clasificacion: "declarada" | "inferida" | "sin_clasificar";
  egreso_restringido: boolean;
  multipata: boolean;
}

export interface Reporte {
  formato: "mcp" | "agentguard";
  severidad: Severidad;
  incompleto: boolean;
  severidad_peor_caso: Severidad | null;
  faltan: Pata[];
  patas: Record<Pata, Evidencia[]>;
  herramientas: ResumenHerramienta[];
  recomendaciones: { id: string; texto: string }[];
}

export const NOMBRE_PATA: Record<Pata, string> = {
  datos_privados: "Datos privados",
  no_confiable: "Contenido no confiable",
  salida_externa: "Salida externa",
};

export const NOMBRE_SEVERIDAD: Record<Severidad, string> = {
  critica: "Crítica",
  alta: "Alta",
  media: "Media",
  baja: "Baja",
  ninguna: "Ninguna",
};

export const NOMBRE_ORIGEN: Record<Evidencia["origen"], string> = {
  declarado: "declarado",
  anotacion: "anotación MCP",
  regla: "regla",
};

export type Preparado = { ok: true; cuerpo: string } | { ok: false; error: string };

/** Valida en el navegador antes de enviar (E15): vacío, tamaño y JSON roto, con mensaje claro. */
export function prepararManifiesto(texto: string): Preparado {
  const recortado = texto.trim();
  if (!recortado) return { ok: false, error: "Pega un manifiesto o carga un archivo .json." };
  if (new TextEncoder().encode(recortado).length > MAX_BYTES) {
    return { ok: false, error: "El manifiesto supera el máximo de 1 MB." };
  }
  try {
    const valor: unknown = JSON.parse(recortado);
    if (typeof valor !== "object" || valor === null || Array.isArray(valor)) {
      return { ok: false, error: "El manifiesto debe ser un objeto JSON ({ ... })." };
    }
    return { ok: true, cuerpo: recortado };
  } catch (error) {
    const detalle = error instanceof SyntaxError ? ` (${error.message})` : "";
    return { ok: false, error: `No es un JSON válido${detalle}.` };
  }
}

export type Resultado = { ok: true; reporte: Reporte } | { ok: false; error: string };

/** Traduce la respuesta de la API a un reporte o a un mensaje claro, sin trazas (E15). */
export function interpretarAnalisis(respuesta: Respuesta): Resultado {
  if (respuesta.tipo === "sin_respuesta") {
    return { ok: false, error: "La API no responde. Revisa que AgentGuard esté en marcha." };
  }
  const { status, cuerpo } = respuesta;
  if (status === 200 && esReporte(cuerpo)) return { ok: true, reporte: cuerpo };
  if (status === 413) return { ok: false, error: "El manifiesto supera el máximo de 1 MB." };
  if (status === 422) return { ok: false, error: describir422(cuerpo) };
  return { ok: false, error: `Respuesta inesperada de la API (${status}).` };
}

function describir422(cuerpo: unknown): string {
  const detalle = typeof cuerpo === "object" && cuerpo !== null && "detail" in cuerpo ? cuerpo.detail : null;
  if (!Array.isArray(detalle) || detalle.length === 0) return "El manifiesto no es válido.";
  const lineas = detalle.slice(0, 3).map((error: unknown) => {
    if (typeof error !== "object" || error === null) return "error desconocido";
    const msg = "msg" in error && typeof error.msg === "string" ? error.msg : "error desconocido";
    const loc = "loc" in error && Array.isArray(error.loc) ? error.loc.join(" › ") : "";
    return loc ? `${loc}: ${msg}` : msg;
  });
  const resto = detalle.length > 3 ? ` (y ${detalle.length - 3} más)` : "";
  return `El manifiesto no es válido: ${lineas.join("; ")}${resto}.`;
}

function esReporte(cuerpo: unknown): cuerpo is Reporte {
  return (
    typeof cuerpo === "object" &&
    cuerpo !== null &&
    "severidad" in cuerpo &&
    typeof cuerpo.severidad === "string" &&
    cuerpo.severidad in NOMBRE_SEVERIDAD &&
    "patas" in cuerpo &&
    "herramientas" in cuerpo &&
    Array.isArray(cuerpo.herramientas)
  );
}

/** Texto de la evidencia: «regla P-BD: "sql"» o «declarado». */
export function describirEvidencia(evidencia: Evidencia): string {
  const origen = NOMBRE_ORIGEN[evidencia.origen];
  const regla = evidencia.regla ? ` ${evidencia.regla}` : "";
  const fragmento = evidencia.fragmento ? `: «${evidencia.fragmento}»` : "";
  return `${origen}${regla}${fragmento}`;
}

/** Qué significa cada pata, para mostrarlas antes de analizar. */
export const DESCRIPCION_PATA: Record<Pata, string> = {
  datos_privados: "Lee correos, archivos, bases o cualquier dato que no debería salir.",
  no_confiable: "Ingiere web, documentos o mensajes que un tercero puede escribir.",
  salida_externa: "Puede enviar datos afuera: webhooks, APIs, correo, peticiones HTTP.",
};

/** «2,4 KB de 1 MB»: cuánto pesa el manifiesto frente al tope del backend. */
export function pesoManifiesto(texto: string): string {
  const bytes = new TextEncoder().encode(texto).length;
  const peso = bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1).replace(".", ",")} KB`;
  return `${peso} de 1 MB`;
}
