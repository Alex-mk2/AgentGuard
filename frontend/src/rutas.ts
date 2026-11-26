// Enrutado mínimo por pathname (SPEC-0002 plan): lógica pura para probarla con node --test.

export type Pagina = "estado" | "triada" | "secretos" | "egresos" | "no_encontrada";

export function paginaDe(ruta: string): Pagina {
  const limpia = ruta.replace(/\/+$/, "") || "/";
  if (limpia === "/") return "estado";
  if (limpia === "/modulos/triada") return "triada";
  if (limpia === "/modulos/secretos") return "secretos";
  if (limpia === "/modulos/egresos") return "egresos";
  return "no_encontrada";
}
