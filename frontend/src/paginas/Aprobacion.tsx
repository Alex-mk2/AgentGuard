import { useState } from "react";
import type { FormEvent } from "react";

import { enviar, obtener } from "../api/cliente.ts";
import {
  cuerpoDecision,
  decididas,
  esRiesgosa,
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

  return (
    <>
      <p>
        <a href="/">← Estado del sistema</a>
      </p>
      <section aria-labelledby="titulo-aprobacion" className="tarjeta">
        <h2 id="titulo-aprobacion">Human-in-the-Loop</h2>
        <p className="ayuda">
          Las acciones irreversibles, las que tocan el plano de control y las de una sesión contaminada esperan aquí
          una decisión. Una aprobación vale una sola vez y solo para esa acción exacta; si nadie decide, vence y se
          niega.
        </p>
        <form onSubmit={consultar} className="acciones">
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
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>

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
      <section className="tarjeta" role="status" aria-labelledby="titulo-bandeja">
        <h2 id="titulo-bandeja">{resumenBandeja(solicitudes)}</h2>
        {estado?.avisos.map((aviso) => (
          <p key={aviso} className="aviso">
            {aviso}
          </p>
        ))}
        {estado && (
          <p className="ayuda">
            Se decide en {estado.minutos_decision} min; aprobada, el agente tiene {estado.minutos_boleto} min para
            reintentar.{" "}
            {estado.notificar ? (
              <>
                Avisos por <code>{estado.notificar}</code>.
              </>
            ) : (
              "Sin aviso por webhook."
            )}
          </p>
        )}
      </section>

      {abiertas.map((solicitud) => (
        <TarjetaPendiente key={solicitud.id} solicitud={solicitud} decidir={decidir} />
      ))}

      {cerradas.length > 0 && (
        <section className="tarjeta" aria-labelledby="titulo-decididas">
          <h2 id="titulo-decididas">Últimas decididas</h2>
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Agente</th>
                <th scope="col">Acción</th>
                <th scope="col">Estado</th>
                <th scope="col">Nota</th>
              </tr>
            </thead>
            <tbody>
              {cerradas.map((solicitud) => (
                <tr key={solicitud.id}>
                  <td>
                    <code>{solicitud.agente}</code>
                  </td>
                  <td>
                    {solicitud.metodo} <code>{solicitud.destino}</code>
                  </td>
                  <td>{nombreEstado(solicitud.estado)}</td>
                  <td>{solicitud.nota ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
  const idNota = `nota-${solicitud.id}`;

  async function responder(decision: Decision) {
    setEnviando(true);
    setError(await decidir(solicitud.id, decision, nota));
    setEnviando(false);
  }

  return (
    <section className="tarjeta" aria-label={`Solicitud de ${solicitud.agente}`}>
      <h3>
        <code>{solicitud.agente}</code> pide {solicitud.metodo} <code>{solicitud.destino}</code>
      </h3>
      <p>
        {nombreMotivo(solicitud)} · sesión <code>{solicitud.sesion}</code> ·{" "}
        {tiempoRestante(solicitud.vence, new Date())}
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
      <h4>Parámetros</h4>
      {parametrosVisibles(solicitud.parametros).length > 0 ? (
        <dl>
          {parametrosVisibles(solicitud.parametros).map(([clave, valor]) => (
            <div key={clave}>
              <dt>
                <code>{clave}</code>
              </dt>
              <dd>
                <pre className="manifiesto">{valor}</pre>
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>Sin parámetros.</p>
      )}
      <label htmlFor={idNota}>Nota (opcional)</label>
      <input
        id={idNota}
        className="campo"
        maxLength={MAX_NOTA}
        value={nota}
        onChange={(evento) => setNota(evento.target.value)}
      />
      <div className="acciones">
        <button type="button" className="principal" disabled={enviando} onClick={() => void responder("aprobar")}>
          Aprobar una vez
        </button>
        <button type="button" className="boton" disabled={enviando} onClick={() => void responder("negar")}>
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
