import { useEffect, useState } from "react";

import { obtener } from "./api/cliente.ts";
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
        <Escudo />
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
        <Icono id={id} />
        {texto}
      </a>
    </li>
  );
}

/** Íconos de línea (24×24, trazo), dibujados a mano: sin librería de íconos. */
const TRAZOS: Partial<Record<Pagina, readonly string[]>> = {
  estado: ["M3 12h4l3-8 4 16 3-8h4"],
  triada: ["M12 3.5 2.8 19.5h18.4Z", "M12 10v4", "M12 16.8v.2"],
  secretos: ["M7.5 19a4.5 4.5 0 1 1 3.6-7.2", "M11.1 11.8 20 3", "M16.5 6.5l2.5 2.5", "M14 9l2 2"],
  egresos: ["M14 4h6v6", "M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  inyeccion: ["M3.5 4.5h17l-6.5 7.5v6l-4 2v-8Z"],
  aprobacion: ["M9 11.5a3.75 3.75 0 1 0 0-7.5 3.75 3.75 0 0 0 0 7.5Z", "M2.5 20.5c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6", "m16 11 2 2 4-4"],
};

function Icono({ id }: { id: Pagina }) {
  return (
    <svg className="menu-icono" viewBox="0 0 24 24" aria-hidden="true">
      {(TRAZOS[id] ?? []).map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

function Escudo() {
  return (
    <svg className="marca-icono" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.5 4 5.5v6c0 4.9 3.4 8.6 8 10 4.6-1.4 8-5.1 8-10v-6l-8-3Z" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </svg>
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
