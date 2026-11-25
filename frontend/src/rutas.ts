// Enrutado mínimo por pathname (SPEC-0002 plan): lógica pura para probarla con node --test.

export type Pagina = "estado" | "triada" | "no_encontrada";

export function paginaDe(ruta: string): Pagina {
  const limpia = ruta.replace(/\/+$/, "") || "/";
  if (limpia === "/") return "estado";
  if (limpia === "/modulos/triada") return "triada";
  return "no_encontrada";
}
