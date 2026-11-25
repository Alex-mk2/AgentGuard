import { Estado } from "./paginas/Estado.tsx";
import { Triada } from "./paginas/Triada.tsx";
import { paginaDe } from "./rutas.ts";

/** Dos páginas: se eligen por la ruta (SPEC-0002 plan, sin react-router). El backend entrega
 * index.html en cualquier ruta que no sea de la API, así que recargar funciona (SPEC-0001 E13). */
export function App() {
  const pagina = paginaDe(window.location.pathname);
  return (
    <main className="pagina">
      <header className="cabecera">
        <h1>
          <a href="/">AgentGuard</a>
        </h1>
        <p className="subtitulo">Seguridad en tiempo de ejecución para agentes de IA</p>
      </header>
      {pagina === "triada" ? <Triada /> : pagina === "estado" ? <Estado /> : <NoEncontrada />}
    </main>
  );
}

function NoEncontrada() {
  return (
    <section className="tarjeta">
      <h2>Página no encontrada</h2>
      <p>
        <a href="/">Volver al estado del sistema</a>
      </p>
    </section>
  );
}
