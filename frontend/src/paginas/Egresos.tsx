import { useState } from "react";
import type { FormEvent } from "react";

import { obtener } from "../api/cliente.ts";
import { filasConteo, interpretarEgresos, nombreCausa, resumenEgresos } from "../egresos.ts";
import type { EstadoEgresos } from "../egresos.ts";
import { cabeceraAdmin, interpretarEstado } from "../secretos.ts";
import type { AccionEstado } from "../secretos.ts";

/** Control de egresos (SPEC-0004 E15, E16). Las acciones bloqueadas vienen de `/secretos/estado`,
 * porque el módulo de egresos no conoce el broker. El token vive solo en este componente. */
export function Egresos() {
  const [token, setToken] = useState("");
  const [estado, setEstado] = useState<EstadoEgresos | null>(null);
  const [bloqueadas, setBloqueadas] = useState<AccionEstado[]>([]);
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
    const [egresos, broker] = await Promise.all([
      obtener("/egresos/estado", cabeceras),
      obtener("/secretos/estado", cabeceras),
    ]);
    setConsultando(false);
    const resultado = interpretarEgresos(egresos);
    const delBroker = interpretarEstado(broker);
    if (resultado.ok) {
      setEstado(resultado.estado);
      setBloqueadas(delBroker.ok ? delBroker.estado.acciones.filter((a) => a.bloqueada_por_egresos) : []);
      setError(null);
    } else {
      setEstado(null);
      setBloqueadas([]);
      setError(resultado.error);
    }
  }

  return (
    <>
      <section aria-labelledby="titulo-egresos" className="tarjeta">
        <h2 id="titulo-egresos">Sealed Tools y control de egresos</h2>
        <p className="ayuda">
          Toda salida de red de AgentGuard pasa por una allowlist, un DLP sobre lo que escribe el agente y
          una verificación de que el destino resuelve a IP públicas. Aquí se ve qué está permitido y qué
          se bloqueó, nunca el contenido.
        </p>
        <form onSubmit={(evento) => void consultar(evento)} className="acciones">
          <label htmlFor="token-admin-egresos" className="oculto">
            Token de administración
          </label>
          <input
            id="token-admin-egresos"
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

      {estado && <VistaEgresos estado={estado} bloqueadas={bloqueadas} />}
    </>
  );
}

function VistaEgresos({ estado, bloqueadas }: { estado: EstadoEgresos; bloqueadas: AccionEstado[] }) {
  const bloqueos = filasConteo(estado.bloqueos);
  const observados = filasConteo(estado.observados);
  const web = Object.entries(estado.web);
  return (
    <section className="tarjeta" role="status" aria-labelledby="titulo-estado-egresos">
      <h2 id="titulo-estado-egresos">{resumenEgresos(estado)}</h2>
      {estado.error && <p className="error">{estado.error}</p>}
      {bloqueadas.length > 0 && (
        <p className="aviso">
          Acciones del broker con un host fuera de la allowlist:{" "}
          {bloqueadas.map((accion) => accion.id).join(", ")}.
        </p>
      )}

      <h3>Allowlist global</h3>
      {estado.allowlist.length > 0 ? (
        <ul>
          {estado.allowlist.map((entrada) => (
            <li key={entrada}>
              <code>{entrada}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p>Vacía: no sale nada.</p>
      )}

      {web.length > 0 && (
        <>
          <h3>Egreso web por agente</h3>
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Agente</th>
                <th scope="col">Hosts permitidos</th>
              </tr>
            </thead>
            <tbody>
              {web.map(([agente, hosts]) => (
                <tr key={agente}>
                  <td>
                    <code>{agente}</code>
                  </td>
                  <td>{hosts.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>Reglas DLP</h3>
      <table className="tabla">
        <thead>
          <tr>
            <th scope="col">Regla</th>
            <th scope="col">Modo</th>
          </tr>
        </thead>
        <tbody>
          {estado.reglas.map((regla) => (
            <tr key={regla.id}>
              <td>
                {nombreCausa(regla.id)} <code>{regla.id}</code>
              </td>
              <td>{regla.modo === "bloquear" ? "Bloquea" : "Solo observa"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ayuda">
        {estado.marcadores} {estado.marcadores === 1 ? "marcador configurado" : "marcadores configurados"}.
      </p>

      <h3>Bloqueos desde el arranque</h3>
      {bloqueos.length > 0 ? <Conteo filas={bloqueos} /> : <p>Ninguno.</p>}
      {observados.length > 0 && (
        <>
          <h3>Observados (no bloqueados)</h3>
          <Conteo filas={observados} />
        </>
      )}
    </section>
  );
}

function Conteo({ filas }: { filas: { causa: string; veces: number }[] }) {
  return (
    <table className="tabla">
      <thead>
        <tr>
          <th scope="col">Causa</th>
          <th scope="col">Veces</th>
        </tr>
      </thead>
      <tbody>
        {filas.map((fila) => (
          <tr key={fila.causa}>
            <td>{fila.causa}</td>
            <td>{fila.veces}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
