import { useState } from "react";

import { obtener } from "../api/cliente.ts";
import { AccesoAdmin, Cifras, Esqueleto, Ficha, TituloPagina, Vacio } from "../componentes.tsx";
import {
  cifrasInyeccion,
  interpretarInyeccion,
  nombreModo,
  nombreOrigen,
  nombreRegla,
  resumenInyeccion,
  sesionesOrdenadas,
  tonoModo,
} from "../inyeccion.ts";
import type { EstadoInyeccion } from "../inyeccion.ts";
import { cabeceraAdmin } from "../secretos.ts";

/** Contención de prompt injection (SPEC-0005 E12, E13). El token vive solo en este componente. */
export function Inyeccion() {
  const [token, setToken] = useState("");
  const [estado, setEstado] = useState<EstadoInyeccion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consultando, setConsultando] = useState(false);

  async function consultar() {
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
      <TituloPagina
        titulo="Contención de prompt injection"
        bajada="Todo contenido externo que entra al contexto de un agente contamina su sesión, y una sesión contaminada pierde las acciones con efecto, se haya detectado la inyección o no. Aquí se ve qué se contuvo, nunca el contenido."
      >
        <AccesoAdmin
          id="token-admin-inyeccion"
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
        <VistaInyeccion estado={estado} />
      ) : consultando ? (
        <Esqueleto />
      ) : (
        !error && (
          <Vacio icono="inyeccion" titulo="Ingresa el token para ver la contención">
            Sesiones activas, cuáles quedaron contaminadas y qué detectó cada regla.
          </Vacio>
        )
      )}
    </>
  );
}

function VistaInyeccion({ estado }: { estado: EstadoInyeccion }) {
  const sesiones = sesionesOrdenadas(estado.sesiones);
  const confiables = Object.entries(estado.origenes_confiables).filter(([, origenes]) => origenes.length > 0);
  return (
    <div role="status" aria-label={resumenInyeccion(estado)}>
      {estado.error && (
        <p className="error">Configuración inválida, la contención sigue con los valores por defecto: {estado.error}</p>
      )}
      {estado.avisos.map((aviso) => (
        <p key={aviso} className="aviso">
          {aviso}
        </p>
      ))}

      <Cifras cifras={cifrasInyeccion(estado)} etiqueta="Resumen de la contención" />

      <section className="tarjeta" aria-labelledby="titulo-sesiones">
        <h2 id="titulo-sesiones">Sesiones</h2>
        {sesiones.length > 0 ? (
          <div className="tabla-contenedor">
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
                      <span className="mono">{sesion.id}</span>
                      {sesion.acotada && <span className="suave"> · acotada</span>}
                    </td>
                    <td>
                      <span className="agente">{sesion.agente}</span>
                    </td>
                    <td>
                      <Ficha tono={sesion.contaminada ? "alerta" : "permitir"}>
                        {sesion.contaminada ? "Contaminada: solo lectura" : "Limpia"}
                      </Ficha>
                    </td>
                    <td className="suave">{sesion.contaminada ? nombreOrigen(sesion.origen) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Vacio icono="escudo" titulo="Ninguna sesión activa">
            El runtime abre una por conversación con <code>POST /api/v1/inyeccion/sesiones</code>.
          </Vacio>
        )}
        <p className="ayuda nota-pie">
          Una sesión se cierra por el runtime, por la administración o tras {estado.ttl_minutos} min sin uso.
        </p>
      </section>

      <div className="columnas">
        <section className="tarjeta" aria-labelledby="titulo-reglas">
          <h2 id="titulo-reglas">Reglas de inspección</h2>
          <ul className="lista-filas">
            {estado.reglas.map((regla) => (
              <li key={regla.id}>
                <div className="lista-fila-cabecera">
                  <span>{nombreRegla(regla.id)}</span>
                  <span className="mono suave">{regla.detecciones}</span>
                  <Ficha tono={tonoModo(regla.modo)}>{nombreModo(regla.modo)}</Ficha>
                </div>
                <p className="evidencia mono">{regla.id}</p>
              </li>
            ))}
          </ul>
          <p className="ayuda nota-pie">
            {estado.marcadores} {estado.marcadores === 1 ? "marcador configurado" : "marcadores configurados"}. Los
            caracteres invisibles se eliminan siempre, sea cual sea el modo.
          </p>
        </section>

        <section className="tarjeta" aria-labelledby="titulo-confiables">
          <h2 id="titulo-confiables">Orígenes confiables</h2>
          {confiables.length > 0 ? (
            <ul className="lista-filas">
              {confiables.map(([agente, origenes]) => (
                <li key={agente}>
                  <div className="lista-fila-cabecera">
                    <span className="agente">{agente}</span>
                  </div>
                  <p className="evidencia">{origenes.map((origen) => nombreOrigen(origen)).join(" · ")}</p>
                </li>
              ))}
            </ul>
          ) : (
            <Vacio icono="inyeccion" titulo="Ninguno">
              Todo lo que entra contamina la sesión: es lo más seguro.
            </Vacio>
          )}
        </section>
      </div>
    </div>
  );
}
