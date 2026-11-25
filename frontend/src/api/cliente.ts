// Único cliente REST del frontend (context.md §3). Todas las llamadas a la API pasan por aquí.

const PREFIJO = "/api/v1";
const TIMEOUT_MS = 5000;

export type Respuesta =
  | { tipo: "ok"; status: number; cuerpo: unknown }
  | { tipo: "sin_respuesta" };

/** GET con timeout. Nunca lanza: si la API no contesta devuelve `sin_respuesta` (E12). */
export async function obtener(ruta: string): Promise<Respuesta> {
  try {
    const respuesta = await fetch(`${PREFIJO}${ruta}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const cuerpo: unknown = await respuesta.json().catch(() => null);
    return { tipo: "ok", status: respuesta.status, cuerpo };
  } catch {
    return { tipo: "sin_respuesta" };
  }
}
