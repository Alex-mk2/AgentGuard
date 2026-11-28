import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { enviar } from "../api/cliente.ts";
import { EJEMPLO_TRIADA } from "../ejemplos/triada.ts";
import {
  DESCRIPCION_PATA,
  MAX_BYTES,
  NOMBRE_PATA,
  NOMBRE_SEVERIDAD,
  PATAS,
  describirEvidencia,
  interpretarAnalisis,
  pesoManifiesto,
  prepararManifiesto,
} from "../triada.ts";
import type { Pata, Reporte } from "../triada.ts";

/** Detector de la Tríada Letal (SPEC-0002 H5): pegar o cargar un manifiesto y ver el reporte. */
export function Triada() {
  const [texto, setTexto] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [reporte, setReporte] = useState<Reporte | null>(null);
  const [analizando, setAnalizando] = useState(false);

  async function analizar(evento: FormEvent) {
    evento.preventDefault();
    setReporte(null);
    const preparado = prepararManifiesto(texto);
    if (!preparado.ok) {
      setError(preparado.error);
      return;
    }
    setError(null);
    setAnalizando(true);
    const resultado = interpretarAnalisis(await enviar("/triada/analisis", preparado.cuerpo));
    setAnalizando(false);
    if (resultado.ok) setReporte(resultado.reporte);
    else setError(resultado.error);
  }

  async function cargarArchivo(evento: ChangeEvent<HTMLInputElement>) {
    const archivo = evento.target.files?.[0];
    evento.target.value = ""; // permite volver a elegir el mismo archivo
    if (!archivo) return;
    if (archivo.size > MAX_BYTES) {
      setError("El archivo supera el máximo de 1 MB.");
      return;
    }
    setTexto(await archivo.text());
    setError(null);
    setReporte(null);
  }

  return (
    <>
      <header className="titulo-pagina">
        <div>
          <h1 id="titulo-triada">Detector de la Tríada Letal</h1>
          <p className="bajada">
            Un agente que lee datos privados, ingiere contenido no confiable y puede enviar datos afuera puede ser
            llevado a exfiltrarlos con una inyección de prompt.
          </p>
        </div>
      </header>

      <section aria-labelledby="titulo-triada" className="tarjeta">
        <p className="ayuda">
          Pega el resultado de <code>tools/list</code> de un servidor MCP o un manifiesto de AgentGuard
          (con <code>herramientas</code>). El análisis no guarda nada.
        </p>
        <form onSubmit={(evento) => void analizar(evento)}>
          <div className="terminal">
            <div className="terminal-barra">
              <label htmlFor="manifiesto" className="mono">
                manifiesto.json
              </label>
              <span className="mono">{pesoManifiesto(texto)}</span>
            </div>
            <textarea
              id="manifiesto"
              className="manifiesto"
              value={texto}
              onChange={(evento) => setTexto(evento.target.value)}
              spellCheck={false}
              rows={14}
              placeholder='{"tools": [ ... ]}'
            />
          </div>
          <div className="acciones">
            <button type="submit" className="principal" disabled={analizando}>
              {analizando ? "Analizando…" : "Analizar"}
            </button>
            <label className="boton">
              Cargar .json
              <input type="file" accept=".json,application/json" onChange={(e) => void cargarArchivo(e)} hidden />
            </label>
            <button type="button" onClick={() => setTexto(JSON.stringify(EJEMPLO_TRIADA, null, 2))}>
              Ejemplo
            </button>
          </div>
        </form>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>

      {reporte ? (
        <VistaReporte reporte={reporte} />
      ) : (
        <section aria-labelledby="titulo-patas">
          <h2 id="titulo-patas" className="rotulo">
            Las tres patas
          </h2>
          <div className="patas">
            {PATAS.map((pata) => (
              <TarjetaPata key={pata} pata={pata} evidencias={null} />
            ))}
          </div>
          <p className="ayuda">Con las tres presentes y sin control de egresos, la severidad es crítica.</p>
        </section>
      )}
    </>
  );
}

/** Una pata de la tríada. Sin reporte (`null`) se muestra apagada, con lo que significa. */
function TarjetaPata({ pata, evidencias }: { pata: Pata; evidencias: Reporte["patas"][Pata] | null }) {
  const presente = evidencias !== null && evidencias.length > 0;
  const estado = evidencias === null ? "apagada" : presente ? "presente" : "ausente";
  return (
    <div className={`pata pata-${estado}`}>
      <h3>
        <span className="pata-numero mono">{PATAS.indexOf(pata) + 1}</span>
        {NOMBRE_PATA[pata]}
      </h3>
      {evidencias === null ? (
        <p className="vacio">{DESCRIPCION_PATA[pata]}</p>
      ) : !presente ? (
        <p className="vacio">Ninguna herramienta</p>
      ) : (
        <ul>
          {evidencias.map((evidencia, i) => (
            <li key={`${evidencia.herramienta}-${evidencia.regla ?? evidencia.origen}-${i}`}>
              <code>{evidencia.herramienta}</code>
              <span className="evidencia">{describirEvidencia(evidencia)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VistaReporte({ reporte }: { reporte: Reporte }) {
  return (
    <section aria-labelledby="titulo-reporte" className="tarjeta" role="status">
      <h2 id="titulo-reporte">
        Severidad: <span className={`severidad severidad-${reporte.severidad}`}>{NOMBRE_SEVERIDAD[reporte.severidad]}</span>
      </h2>
      {reporte.incompleto && reporte.severidad_peor_caso && (
        <p className="aviso">
          Análisis incompleto: hay herramientas sin clasificar. En el peor caso la severidad sería{" "}
          <strong>{NOMBRE_SEVERIDAD[reporte.severidad_peor_caso]}</strong>.
        </p>
      )}

      <div className="patas">
        {PATAS.map((pata) => (
          <TarjetaPata key={pata} pata={pata} evidencias={reporte.patas[pata]} />
        ))}
      </div>

      {reporte.recomendaciones.length > 0 && (
        <>
          <h3>Recomendaciones</h3>
          <ul className="recomendaciones">
            {reporte.recomendaciones.map((recomendacion, i) => (
              <li key={`${recomendacion.id}-${i}`}>{recomendacion.texto}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Herramientas</h3>
      <table className="tabla">
        <thead>
          <tr>
            <th scope="col">Herramienta</th>
            <th scope="col">Patas</th>
            <th scope="col">Clasificación</th>
            <th scope="col">Salida</th>
          </tr>
        </thead>
        <tbody>
          {reporte.herramientas.map((herramienta) => (
            <tr key={herramienta.nombre}>
              <td>
                <code>{herramienta.nombre}</code>
                {herramienta.multipata && <span className="etiqueta">varias patas</span>}
              </td>
              <td>{herramienta.patas.map((pata) => NOMBRE_PATA[pata]).join(", ") || "—"}</td>
              <td>{herramienta.clasificacion.replace("_", " ")}</td>
              <td>{herramienta.patas.includes("salida_externa") ? (herramienta.egreso_restringido ? "allowlist" : "libre") : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
