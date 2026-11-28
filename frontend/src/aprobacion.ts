// Lógica pura de la bandeja de aprobación humana (SPEC-0006 E5–E7, E15), sin JSX ni DOM.

import type { Respuesta } from "./api/cliente.ts";
import type { Cifra, Tono } from "./diseno.ts";
import { nombreOrigen } from "./inyeccion.ts";

export type { Cifra, Tono };

export type EstadoSolicitud = "pendiente" | "aprobada" | "negada" | "vencida" | "usada" | "cancelada";

export interface Solicitud {
  id: string;
  agente: string;
  sesion: string; // abreviada: el id completo nunca sale
  destino: string;
  metodo: string;
  motivo: "siempre" | "sesion_contaminada";
  origen: string | null;
  senales: Record<string, number>;
  parametros: Record<string, unknown> | null; // null una vez decidida (E14)
  estado: EstadoSolicitud;
  nota: string | null;
  decidida_por: string | null;
  creada: string;
  vence: string;
  decidida: string | null;
  usada: string | null;
}

export interface EstadoAprobacion {
  configurado: boolean;
  error: string | null;
  minutos_decision: number;
  minutos_boleto: number;
  notificar: string | null;
  contadores: Record<string, number> | null;
  avisos: string[];
}

export type Decision = "aprobar" | "negar";
export type Resultado<T> = { ok: true; valor: T } | { ok: false; error: string };

export const MAX_NOTA = 500;

const ESTADOS: Readonly<Record<EstadoSolicitud, string>> = {
  pendiente: "Pendiente",
  aprobada: "Aprobada: esperando el reintento",
  negada: "Negada",
  vencida: "Vencida",
  usada: "Aprobada y ejecutada",
  cancelada: "Cancelada (sesión cerrada)",
};

export function nombreEstado(estado: EstadoSolicitud): string {
  return ESTADOS[estado];
}

export function nombreMotivo(solicitud: Pick<Solicitud, "motivo" | "origen">): string {
  return solicitud.motivo === "siempre"
    ? "La acción siempre pide aprobación (irreversible o del plano de control)"
    : `Sesión contaminada por: ${nombreOrigen(solicitud.origen).toLowerCase()}`;
}

/** E7: una sesión contaminada pudo leer una inyección; los parámetros pueden venir de ella. */
export function esRiesgosa(solicitud: Pick<Solicitud, "motivo">): boolean {
  return solicitud.motivo === "sesion_contaminada";
}

/** E7: los parámetros vienen del agente. Siempre texto plano: nunca HTML ni enlaces. */
export function parametrosVisibles(parametros: Record<string, unknown> | null): [string, string][] {
  if (parametros === null) return [];
  return Object.entries(parametros).map(([clave, valor]) => [
    clave,
    typeof valor === "string" ? valor : JSON.stringify(valor),
  ]);
}

/** «vence en 12 min», «vence en menos de 1 min» o «vencida». */
export function tiempoRestante(vence: string, ahora: Date): string {
  const minutos = Math.floor((new Date(vence).getTime() - ahora.getTime()) / 60000);
  if (Number.isNaN(minutos)) return "";
  if (new Date(vence).getTime() <= ahora.getTime()) return "vencida";
  return minutos < 1 ? "vence en menos de 1 min" : `vence en ${minutos} min`;
}

export function pendientes(solicitudes: readonly Solicitud[]): Solicitud[] {
  return solicitudes.filter((s) => s.estado === "pendiente");
}

export function decididas(solicitudes: readonly Solicitud[]): Solicitud[] {
  return solicitudes.filter((s) => s.estado !== "pendiente");
}

export function resumenBandeja(solicitudes: readonly Solicitud[]): string {
  const cantidad = pendientes(solicitudes).length;
  if (cantidad === 0) return "Sin solicitudes pendientes";
  return `${cantidad} ${cantidad === 1 ? "solicitud pendiente" : "solicitudes pendientes"}`;
}

/** El cuerpo de E6. La nota es opcional y se recorta: el backend rechaza más de 500 caracteres. */
export function cuerpoDecision(decision: Decision, nota: string): string {
  const limpia = nota.trim().slice(0, MAX_NOTA);
  return JSON.stringify(limpia ? { decision, nota: limpia } : { decision });
}

function sinRespuesta<T>(respuesta: Respuesta): Resultado<T> | null {
  if (respuesta.tipo === "sin_respuesta") {
    return { ok: false, error: "La API no responde. Revisa que AgentGuard esté en marcha." };
  }
  if (respuesta.status === 401) return { ok: false, error: "Token de administración inválido." };
  if (respuesta.status === 503) {
    return {
      ok: false,
      error: "Aprobación humana no disponible: la base no responde o APROBACION_CONFIG es inválido.",
    };
  }
  return null;
}

export function interpretarSolicitudes(respuesta: Respuesta): Resultado<Solicitud[]> {
  const fallo = sinRespuesta<Solicitud[]>(respuesta);
  if (fallo) return fallo;
  if (respuesta.tipo === "ok" && respuesta.status === 200 && esBandeja(respuesta.cuerpo)) {
    return { ok: true, valor: respuesta.cuerpo.solicitudes };
  }
  return { ok: false, error: inesperada(respuesta) };
}

export function interpretarEstado(respuesta: Respuesta): Resultado<EstadoAprobacion> {
  const fallo = sinRespuesta<EstadoAprobacion>(respuesta);
  if (fallo) return fallo;
  if (respuesta.tipo === "ok" && respuesta.status === 200 && esEstado(respuesta.cuerpo)) {
    return { ok: true, valor: respuesta.cuerpo };
  }
  return { ok: false, error: inesperada(respuesta) };
}

export function interpretarDecision(respuesta: Respuesta): Resultado<Solicitud> {
  const fallo = sinRespuesta<Solicitud>(respuesta);
  if (fallo) return fallo;
  if (respuesta.tipo === "ok" && respuesta.status === 409) {
    return { ok: false, error: "La solicitud ya no está pendiente: venció o ya se decidió." };
  }
  if (respuesta.tipo === "ok" && respuesta.status === 404) {
    return { ok: false, error: "La solicitud no existe." };
  }
  if (respuesta.tipo === "ok" && respuesta.status === 200 && esSolicitud(respuesta.cuerpo)) {
    return { ok: true, valor: respuesta.cuerpo };
  }
  return { ok: false, error: inesperada(respuesta) };
}

function inesperada(respuesta: Respuesta): string {
  return `Respuesta inesperada de la API (${respuesta.tipo === "ok" ? respuesta.status : "sin respuesta"}).`;
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function esSolicitud(valor: unknown): valor is Solicitud {
  return (
    esObjeto(valor) &&
    typeof valor["id"] === "string" &&
    typeof valor["agente"] === "string" &&
    typeof valor["destino"] === "string" &&
    typeof valor["estado"] === "string" &&
    typeof valor["vence"] === "string" &&
    (valor["parametros"] === null || esObjeto(valor["parametros"])) &&
    esObjeto(valor["senales"])
  );
}

function esBandeja(cuerpo: unknown): cuerpo is { solicitudes: Solicitud[] } {
  return esObjeto(cuerpo) && Array.isArray(cuerpo["solicitudes"]) && cuerpo["solicitudes"].every(esSolicitud);
}

function esEstado(cuerpo: unknown): cuerpo is EstadoAprobacion {
  return (
    esObjeto(cuerpo) &&
    typeof cuerpo["configurado"] === "boolean" &&
    typeof cuerpo["minutos_decision"] === "number" &&
    (cuerpo["contadores"] === null || esObjeto(cuerpo["contadores"])) &&
    Array.isArray(cuerpo["avisos"])
  );
}

// ---------- Presentación (sistema de diseño Tactical Terminal) ----------

const TONOS: Readonly<Record<EstadoSolicitud, Tono>> = {
  pendiente: "alerta",
  aprobada: "permitir",
  usada: "permitir",
  negada: "bloquear",
  vencida: "neutro",
  cancelada: "neutro",
};

export function tonoEstado(estado: EstadoSolicitud): Tono {
  return TONOS[estado];
}

/** Las cuatro cifras de la bandeja. Salen de los contadores de la base (todo el historial); si la base no
 * respondió, de la lista recibida, que solo trae las últimas decididas. */
export function cifras(estado: EstadoAprobacion | null, solicitudes: readonly Solicitud[]): Cifra[] {
  const cuenta = estado?.contadores ?? contarLista(solicitudes);
  const de = (clave: EstadoSolicitud) => cuenta[clave] ?? 0;
  const aprobadas = de("aprobada") + de("usada");
  return [
    { id: "pendientes", titulo: "Pendientes", valor: de("pendiente"), detalle: "esperan una decisión", tono: "alerta" },
    {
      id: "aprobadas",
      titulo: "Aprobadas",
      valor: aprobadas,
      detalle: `${de("usada")} ${de("usada") === 1 ? "ejecutada" : "ejecutadas"}`,
      tono: "permitir",
    },
    { id: "negadas", titulo: "Negadas", valor: de("negada"), detalle: "por una persona", tono: "bloquear" },
    {
      id: "cerradas",
      titulo: "Vencidas",
      valor: de("vencida") + de("cancelada"),
      detalle: de("cancelada") ? `${de("cancelada")} por sesión cerrada` : "nadie decidió a tiempo",
      tono: "neutro",
    },
  ];
}

function contarLista(solicitudes: readonly Solicitud[]): Record<string, number> {
  const cuenta: Record<string, number> = {};
  for (const s of solicitudes) cuenta[s.estado] = (cuenta[s.estado] ?? 0) + 1;
  return cuenta;
}

/** La línea bajo el título: si la puerta está lista y si la base responde (E15). */
export function estadoPuerta(estado: EstadoAprobacion | null): { texto: string; tono: Tono } {
  if (estado === null) return { texto: "Sin datos de la puerta", tono: "neutro" };
  if (!estado.configurado) return { texto: "Puerta sin configurar: nada se ejecuta", tono: "bloquear" };
  if (estado.contadores === null) return { texto: "Puerta activa · base sin respuesta", tono: "alerta" };
  return { texto: "Puerta activa · base conectada", tono: "permitir" };
}

/** «20:56» en la hora local: cuándo se decidió o, si nadie decidió, cuándo venció. */
export function horaDe(solicitud: Pick<Solicitud, "decidida" | "vence">): string {
  const fecha = new Date(solicitud.decidida ?? solicitud.vence);
  if (Number.isNaN(fecha.getTime())) return "—";
  return `${String(fecha.getHours()).padStart(2, "0")}:${String(fecha.getMinutes()).padStart(2, "0")}`;
}
