import { useState } from "react";

import { obtener } from "../api/cliente.ts";
import { AccesoAdmin, Cifras, Esqueleto, Ficha, TituloPagina, Vacio } from "../componentes.tsx";
import { cifrasEgresos, filasConteo, interpretarEgresos, nombreCausa, resumenEgresos, tonoModoDlp } from "../egresos.ts";
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

  async function consultar() {
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
      <TituloPagina
        titulo="Control de egresos"
        bajada="Toda salida de red pasa por una allowlist, un DLP sobre lo que escribe el agente y una verificación de que el destino resuelve a IP públicas. Aquí se ve qué está permitido y qué se bloqueó, nunca el contenido."
      >
        <AccesoAdmin
          id="token-admin-egresos"
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
        <VistaEgresos estado={estado} bloqueadas={bloqueadas} />
      ) : consultando ? (
        <Esqueleto />
      ) : (
        !error && (
          <Vacio icono="egresos" titulo="Ingresa el token para ver las salidas">
            Allowlist, reglas DLP y lo que se bloqueó desde el arranque.
          </Vacio>
        )
      )}
    </>
  );
}

function VistaEgresos({ estado, bloqueadas }: { estado: EstadoEgresos; bloqueadas: AccionEstado[] }) {
  const bloqueos = filasConteo(estado.bloqueos);
  const observados = filasConteo(estado.observados);
  const web = Object.entries(estado.web);
  return (
    <div role="status" aria-label={resumenEgresos(estado)}>
      {estado.error && <p className="error">{estado.error}</p>}
      {!estado.configurado && (
        <p className="aviso">Sin allowlist configurada: toda salida de red está bloqueada.</p>
      )}
      {bloqueadas.length > 0 && (
        <p className="aviso">
          Acciones del broker con un host fuera de la allowlist:{" "}
          {bloqueadas.map((accion) => accion.id).join(", ")}.
        </p>
      )}

      <Cifras cifras={cifrasEgresos(estado)} etiqueta="Resumen de egresos" />

      <div className="columnas">
        <section className="tarjeta" aria-labelledby="titulo-allowlist">
          <h2 id="titulo-allowlist">Allowlist global</h2>
          {estado.allowlist.length > 0 ? (
            <ul className="hosts">
              {estado.allowlist.map((entrada) => (
                <li key={entrada} className="mono">
                  {entrada}
                </li>
              ))}
            </ul>
          ) : (
            <Vacio icono="egresos" titulo="Vacía: no sale nada" />
          )}

          {web.length > 0 && (
            <>
              <h3 className="rotulo">Egreso web por agente</h3>
              <ul className="lista-filas">
                {web.map(([agente, hosts]) => (
                  <li key={agente}>
                    <div className="lista-fila-cabecera">
                      <span className="agente">{agente}</span>
                    </div>
                    <p className="evidencia mono">{hosts.join(" · ")}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section className="tarjeta" aria-labelledby="titulo-dlp">
          <h2 id="titulo-dlp">Reglas DLP</h2>
          <ul className="lista-filas">
            {estado.reglas.map((regla) => (
              <li key={regla.id}>
                <div className="lista-fila-cabecera">
                  <span>{nombreCausa(regla.id)}</span>
                  <Ficha tono={tonoModoDlp(regla.modo)}>{regla.modo === "bloquear" ? "Bloquea" : "Solo observa"}</Ficha>
                </div>
                <p className="evidencia mono">{regla.id}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="tarjeta" aria-labelledby="titulo-bloqueos">
        <h2 id="titulo-bloqueos">Bloqueos desde el arranque</h2>
        {bloqueos.length > 0 ? (
          <Barras filas={bloqueos} tono="bloquear" />
        ) : (
          <Vacio icono="escudo" titulo="Nada bloqueado todavía">
            Cuando una salida choque con la allowlist o el DLP, aparecerá aquí con su causa.
          </Vacio>
        )}
        {observados.length > 0 && (
          <>
            <h3 className="rotulo">Observadas (salieron, quedaron marcadas)</h3>
            <Barras filas={observados} tono="alerta" />
          </>
        )}
      </section>
    </div>
  );
}

/** Conteo por causa como barras horizontales: la más frecuente ocupa todo el ancho. */
function Barras({ filas, tono }: { filas: { causa: string; veces: number }[]; tono: "bloquear" | "alerta" }) {
  const maximo = Math.max(...filas.map((fila) => fila.veces), 1);
  return (
    <ul className={`barras tono-${tono}`}>
      {filas.map((fila) => (
        <li key={fila.causa}>
          <span className="barra-causa">{fila.causa}</span>
          <span className="barra-pista" aria-hidden="true">
            <span className="barra-relleno" style={{ width: `${(fila.veces / maximo) * 100}%` }} />
          </span>
          <span className="barra-valor mono">{fila.veces}</span>
        </li>
      ))}
    </ul>
  );
}
