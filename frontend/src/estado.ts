// Lógica pura de la página de estado (SPEC-0001 H4): sin JSX ni DOM, para probarla con node --test.

import type { Respuesta } from "./api/cliente.ts";
import type { Cifra, Tono } from "./diseno.ts";
import { MODULOS } from "./modulos.ts";

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

/** El punto del pie del menú: `/health` no consulta la base, así que solo dice si la API responde. */
export function semaforoApi(respuesta: Respuesta): Semaforo {
  if (respuesta.tipo === "sin_respuesta") return "caida";
  return respuesta.status === 200 ? "ok" : "desconocido";
}

/** El tono de la línea de estado: todo bien en verde, la base caída en ámbar (la API sigue
 * sirviendo), la API caída en rojo y, mientras se comprueba, gris. */
export function tonoSistema(estado: EstadoSistema | null): Tono {
  if (estado === null) return "neutro";
  if (estado.api !== "ok") return "bloquear";
  return estado.postgres === "ok" ? "permitir" : "alerta";
}

const ETIQUETA: Record<Semaforo, string> = { ok: "En línea", caida: "Caído", desconocido: "Sin datos" };
const TONO: Record<Semaforo, Tono> = { ok: "permitir", caida: "bloquear", desconocido: "neutro" };

/** Las cifras del panel de inicio. Con `estado` en null, la API y la base se están comprobando. */
export function cifrasSistema(estado: EstadoSistema | null, version: string | null): Cifra[] {
  const de = (semaforo: Semaforo | undefined, detalle: string): Pick<Cifra, "valor" | "detalle" | "tono"> =>
    semaforo === undefined
      ? { valor: "…", detalle: "comprobando", tono: "neutro" }
      : { valor: ETIQUETA[semaforo], detalle, tono: TONO[semaforo] };
  const activos = MODULOS.filter((modulo) => modulo.estado === "activo").length;
  return [
    { id: "api", titulo: "API", ...de(estado?.api, "FastAPI · /api/v1") },
    { id: "postgres", titulo: "PostgreSQL", ...de(estado?.postgres, "aprobaciones y migraciones") },
    {
      id: "modulos",
      titulo: "Módulos activos",
      valor: `${activos}/${MODULOS.length}`,
      detalle: "protegiendo en tiempo de ejecución",
      tono: "marca",
    },
    { id: "version", titulo: "Versión", valor: version ?? "—", detalle: "AgentGuard", tono: "neutro" },
  ];
}
