// Lógica pura de la pantalla de control de egresos (SPEC-0004 E15, E16), sin JSX ni DOM.

import type { Respuesta } from "./api/cliente.ts";
import type { Cifra, Tono } from "./diseno.ts";
import { plural, suma } from "./diseno.ts";

export interface ReglaDlp {
  id: string;
  modo: "bloquear" | "observar";
}

export interface EstadoEgresos {
  configurado: boolean;
  error: string | null;
  allowlist: string[];
  reglas: ReglaDlp[];
  marcadores: number; // solo cuántos: el texto nunca sale de AgentGuard
  bloqueos: Record<string, number>;
  observados: Record<string, number>;
  web: Record<string, string[]>;
}

export type ResultadoEgresos = { ok: true; estado: EstadoEgresos } | { ok: false; error: string };

/** Nombre legible de cada causa de bloqueo (las reglas DLP y los motivos de la salida). */
export const CAUSAS: Readonly<Record<string, string>> = {
  destino: "Destino fuera de la allowlist",
  ip: "Host que resuelve a una IP no pública",
  "dlp.secreto_cargado": "Secreto del broker",
  "dlp.credencial": "Credencial conocida",
  "dlp.tarjeta": "Número de tarjeta",
  "dlp.rut": "RUT",
  "dlp.marcador": "Marcador o canary token",
};

export function nombreCausa(id: string): string {
  return CAUSAS[id] ?? id;
}

export function interpretarEgresos(respuesta: Respuesta): ResultadoEgresos {
  if (respuesta.tipo === "sin_respuesta") {
    return { ok: false, error: "La API no responde. Revisa que AgentGuard esté en marcha." };
  }
  if (respuesta.status === 401) return { ok: false, error: "Token de administración inválido." };
  if (respuesta.status === 200 && esEstado(respuesta.cuerpo)) return { ok: true, estado: respuesta.cuerpo };
  return { ok: false, error: `Respuesta inesperada de la API (${respuesta.status}).` };
}

function esEstado(cuerpo: unknown): cuerpo is EstadoEgresos {
  return (
    typeof cuerpo === "object" &&
    cuerpo !== null &&
    "configurado" in cuerpo &&
    typeof cuerpo.configurado === "boolean" &&
    "allowlist" in cuerpo &&
    Array.isArray(cuerpo.allowlist) &&
    "reglas" in cuerpo &&
    Array.isArray(cuerpo.reglas) &&
    "bloqueos" in cuerpo &&
    typeof cuerpo.bloqueos === "object" &&
    "observados" in cuerpo &&
    typeof cuerpo.observados === "object" &&
    "web" in cuerpo &&
    typeof cuerpo.web === "object"
  );
}

/** Resumen de una línea. Sin allowlist, toda salida está bloqueada (D-01). */
export function resumenEgresos(estado: EstadoEgresos): string {
  if (!estado.configurado) return "Sin allowlist configurada: toda salida de red está bloqueada.";
  const bloqueos = Object.values(estado.bloqueos).reduce((total, n) => total + n, 0);
  const destinos = estado.allowlist.length;
  return `${destinos} ${destinos === 1 ? "destino permitido" : "destinos permitidos"} · ${bloqueos} ${
    bloqueos === 1 ? "salida bloqueada" : "salidas bloqueadas"
  } desde el arranque`;
}

/** Filas de bloqueos u observaciones, de la causa más frecuente a la menos. */
export function filasConteo(conteo: Record<string, number>): { causa: string; veces: number }[] {
  return Object.entries(conteo)
    .map(([id, veces]) => ({ causa: nombreCausa(id), veces }))
    .sort((a, b) => b.veces - a.veces || a.causa.localeCompare(b.causa));
}

// ---------- Presentación ----------

export function tonoModoDlp(modo: ReglaDlp["modo"]): Tono {
  return modo === "bloquear" ? "bloquear" : "neutro";
}

export function cifrasEgresos(estado: EstadoEgresos): Cifra[] {
  const bloquean = estado.reglas.filter((r) => r.modo === "bloquear").length;
  const bloqueos = suma(estado.bloqueos);
  const observados = suma(estado.observados);
  return [
    {
      id: "allowlist",
      titulo: "Destinos permitidos",
      valor: estado.allowlist.length,
      detalle: estado.configurado ? "en la allowlist global" : "sin allowlist: no sale nada",
      tono: estado.configurado ? "marca" : "bloquear",
    },
    {
      id: "dlp",
      titulo: "Reglas DLP",
      valor: estado.reglas.length,
      detalle: `${bloquean} bloquean · ${plural(estado.marcadores, "marcador", "marcadores")}`,
      tono: "marca",
    },
    {
      id: "bloqueos",
      titulo: "Salidas bloqueadas",
      valor: bloqueos,
      detalle: "desde el arranque",
      tono: bloqueos ? "bloquear" : "neutro",
    },
    {
      id: "observados",
      titulo: "Observadas",
      valor: observados,
      detalle: "salieron, pero quedaron marcadas",
      tono: observados ? "alerta" : "neutro",
    },
  ];
}
