import { useCallback, useEffect, useState } from "react";

import { obtener } from "./api/cliente.ts";
import { interpretarDependencias, interpretarVersion } from "./estado.ts";
import type { EstadoSistema, Semaforo } from "./estado.ts";
import { MODULOS } from "./modulos.ts";

const ETIQUETA: Record<Semaforo, string> = { ok: "En línea", caida: "Caído", desconocido: "Sin datos" };

function Indicador({ nombre, valor }: { nombre: string; valor: Semaforo | "cargando" }) {
  const texto = valor === "cargando" ? "Comprobando…" : ETIQUETA[valor];
  return (
    <li className="indicador">
      <span className={`punto punto-${valor}`} aria-hidden="true" />
      <span className="indicador-nombre">{nombre}</span>
      <span className="indicador-valor">{texto}</span>
    </li>
  );
}

export function App() {
  const [estado, setEstado] = useState<EstadoSistema | null>(null);
  const [version, setVersion] = useState<string | null>(null);

  const comprobar = useCallback(async () => {
    setEstado(null);
    const [dependencias, respuestaVersion] = await Promise.all([
      obtener("/health/dependencias"),
      obtener("/version"),
    ]);
    setEstado(interpretarDependencias(dependencias));
    setVersion(interpretarVersion(respuestaVersion));
  }, []);

  useEffect(() => {
    void comprobar();
  }, [comprobar]);

  return (
    <main className="pagina">
      <header className="cabecera">
        <h1>AgentGuard</h1>
        <p className="subtitulo">Seguridad en tiempo de ejecución para agentes de IA</p>
      </header>

      <section aria-labelledby="titulo-estado" className="tarjeta">
        <div className="tarjeta-cabecera">
          <h2 id="titulo-estado">Estado del sistema</h2>
          <button type="button" onClick={() => void comprobar()} disabled={estado === null}>
            Comprobar de nuevo
          </button>
        </div>
        <ul className="indicadores">
          <Indicador nombre="API" valor={estado?.api ?? "cargando"} />
          <Indicador nombre="PostgreSQL" valor={estado?.postgres ?? "cargando"} />
        </ul>
        <p className="mensaje" role="status">
          {estado?.mensaje ?? "Consultando la API…"}
        </p>
      </section>

      <section aria-labelledby="titulo-modulos" className="tarjeta">
        <h2 id="titulo-modulos">Módulos</h2>
        <ol className="modulos">
          {MODULOS.map((modulo) => (
            <li key={modulo.id} className="modulo">
              <div>
                <strong>{modulo.nombre}</strong>
                <p>{modulo.descripcion}</p>
              </div>
              <span className={`etiqueta etiqueta-${modulo.estado}`}>
                {modulo.estado === "pendiente" ? "Pendiente" : "Activo"}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <footer className="pie">{version ? `Versión ${version}` : ""}</footer>
    </main>
  );
}
