import { useState } from "react";
import type { FormEvent } from "react";

import { obtener } from "../api/cliente.ts";
import { cabeceraAdmin, estadoAccion, interpretarEstado, resumen } from "../secretos.ts";
import type { EstadoBroker } from "../secretos.ts";

/** Estado del Secret Broker (SPEC-0003 E11, E13). El token de administración vive solo en este
 * componente: no se guarda en localStorage ni en la URL. Nunca se muestran valores de secretos. */
export function Secretos() {
  const [token, setToken] = useState("");
  const [estado, setEstado] = useState<EstadoBroker | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consultando, setConsultando] = useState(false);

  async function consultar(evento: FormEvent) {
    evento.preventDefault();
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
      <p>
        <a href="/">← Estado del sistema</a>
      </p>
      <section aria-labelledby="titulo-secretos" className="tarjeta">
        <h2 id="titulo-secretos">Secret Broker</h2>
        <p className="ayuda">
          El agente pide una acción por su nombre y AgentGuard inyecta la credencial al ejecutarla: el
          modelo nunca la ve. Aquí se ven las acciones, los agentes y qué secretos están cargados, nunca
          sus valores.
        </p>
        <form onSubmit={(evento) => void consultar(evento)} className="acciones">
          <label htmlFor="token-admin" className="oculto">
            Token de administración
          </label>
          <input
            id="token-admin"
            type="password"
            className="campo"
            autoComplete="off"
            placeholder="Token de administración"
            value={token}
            onChange={(evento) => setToken(evento.target.value)}
          />
          <button type="submit" className="principal" disabled={consultando}>
            {consultando ? "Consultando…" : "Consultar"}
          </button>
        </form>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>

      {estado && <VistaEstado estado={estado} />}
    </>
  );
}

function VistaEstado({ estado }: { estado: EstadoBroker }) {
  return (
    <section className="tarjeta" role="status" aria-labelledby="titulo-estado-broker">
      <h2 id="titulo-estado-broker">{resumen(estado)}</h2>
      {estado.error && <p className="error">{estado.error}</p>}
      {estado.avisos.map((aviso) => (
        <p key={aviso} className="aviso">
          {aviso}
        </p>
      ))}

      {estado.configurado && (
        <>
          <h3>Acciones</h3>
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
                    <code>{accion.id}</code>
                    {accion.descripcion && <div className="evidencia">{accion.descripcion}</div>}
                  </td>
                  <td>{accion.host ?? "—"}</td>
                  <td>{accion.secreto ? <code>{accion.secreto}</code> : "sin credencial"}</td>
                  <td>{estadoAccion(accion)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Agentes</h3>
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Agente</th>
                <th scope="col">Acciones permitidas</th>
                <th scope="col">Límite</th>
                <th scope="col">Token</th>
              </tr>
            </thead>
            <tbody>
              {estado.agentes.map((agente) => (
                <tr key={agente.id}>
                  <td>
                    <code>{agente.id}</code>
                  </td>
                  <td>{agente.acciones.join(", ") || "ninguna"}</td>
                  <td>{agente.max_por_minuto}/min</td>
                  <td>{agente.token_cargado ? "Cargado" : "Falta"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Secretos</h3>
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Nombre</th>
                <th scope="col">Estado</th>
                <th scope="col">Lo usan</th>
              </tr>
            </thead>
            <tbody>
              {estado.secretos.map((secreto) => (
                <tr key={secreto.nombre}>
                  <td>
                    <code>{secreto.nombre}</code>
                    {secreto.compartido && <span className="etiqueta">compartido</span>}
                  </td>
                  <td>{secreto.cargado ? "Cargado" : "Falta"}</td>
                  <td>{secreto.acciones.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
