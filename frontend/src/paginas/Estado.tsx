import { useCallback, useEffect, useState } from "react";

import { obtener } from "../api/cliente.ts";
import { Cifras, Ficha, Icono, TituloPagina } from "../componentes.tsx";
import { cifrasSistema, interpretarDependencias, interpretarVersion, tonoSistema } from "../estado.ts";
import type { EstadoSistema } from "../estado.ts";
import { MODULOS } from "../modulos.ts";
import { paginaDe } from "../rutas.ts";

/** Página de estado (SPEC-0001 H4): el panel de inicio. */
export function Estado() {
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
    <>
      <TituloPagina
        titulo="Estado del sistema"
        bajada={
          <>
            AgentGuard se interpone entre el agente y el mundo: rompe la Tríada Letal en cada punto en vez de confiar
            en que el modelo se porte bien.
            <span className={`linea-estado tono-${tonoSistema(estado)}`} role="status">
              <span className="punto" aria-hidden="true" />
              {estado?.mensaje ?? "Consultando la API…"}
            </span>
          </>
        }
      >
        <button type="button" onClick={() => void comprobar()} disabled={estado === null}>
          {estado === null ? "Comprobando…" : "Comprobar de nuevo"}
        </button>
      </TituloPagina>

      <Cifras cifras={cifrasSistema(estado, version)} etiqueta="Estado del sistema" />

      <h2 className="rotulo">Módulos</h2>
      <ol className="panel-modulos">
        {MODULOS.map((modulo, i) => (
          <li key={modulo.id} className="panel-modulo">
            <div className="panel-modulo-cabecera">
              <span className="panel-modulo-icono">
                <Icono id={modulo.ruta ? paginaDe(modulo.ruta) : "estado"} />
              </span>
              <span className="mono suave">0{i + 1}</span>
              <Ficha tono={modulo.estado === "activo" ? "permitir" : "neutro"}>
                {modulo.estado === "activo" ? "Activo" : "Pendiente"}
              </Ficha>
            </div>
            <h3>{modulo.ruta ? <a href={modulo.ruta}>{modulo.nombre}</a> : modulo.nombre}</h3>
            <p>{modulo.descripcion}</p>
          </li>
        ))}
      </ol>
    </>
  );
}
