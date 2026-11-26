// Lógica pura de la pantalla de contención de prompt injection (SPEC-0005 E12, E13), sin JSX ni DOM.

import type { Respuesta } from "./api/cliente.ts";

export interface ReglaInyeccion {
  id: string;
  modo: "marcar" | "bloquear" | "observar";
  detecciones: number;
}

export interface SesionEstado {
  id: string; // abreviado: el id completo es una capacidad del runtime y nunca sale
  agente: string;
  implicita: boolean;
  acotada: boolean;
  contaminada: boolean;
  origen: string | null;
  desde: string | null;
}

export interface EstadoInyeccion {
  configurado: boolean;
  error: string | null;
  reglas: ReglaInyeccion[];
  marcadores: number;
  ttl_minutos: number;
  origenes_confiables: Record<string, string[]>;
  sesiones: SesionEstado[];
  contadores: Record<string, number>;
  avisos: string[];
}

export type ResultadoInyeccion = { ok: true; estado: EstadoInyeccion } | { ok: false; error: string };

export const NOMBRES_REGLAS: Readonly<Record<string, string>> = {
  "iny.invisible": "Caracteres invisibles",
  "iny.rol": "Marcas de rol o plantilla",
  "iny.instruccion": "Frases de secuestro",
  "iny.herramienta": "Llamada a herramienta imitada",
  "iny.exfil_markdown": "Imagen hacia una URL con datos",
  "iny.oculto": "Texto oculto en HTML",
  "iny.marcador": "Marcador propio",
};

export const NOMBRES_ORIGENES: Readonly<Record<string, string>> = {
  web: "Web",
  correo: "Correo",
  documento: "Documento",
  memoria: "Memoria",
  agente: "Otro agente",
  herramienta: "Respuesta de una acción",
};

const MODOS: Readonly<Record<ReglaInyeccion["modo"], string>> = {
  marcar: "Marca y entrega",
  bloquear: "Bloquea el contenido",
  observar: "Solo auditoría",
};

export function nombreRegla(id: string): string {
  return NOMBRES_REGLAS[id] ?? id;
}

export function nombreOrigen(id: string | null): string {
  return id === null ? "—" : (NOMBRES_ORIGENES[id] ?? id);
}

export function nombreModo(modo: ReglaInyeccion["modo"]): string {
  return MODOS[modo];
}

export function interpretarInyeccion(respuesta: Respuesta): ResultadoInyeccion {
  if (respuesta.tipo === "sin_respuesta") {
    return { ok: false, error: "La API no responde. Revisa que AgentGuard esté en marcha." };
  }
  if (respuesta.status === 401) return { ok: false, error: "Token de administración inválido." };
  if (respuesta.status === 200 && esEstado(respuesta.cuerpo)) return { ok: true, estado: respuesta.cuerpo };
  return { ok: false, error: `Respuesta inesperada de la API (${respuesta.status}).` };
}

function esEstado(cuerpo: unknown): cuerpo is EstadoInyeccion {
  return (
    typeof cuerpo === "object" &&
    cuerpo !== null &&
    "configurado" in cuerpo &&
    typeof cuerpo.configurado === "boolean" &&
    "reglas" in cuerpo &&
    Array.isArray(cuerpo.reglas) &&
    "sesiones" in cuerpo &&
    Array.isArray(cuerpo.sesiones) &&
    "contadores" in cuerpo &&
    typeof cuerpo.contadores === "object" &&
    "origenes_confiables" in cuerpo &&
    typeof cuerpo.origenes_confiables === "object" &&
    "avisos" in cuerpo &&
    Array.isArray(cuerpo.avisos)
  );
}

/** Resumen de una línea: cuántas sesiones hay y cuántas quedaron contenidas. */
export function resumenInyeccion(estado: EstadoInyeccion): string {
  const activas = estado.contadores["sesiones_activas"] ?? estado.sesiones.length;
  const contaminadas = estado.contadores["sesiones_contaminadas"] ?? 0;
  const bloqueos = totalBloqueos(estado);
  return `${activas} ${activas === 1 ? "sesión activa" : "sesiones activas"} · ${contaminadas} ${
    contaminadas === 1 ? "contaminada" : "contaminadas"
  } · ${bloqueos} ${bloqueos === 1 ? "acción contenida" : "acciones contenidas"} desde el arranque`;
}

export function totalBloqueos(estado: EstadoInyeccion): number {
  return (
    (estado.contadores["bloqueos_sesion_contaminada"] ?? 0) +
    (estado.contadores["bloqueos_fuera_de_sesion"] ?? 0) +
    (estado.contadores["bloqueos_contenido"] ?? 0)
  );
}

/** Las contaminadas primero y, dentro de cada grupo, por agente. */
export function sesionesOrdenadas(sesiones: readonly SesionEstado[]): SesionEstado[] {
  return [...sesiones].sort(
    (a, b) => Number(b.contaminada) - Number(a.contaminada) || a.agente.localeCompare(b.agente),
  );
}
