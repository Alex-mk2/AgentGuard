import { useState } from "react";

import { obtener } from "../api/cliente.ts";
import { AccesoAdmin, Cifras, Esqueleto, Ficha, TituloPagina, Vacio } from "../componentes.tsx";
import { cabeceraAdmin, cifrasBroker, estadoAccion, interpretarEstado, resumen, tonoAccion } from "../secretos.ts";
import type { EstadoBroker } from "../secretos.ts";

/** Estado del Secret Broker (SPEC-0003 E11, E13). El token de administración vive solo en este
 * componente: no se guarda en localStorage ni en la URL. Nunca se muestran valores de secretos. */
export function Secretos() {
  const [token, setToken] = useState("");
  const [estado, setEstado] = useState<EstadoBroker | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consultando, setConsultando] = useState(false);

  async function consultar() {
    const cabeceras = cabeceraAdmin(token);
    if (!cabeceras) {
      setError("Ingresa el token de administración.");
      return;
    }
    setConsultando(true);
    const resultado = interpretarEstado(await obtener("/secretos/estado", cabeceras));
    setConsultando(false);
    if (resultado.ok) {
      setEstado(resultado.estado);
      setError(null);
    } else {
      setEstado(null);
      setError(resultado.error);
    }
  }

  return (
    <>
      <TituloPagina
        titulo="Secret Broker"
        bajada="El agente pide una acción por su nombre y AgentGuard inyecta la credencial al ejecutarla: el modelo nunca la ve. Aquí se ven acciones, agentes y qué secretos están cargados, nunca sus valores."
      >
        <AccesoAdmin
          id="token-admin"
          token={token}
          setToken={setToken}
          consultando={consultando}
          cargado={estado !== null}
          alEnviar={() => void consultar()}
        />
      </TituloPagina>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {estado ? (
        <VistaEstado estado={estado} />
      ) : consultando ? (
        <Esqueleto />
      ) : (
        !error && (
          <Vacio icono="secretos" titulo="Ingresa el token para ver el broker">
            Solo verás nombres y estados: los valores de los secretos nunca salen de AgentGuard.
          </Vacio>
        )
      )}
    </>
  );
}

function VistaEstado({ estado }: { estado: EstadoBroker }) {
  return (
    <div role="status" aria-label={resumen(estado)}>
      {estado.error && <p className="error">{estado.error}</p>}
      {estado.avisos.map((aviso) => (
        <p key={aviso} className="aviso">
          {aviso}
        </p>
      ))}

      {!estado.configurado ? (
        <Vacio icono="secretos" titulo="El Secret Broker no está configurado">
          Sin <code>SECRETOS_CONFIG</code> no hay acciones que ejecutar.
        </Vacio>
      ) : (
        <>
          <Cifras cifras={cifrasBroker(estado)} etiqueta="Resumen del broker" />

          <section className="tarjeta" aria-labelledby="titulo-acciones">
            <h2 id="titulo-acciones">Acciones</h2>
            <div className="tabla-contenedor">
              <table className="tabla">
                <thead>
                  <tr>
                    <th scope="col">Acción</th>
                    <th scope="col">Destino</th>
                    <th scope="col">Secreto</th>
                    <th scope="col">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {estado.acciones.map((accion) => (
                    <tr key={accion.id}>
                      <td>
                        <span className="mono">{accion.id}</span>
                        {accion.descripcion && <div className="evidencia">{accion.descripcion}</div>}
                      </td>
                      <td className="mono suave">{accion.host ?? "—"}</td>
                      <td>
                        {accion.secreto ? (
                          <span className="mono">{accion.secreto}</span>
                        ) : (
                          <span className="suave">sin credencial</span>
                        )}
                      </td>
                      <td>
                        <Ficha tono={tonoAccion(accion)}>{estadoAccion(accion)}</Ficha>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="columnas">
            <section className="tarjeta" aria-labelledby="titulo-agentes">
              <h2 id="titulo-agentes">Agentes</h2>
              <ul className="lista-filas">
                {estado.agentes.map((agente) => (
                  <li key={agente.id}>
                    <div className="lista-fila-cabecera">
                      <span className="agente">{agente.id}</span>
                      <span className="mono suave">{agente.max_por_minuto}/min</span>
                      <Ficha tono={agente.token_cargado ? "permitir" : "alerta"}>
                        {agente.token_cargado ? "Token cargado" : "Falta el token"}
                      </Ficha>
                    </div>
                    <p className="evidencia">
                      {agente.acciones.length ? agente.acciones.join(" · ") : "sin acciones permitidas"}
                    </p>
                  </li>
                ))}
              </ul>
            </section>

            <section className="tarjeta" aria-labelledby="titulo-secretos-lista">
              <h2 id="titulo-secretos-lista">Secretos</h2>
              <ul className="lista-filas">
                {estado.secretos.map((secreto) => (
                  <li key={secreto.nombre}>
                    <div className="lista-fila-cabecera">
                      <span className="mono">{secreto.nombre}</span>
                      {secreto.compartido && <Ficha tono="neutro">compartido</Ficha>}
                      <Ficha tono={secreto.cargado ? "permitir" : "alerta"}>
                        {secreto.cargado ? "Cargado" : "Falta"}
                      </Ficha>
                    </div>
                    <p className="evidencia">{secreto.acciones.join(" · ")}</p>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
