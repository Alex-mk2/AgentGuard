// Único cliente REST del frontend (context.md §3). Todas las llamadas a la API pasan por aquí.

const PREFIJO = "/api/v1";
const TIMEOUT_MS = 5000;

export type Respuesta =
  | { tipo: "ok"; status: number; cuerpo: unknown }
  | { tipo: "sin_respuesta" };

/** GET con timeout. Nunca lanza: si la API no contesta devuelve `sin_respuesta` (SPEC-0001 E12). */
export function obtener(ruta: string, cabeceras?: Record<string, string>): Promise<Respuesta> {
  return pedir(ruta, { method: "GET", headers: cabeceras });
}

/** POST de JSON con el mismo contrato que `obtener`. `cuerpo` ya viene serializado. */
export function enviar(ruta: string, cuerpo: string): Promise<Respuesta> {
  return pedir(ruta, {
    method: "POST",
    body: cuerpo,
    headers: { "Content-Type": "application/json" },
  });
}

async function pedir(ruta: string, opciones: RequestInit): Promise<Respuesta> {
  try {
    const respuesta = await fetch(`${PREFIJO}${ruta}`, {
      ...opciones,
      headers: { Accept: "application/json", ...opciones.headers },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const cuerpo: unknown = await respuesta.json().catch(() => null);
    return { tipo: "ok", status: respuesta.status, cuerpo };
  } catch {
    return { tipo: "sin_respuesta" };
  }
}
