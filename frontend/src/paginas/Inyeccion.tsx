import { useState } from "react";
import type { FormEvent } from "react";

import { obtener } from "../api/cliente.ts";
import {
  interpretarInyeccion,
  nombreModo,
  nombreOrigen,
  nombreRegla,
  resumenInyeccion,
  sesionesOrdenadas,
} from "../inyeccion.ts";
import type { EstadoInyeccion } from "../inyeccion.ts";
import { cabeceraAdmin } from "../secretos.ts";

/** Contención de prompt injection (SPEC-0005 E12, E13). El token vive solo en este componente. */
export function Inyeccion() {
  const [token, setToken] = useState("");
  const [estado, setEstado] = useState<EstadoInyeccion | null>(null);
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
    const resultado = interpretarInyeccion(await obtener("/inyeccion/estado", cabeceras));
    setConsultando(false);
    setEstado(resultado.ok ? resultado.estado : null);
    setError(resultado.ok ? null : resultado.error);
  }

  return (
    <>
      <p>
        <a href="/">← Estado del sistema</a>
      </p>
      <section aria-labelledby="titulo-inyeccion" className="tarjeta">
        <h2 id="titulo-inyeccion">Contención de prompt injection</h2>
        <p className="ayuda">
          Todo contenido externo que entra al contexto de un agente contamina su sesión, y una sesión
          contaminada pierde las acciones con efecto, se haya detectado la inyección o no. Las reglas
          quitan lo invisible y marcan lo que parece una instrucción. Aquí se ve qué se contuvo, nunca el
          contenido.
        </p>
        <form onSubmit={(evento) => void consultar(evento)} className="acciones">
          <label htmlFor="token-admin-inyeccion" className="oculto">
            Token de administración
          </label>
          <input
            id="token-admin-inyeccion"
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

      {estado && <VistaInyeccion estado={estado} />}
    </>
  );
}

function VistaInyeccion({ estado }: { estado: EstadoInyeccion }) {
  const sesiones = sesionesOrdenadas(estado.sesiones);
  const confiables = Object.entries(estado.origenes_confiables).filter(([, origenes]) => origenes.length > 0);
  return (
    <section className="tarjeta" role="status" aria-labelledby="titulo-estado-inyeccion">
      <h2 id="titulo-estado-inyeccion">{resumenInyeccion(estado)}</h2>
      {estado.error && (
        <p className="error">
          Configuración inválida, la contención sigue con los valores por defecto: {estado.error}
        </p>
      )}
      {estado.avisos.map((aviso) => (
        <p key={aviso} className="aviso">
          {aviso}
        </p>
      ))}

      <h3>Sesiones</h3>
      {sesiones.length > 0 ? (
        <table className="tabla">
          <thead>
            <tr>
              <th scope="col">Sesión</th>
              <th scope="col">Agente</th>
              <th scope="col">Estado</th>
              <th scope="col">Contaminada por</th>
            </tr>
          </thead>
          <tbody>
            {sesiones.map((sesion) => (
              <tr key={sesion.id}>
                <td>
                  <code>{sesion.id}</code>
                  {sesion.acotada && " · acotada"}
                </td>
                <td>
                  <code>{sesion.agente}</code>
                </td>
                <td>{sesion.contaminada ? "Contaminada: solo lectura" : "Limpia"}</td>
                <td>{nombreOrigen(sesion.origen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>Ninguna activa.</p>
      )}
      <p className="ayuda">Una sesión se cierra por el runtime, por la administración o tras {estado.ttl_minutos} min sin uso.</p>

      <h3>Reglas de inspección</h3>
      <table className="tabla">
        <thead>
          <tr>
            <th scope="col">Regla</th>
            <th scope="col">Modo</th>
            <th scope="col">Detecciones</th>
          </tr>
        </thead>
        <tbody>
          {estado.reglas.map((regla) => (
            <tr key={regla.id}>
              <td>
                {nombreRegla(regla.id)} <code>{regla.id}</code>
              </td>
              <td>{nombreModo(regla.modo)}</td>
              <td>{regla.detecciones}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ayuda">
        {estado.marcadores} {estado.marcadores === 1 ? "marcador configurado" : "marcadores configurados"}. Los
        caracteres invisibles se eliminan siempre, sea cual sea el modo.
      </p>

      {confiables.length > 0 && (
        <>
          <h3>Orígenes confiables</h3>
          <ul>
            {confiables.map(([agente, origenes]) => (
              <li key={agente}>
                <code>{agente}</code>: {origenes.map((origen) => nombreOrigen(origen)).join(", ")}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
