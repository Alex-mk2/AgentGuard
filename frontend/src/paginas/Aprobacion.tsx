import { useState } from "react";
import type { FormEvent } from "react";

import { enviar, obtener } from "../api/cliente.ts";
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

  function consultar(evento: FormEvent) {
    evento.preventDefault();
    void cargar();
  }

  const puerta = solicitudes ? estadoPuerta(estado) : null;

  return (
    <>
      <header className="titulo-pagina">
        <div>
          <h1>Aprobación humana</h1>
          {puerta && (
            <p className={`linea-estado tono-${puerta.tono}`}>
              <span className="punto" aria-hidden="true" />
              {puerta.texto}
            </p>
          )}
        </div>
        <form onSubmit={consultar} className="acceso">
          <label htmlFor="token-admin-aprobacion" className="oculto">
            Token de administración
          </label>
          <input
            id="token-admin-aprobacion"
            type="password"
            className="campo"
            autoComplete="off"
            placeholder="Token de administración"
            value={token}
            onChange={(evento) => setToken(evento.target.value)}
          />
          <button type="submit" className="principal" disabled={consultando}>
            {consultando ? "Consultando…" : solicitudes ? "Actualizar" : "Consultar"}
          </button>
        </form>
      </header>

      <p className="ayuda">
        Las acciones irreversibles, las que tocan el plano de control y las de una sesión contaminada esperan aquí una
        decisión. Una aprobación vale una sola vez y solo para esa acción exacta; si nadie decide, vence y se niega.
      </p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {solicitudes && <Bandeja solicitudes={solicitudes} estado={estado} decidir={decidir} />}
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
      <ul className="cifras" aria-label="Resumen de solicitudes">
        {cifras(estado, solicitudes).map((cifra) => (
          <li key={cifra.id} className={`cifra tono-${cifra.tono}`}>
            <span className="cifra-titulo">{cifra.titulo}</span>
            <span className="cifra-valor">{cifra.valor}</span>
            <span className="cifra-detalle">{cifra.detalle}</span>
          </li>
        ))}
      </ul>

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

      {abiertas.map((solicitud) => (
        <TarjetaPendiente key={solicitud.id} solicitud={solicitud} decidir={decidir} />
      ))}

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
                      <span className={`ficha tono-${tonoEstado(solicitud.estado)}`}>
                        {nombreEstado(solicitud.estado)}
                      </span>
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
        <span className="ficha tono-alerta">{nombreMotivo(solicitud)}</span>
        <span className="ficha tono-neutro">
          sesión <span className="mono">{solicitud.sesion}</span>
        </span>
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
