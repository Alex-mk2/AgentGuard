import { Aprobacion } from "./paginas/Aprobacion.tsx";
import { Egresos } from "./paginas/Egresos.tsx";
import { Estado } from "./paginas/Estado.tsx";
import { Inyeccion } from "./paginas/Inyeccion.tsx";
import { Secretos } from "./paginas/Secretos.tsx";
import { Triada } from "./paginas/Triada.tsx";
import { paginaDe } from "./rutas.ts";

/** Una página por módulo: se elige por la ruta (SPEC-0002 plan, sin react-router). El backend entrega
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
      {pagina === "triada" ? (
        <Triada />
      ) : pagina === "secretos" ? (
        <Secretos />
      ) : pagina === "egresos" ? (
        <Egresos />
      ) : pagina === "inyeccion" ? (
        <Inyeccion />
      ) : pagina === "aprobacion" ? (
        <Aprobacion />
      ) : pagina === "estado" ? (
        <Estado />
      ) : (
        <NoEncontrada />
      )}
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
