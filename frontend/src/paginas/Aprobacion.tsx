import { useState } from "react";

import { enviar, obtener } from "../api/cliente.ts";
import { AccesoAdmin, Cifras, Esqueleto, Ficha, TituloPagina, Vacio } from "../componentes.tsx";
import {
  cifras,
  cuerpoDecision,
  decididas,
  esRiesgosa,
  estadoPuerta,
  horaDe,
  interpretarDecision,
  interpretarEstado,
  interpretarSolicitudes,
  MAX_NOTA,
  nombreEstado,
  nombreMotivo,
  parametrosVisibles,
  pendientes,
  resumenBandeja,
  tiempoRestante,
  tonoEstado,
} from "../aprobacion.ts";
import type { Decision, EstadoAprobacion, Solicitud } from "../aprobacion.ts";
import { nombreRegla } from "../inyeccion.ts";
import { cabeceraAdmin } from "../secretos.ts";

/** Bandeja de aprobación humana (SPEC-0006 E5–E7, E15). El token vive solo en este componente. */
export function Aprobacion() {
  const [token, setToken] = useState("");
  const [solicitudes, setSolicitudes] = useState<Solicitud[] | null>(null);
  const [estado, setEstado] = useState<EstadoAprobacion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consultando, setConsultando] = useState(false);

  async function cargar(): Promise<void> {
    const cabeceras = cabeceraAdmin(token);
    if (!cabeceras) {
      setError("Ingresa el token de administración.");
      return;
    }
    setConsultando(true);
    const [bandeja, resumen] = await Promise.all([
      obtener("/aprobacion/solicitudes", cabeceras),
      obtener("/aprobacion/estado", cabeceras),
    ]);
    setConsultando(false);
    const lista = interpretarSolicitudes(bandeja);
    const datos = interpretarEstado(resumen);
    setSolicitudes(lista.ok ? lista.valor : null);
    setEstado(datos.ok ? datos.valor : null);
    setError(lista.ok ? null : lista.error);
  }

  async function decidir(id: string, decision: Decision, nota: string): Promise<string | null> {
    const cabeceras = cabeceraAdmin(token);
    if (!cabeceras) return "Ingresa el token de administración.";
    const resultado = interpretarDecision(
      await enviar(`/aprobacion/solicitudes/${encodeURIComponent(id)}/decision`, cuerpoDecision(decision, nota), cabeceras),
    );
    await cargar();
    return resultado.ok ? null : resultado.error;
  }

  const puerta = solicitudes ? estadoPuerta(estado) : null;

  return (
    <>
      <TituloPagina
        titulo="Aprobación humana"
        bajada={
          <>
            Las acciones irreversibles, las que tocan el plano de control y las de una sesión contaminada esperan
            aquí una decisión. Una aprobación vale una sola vez y solo para esa acción exacta; si nadie decide, vence
            y se niega.
            {puerta && (
              <span className={`linea-estado tono-${puerta.tono}`}>
                <span className="punto" aria-hidden="true" />
                {puerta.texto}
              </span>
            )}
          </>
        }
      >
        <AccesoAdmin
          id="token-admin-aprobacion"
          token={token}
          setToken={setToken}
          consultando={consultando}
          cargado={solicitudes !== null}
          alEnviar={() => void cargar()}
        />
      </TituloPagina>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {solicitudes ? (
        <Bandeja solicitudes={solicitudes} estado={estado} decidir={decidir} />
      ) : consultando ? (
        <Esqueleto filas={4} />
      ) : (
        !error && (
          <Vacio icono="aprobacion" titulo="Ingresa el token para ver la bandeja">
            Aquí esperan las acciones que necesitan que una persona las apruebe o las niegue.
          </Vacio>
        )
      )}
    </>
  );
}

interface PropsBandeja {
  solicitudes: Solicitud[];
  estado: EstadoAprobacion | null;
  decidir: (id: string, decision: Decision, nota: string) => Promise<string | null>;
}

function Bandeja({ solicitudes, estado, decidir }: PropsBandeja) {
  const abiertas = pendientes(solicitudes);
  const cerradas = decididas(solicitudes);
  return (
    <>
      <Cifras cifras={cifras(estado, solicitudes)} etiqueta="Resumen de solicitudes" />

      {estado?.avisos.map((aviso) => (
        <p key={aviso} className="aviso">
          {aviso}
        </p>
      ))}

      <div className="seccion-cabecera">
        <h2 role="status">{resumenBandeja(solicitudes)}</h2>
        {estado && (
          <p className="ayuda">
            Se decide en {estado.minutos_decision} min · aprobada, el agente tiene {estado.minutos_boleto} min para
            reintentar ·{" "}
            {estado.notificar ? (
              <>
                avisos por <code>{estado.notificar}</code>
              </>
            ) : (
              "sin aviso por webhook"
            )}
          </p>
        )}
      </div>

      {abiertas.length > 0 ? (
        abiertas.map((solicitud) => <TarjetaPendiente key={solicitud.id} solicitud={solicitud} decidir={decidir} />)
      ) : (
        <Vacio icono="escudo" titulo="Nada espera tu decisión">
          Cuando un agente intente una acción que necesita aprobación, aparecerá aquí.
        </Vacio>
      )}

      {cerradas.length > 0 && (
        <section className="tarjeta" aria-labelledby="titulo-decididas">
          <h2 id="titulo-decididas">Últimas decididas</h2>
          <div className="tabla-contenedor">
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col">Hora</th>
                  <th scope="col">Agente</th>
                  <th scope="col">Acción</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Nota</th>
                </tr>
              </thead>
              <tbody>
                {cerradas.map((solicitud) => (
                  <tr key={solicitud.id}>
                    <td className="mono suave">{horaDe(solicitud)}</td>
                    <td>
                      <span className="agente">{solicitud.agente}</span>
                    </td>
                    <td className="mono">
                      <span className="metodo">{solicitud.metodo}</span> {solicitud.destino}
                    </td>
                    <td>
                      <Ficha tono={tonoEstado(solicitud.estado)}>{nombreEstado(solicitud.estado)}</Ficha>
                    </td>
                    <td className="suave">{solicitud.nota ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

function TarjetaPendiente({ solicitud, decidir }: { solicitud: Solicitud; decidir: PropsBandeja["decidir"] }) {
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const senales = Object.entries(solicitud.senales);
  const parametros = parametrosVisibles(solicitud.parametros);
  const idNota = `nota-${solicitud.id}`;

  async function responder(decision: Decision) {
    setEnviando(true);
    setError(await decidir(solicitud.id, decision, nota));
    setEnviando(false);
  }

  return (
    <section className="tarjeta pendiente" aria-label={`Solicitud de ${solicitud.agente}`}>
      <div className="pendiente-cabecera">
        <h3>
          <span className="agente">{solicitud.agente}</span>
          <span className="metodo">{solicitud.metodo}</span>
          <span className="mono">{solicitud.destino}</span>
        </h3>
        <span className="mono suave">{tiempoRestante(solicitud.vence, new Date())}</span>
      </div>

      <p className="fichas">
        <Ficha tono="alerta">{nombreMotivo(solicitud)}</Ficha>
        <Ficha tono="neutro">
          sesión <span className="mono">{solicitud.sesion}</span>
        </Ficha>
      </p>

      {esRiesgosa(solicitud) && (
        <p className="aviso">
          Esta sesión leyó contenido no confiable. Los parámetros pueden venir de una inyección: revísalos como datos,
          no como instrucciones.
        </p>
      )}
      {senales.length > 0 && (
        <p className="ayuda">
          Señales vistas en la sesión:{" "}
          {senales.map(([regla, conteo]) => `${nombreRegla(regla)} (${conteo})`).join(", ")}
        </p>
      )}

      <h4 className="rotulo">Parámetros</h4>
      {parametros.length > 0 ? (
        <dl className="parametros">
          {parametros.map(([clave, valor]) => (
            <div key={clave}>
              <dt className="mono">{clave}</dt>
              <dd>
                <pre className="manifiesto">{valor}</pre>
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="suave">Sin parámetros.</p>
      )}

      <div className="decision">
        <label htmlFor={idNota} className="oculto">
          Nota (opcional)
        </label>
        <input
          id={idNota}
          className="campo"
          maxLength={MAX_NOTA}
          placeholder="Nota (opcional)"
          value={nota}
          onChange={(evento) => setNota(evento.target.value)}
        />
        <button type="button" className="aprobar" disabled={enviando} onClick={() => void responder("aprobar")}>
          Aprobar una vez
        </button>
        <button type="button" className="negar" disabled={enviando} onClick={() => void responder("negar")}>
          Negar
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
