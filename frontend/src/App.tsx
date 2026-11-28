import { useEffect, useState } from "react";

import { obtener } from "./api/cliente.ts";
import { Escudo, Icono } from "./componentes.tsx";
import { interpretarVersion, semaforoApi } from "./estado.ts";
import type { Semaforo } from "./estado.ts";
import { MODULOS } from "./modulos.ts";
import { Aprobacion } from "./paginas/Aprobacion.tsx";
import { Egresos } from "./paginas/Egresos.tsx";
import { Estado } from "./paginas/Estado.tsx";
import { Inyeccion } from "./paginas/Inyeccion.tsx";
import { Secretos } from "./paginas/Secretos.tsx";
import { Triada } from "./paginas/Triada.tsx";
import { paginaDe } from "./rutas.ts";
import type { Pagina } from "./rutas.ts";

/** Una página por módulo: se elige por la ruta (SPEC-0002 plan, sin react-router). El backend entrega
 * index.html en cualquier ruta que no sea de la API, así que recargar funciona (SPEC-0001 E13). */
export function App() {
  const pagina = paginaDe(window.location.pathname);
  return (
    <div className="armazon">
      <Menu actual={pagina} />
      <main className="pagina">
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
    </div>
  );
}

const MODULOS_MENU = MODULOS.flatMap((modulo) =>
  modulo.ruta ? [{ id: paginaDe(modulo.ruta), ruta: modulo.ruta, texto: modulo.corto }] : [],
);

function Menu({ actual }: { actual: Pagina }) {
  const [api, setApi] = useState<Semaforo>("desconocido");
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([obtener("/health"), obtener("/version")]).then(([salud, respuestaVersion]) => {
      setApi(semaforoApi(salud));
      setVersion(interpretarVersion(respuestaVersion));
    });
  }, []);

  return (
    <aside className="menu">
      <a className="marca" href="/">
        <Escudo clase="marca-icono" />
        <span>
          <span className="marca-nombre">AgentGuard</span>
          <span className="marca-lema">Seguridad para agentes de IA</span>
        </span>
      </a>
      <nav aria-label="Navegación principal" className="menu-nav">
        <ul className="menu-lista">
          <Entrada id="estado" ruta="/" texto="Estado" actual={actual} />
        </ul>
        <p className="menu-rotulo" id="rotulo-modulos">
          Módulos
        </p>
        <ul className="menu-lista" aria-labelledby="rotulo-modulos">
          {MODULOS_MENU.map((entrada) => (
            <Entrada key={entrada.id} {...entrada} actual={actual} />
          ))}
        </ul>
      </nav>
      <p className={`menu-pie tono-${TONO_API[api]}`}>
        <span className="punto" aria-hidden="true" />
        <span>{TEXTO_API[api]}</span>
        {version && <span className="mono">v{version}</span>}
      </p>
    </aside>
  );
}

const TONO_API: Record<Semaforo, string> = { ok: "permitir", caida: "bloquear", desconocido: "neutro" };
const TEXTO_API: Record<Semaforo, string> = { ok: "API en línea", caida: "API sin respuesta", desconocido: "API sin datos" };

function Entrada({ id, ruta, texto, actual }: { id: Pagina; ruta: string; texto: string; actual: Pagina }) {
  return (
    <li>
      <a className="menu-entrada" href={ruta} aria-current={id === actual ? "page" : undefined}>
        <Icono id={id} clase="menu-icono" />
        {texto}
      </a>
    </li>
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
