// Lógica pura de la pantalla del Secret Broker (SPEC-0003 E11, E13, E15), sin JSX ni DOM.

import type { Respuesta } from "./api/cliente.ts";

export interface AccionEstado {
  id: string;
  descripcion: string;
  secreto: string;
  host: string | null;
  disponible: boolean;
}

export interface AgenteEstado {
  id: string;
  acciones: string[];
  max_por_minuto: number;
  token_cargado: boolean;
}

export interface SecretoEstado {
  nombre: string;
  cargado: boolean;
  compartido: boolean;
  acciones: string[];
}

export interface EstadoBroker {
  configurado: boolean;
  error: string | null;
  acciones: AccionEstado[];
  agentes: AgenteEstado[];
  secretos: SecretoEstado[];
  avisos: string[];
}

export type ResultadoEstado = { ok: true; estado: EstadoBroker } | { ok: false; error: string };

/** El token se valida mínimamente antes de enviarlo; nunca se guarda fuera del componente. */
export function cabeceraAdmin(token: string): Record<string, string> | null {
  const limpio = token.trim();
  return limpio ? { Authorization: `Bearer ${limpio}` } : null;
}

export function interpretarEstado(respuesta: Respuesta): ResultadoEstado {
  if (respuesta.tipo === "sin_respuesta") {
    return { ok: false, error: "La API no responde. Revisa que AgentGuard esté en marcha." };
  }
  if (respuesta.status === 401) return { ok: false, error: "Token de administración inválido." };
  if (respuesta.status === 200 && esEstado(respuesta.cuerpo)) return { ok: true, estado: respuesta.cuerpo };
  return { ok: false, error: `Respuesta inesperada de la API (${respuesta.status}).` };
}

function esEstado(cuerpo: unknown): cuerpo is EstadoBroker {
  return (
    typeof cuerpo === "object" &&
    cuerpo !== null &&
    "configurado" in cuerpo &&
    typeof cuerpo.configurado === "boolean" &&
    "acciones" in cuerpo &&
    Array.isArray(cuerpo.acciones) &&
    "agentes" in cuerpo &&
    Array.isArray(cuerpo.agentes) &&
    "secretos" in cuerpo &&
    Array.isArray(cuerpo.secretos) &&
    "avisos" in cuerpo &&
    Array.isArray(cuerpo.avisos)
  );
}

/** Resumen de una línea para la cabecera de la pantalla. */
export function resumen(estado: EstadoBroker): string {
  if (!estado.configurado) return "El Secret Broker no está configurado.";
  const disponibles = estado.acciones.filter((accion) => accion.disponible).length;
  return `${disponibles} de ${estado.acciones.length} acciones disponibles · ${estado.agentes.length} agentes`;
}
