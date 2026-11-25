// Lógica pura de la página de estado (SPEC-0001 H4): sin JSX ni DOM, para probarla con node --test.

import type { Respuesta } from "./api/cliente.ts";

export type Semaforo = "ok" | "caida" | "desconocido";

export interface EstadoSistema {
  api: Semaforo;
  postgres: Semaforo;
  mensaje: string;
}

/** Traduce la respuesta de `/health/dependencias` a lo que muestra la página (E11, E12). */
export function interpretarDependencias(respuesta: Respuesta): EstadoSistema {
  if (respuesta.tipo === "sin_respuesta") {
    return { api: "caida", postgres: "desconocido", mensaje: "La API no responde." };
  }
  const postgres = leerPostgres(respuesta.cuerpo);
  if (respuesta.status === 200 && postgres === "ok") {
    return { api: "ok", postgres: "ok", mensaje: "Todo en orden." };
  }
  if (respuesta.status === 503) {
    return { api: "ok", postgres, mensaje: "La API responde, pero PostgreSQL no." };
  }
  return { api: "caida", postgres: "desconocido", mensaje: `Respuesta inesperada (${respuesta.status}).` };
}

function leerPostgres(cuerpo: unknown): Semaforo {
  if (typeof cuerpo !== "object" || cuerpo === null || !("dependencias" in cuerpo)) {
    return "desconocido";
  }
  const dependencias = cuerpo.dependencias;
  if (typeof dependencias !== "object" || dependencias === null || !("postgres" in dependencias)) {
    return "desconocido";
  }
  const valor = dependencias.postgres;
  return valor === "ok" || valor === "caida" ? valor : "desconocido";
}

/** Lee la versión de `/version`; `null` si no vino o no tiene la forma esperada. */
export function interpretarVersion(respuesta: Respuesta): string | null {
  if (respuesta.tipo !== "ok" || respuesta.status !== 200) return null;
  const cuerpo = respuesta.cuerpo;
  if (typeof cuerpo === "object" && cuerpo !== null && "version" in cuerpo) {
    return typeof cuerpo.version === "string" ? cuerpo.version : null;
  }
  return null;
}
