// Piezas visuales compartidas por las pantallas (sistema de diseño «Tactical Terminal»).
// La lógica vive en diseno.ts para probarla sin JSX.

import { useRef } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";

import { contarLineas, fichasJson } from "./diseno.ts";
import type { Cifra, Tono } from "./diseno.ts";
import type { Pagina } from "./rutas.ts";

export function TituloPagina({ titulo, bajada, children }: { titulo: string; bajada: ReactNode; children?: ReactNode }) {
  return (
    <header className="titulo-pagina">
      <div>
        <h1>{titulo}</h1>
        <div className="bajada">{bajada}</div>
      </div>
      {children}
    </header>
  );
}

interface PropsAcceso {
  id: string;
  token: string;
  setToken: (token: string) => void;
  consultando: boolean;
  cargado: boolean;
  alEnviar: () => void;
}

/** El token de administración: vive en el estado del componente que lo usa, nunca en localStorage. */
export function AccesoAdmin({ id, token, setToken, consultando, cargado, alEnviar }: PropsAcceso) {
  function enviar(evento: FormEvent) {
    evento.preventDefault();
    alEnviar();
  }
  return (
    <form onSubmit={enviar} className="acceso">
      <label htmlFor={id} className="oculto">
        Token de administración
      </label>
      <input
        id={id}
        type="password"
        className="campo"
        autoComplete="off"
        placeholder="Token de administración"
        value={token}
        onChange={(evento) => setToken(evento.target.value)}
      />
      <button type="submit" className="principal" disabled={consultando}>
        {consultando ? "Consultando…" : cargado ? "Actualizar" : "Consultar"}
      </button>
    </form>
  );
}

export function Cifras({ cifras, etiqueta }: { cifras: readonly Cifra[]; etiqueta: string }) {
  return (
    <ul className="cifras" aria-label={etiqueta}>
      {cifras.map((cifra) => (
        <li key={cifra.id} className={`cifra tono-${cifra.tono}`}>
          <span className="cifra-titulo">{cifra.titulo}</span>
          <span className="cifra-valor">{cifra.valor}</span>
          <span className="cifra-detalle">{cifra.detalle}</span>
        </li>
      ))}
    </ul>
  );
}

export function Ficha({ tono, children }: { tono: Tono; children: ReactNode }) {
  return <span className={`ficha tono-${tono}`}>{children}</span>;
}

/** Lo que se ve mientras llega la primera respuesta: la forma de la pantalla, sin datos. */
export function Esqueleto({ cifras = 4, filas = 3 }: { cifras?: number; filas?: number }) {
  return (
    <div className="esqueleto" aria-hidden="true">
      <div className="cifras">
        {Array.from({ length: cifras }, (_, i) => (
          <div key={i} className="cifra esqueleto-bloque" />
        ))}
      </div>
      <div className="tarjeta">
        {Array.from({ length: filas }, (_, i) => (
          <div key={i} className="esqueleto-linea" />
        ))}
      </div>
    </div>
  );
}

/** Estado vacío: un ícono, qué significa y, si hace falta, qué hacer. */
export function Vacio({ icono, titulo, children }: { icono: Pagina | "escudo"; titulo: string; children?: ReactNode }) {
  return (
    <div className="vacio-bloque">
      {icono === "escudo" ? <Escudo /> : <Icono id={icono} />}
      <p className="vacio-titulo">{titulo}</p>
      {children && <p className="vacio-texto">{children}</p>}
    </div>
  );
}

/** Íconos de línea (24×24, trazo), dibujados a mano: sin librería de íconos. */
const TRAZOS: Partial<Record<Pagina, readonly string[]>> = {
  estado: ["M3 12h4l3-8 4 16 3-8h4"],
  triada: ["M12 3.5 2.8 19.5h18.4Z", "M12 10v4", "M12 16.8v.2"],
  secretos: ["M7.5 19a4.5 4.5 0 1 1 3.6-7.2", "M11.1 11.8 20 3", "M16.5 6.5l2.5 2.5", "M14 9l2 2"],
  egresos: ["M14 4h6v6", "M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  inyeccion: ["M3.5 4.5h17l-6.5 7.5v6l-4 2v-8Z"],
  aprobacion: [
    "M9 11.5a3.75 3.75 0 1 0 0-7.5 3.75 3.75 0 0 0 0 7.5Z",
    "M2.5 20.5c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6",
    "m16 11 2 2 4-4",
  ],
};

export function Icono({ id, clase = "icono" }: { id: Pagina; clase?: string }) {
  return (
    <svg className={clase} viewBox="0 0 24 24" aria-hidden="true">
      {(TRAZOS[id] ?? []).map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

export function Escudo({ clase = "icono" }: { clase?: string }) {
  return (
    <svg className={clase} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.5 4 5.5v6c0 4.9 3.4 8.6 8 10 4.6-1.4 8-5.1 8-10v-6l-8-3Z" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </svg>
  );
}

interface PropsEditor {
  id: string;
  valor: string;
  alCambiar: (valor: string) => void;
  placeholder: string;
  filas: number;
}

/** Editor JSON tipo terminal: números de línea y resaltado. El texto real lo escribe un textarea
 * transparente; debajo, un <pre> con las mismas medidas pinta los colores con spans de React
 * (nunca innerHTML: lo pegado puede ser hostil). Sin envolver líneas, para que ambos coincidan. */
export function EditorJson({ id, valor, alCambiar, placeholder, filas }: PropsEditor) {
  const pintado = useRef<HTMLPreElement>(null);
  const margen = useRef<HTMLDivElement>(null);
  const lineas = contarLineas(valor);

  function sincronizar(evento: { currentTarget: HTMLTextAreaElement }) {
    const { scrollTop, scrollLeft } = evento.currentTarget;
    if (pintado.current) {
      pintado.current.scrollTop = scrollTop;
      pintado.current.scrollLeft = scrollLeft;
    }
    if (margen.current) margen.current.scrollTop = scrollTop;
  }

  return (
    <div className="editor" style={{ "--filas": filas } as CSSProperties}>
      <div className="editor-margen" ref={margen} aria-hidden="true">
        {Array.from({ length: Math.max(lineas, filas) }, (_, i) => (
          <span key={i} className={i < lineas ? "" : "editor-margen-vacia"}>
            {i + 1}
          </span>
        ))}
      </div>
      <div className="editor-cuerpo">
        <pre className="editor-pintado" ref={pintado} aria-hidden="true">
          {fichasJson(valor).map((ficha, i) =>
            ficha.tipo === "texto" ? ficha.texto : (
              <span key={i} className={`json-${ficha.tipo}`}>
                {ficha.texto}
              </span>
            ),
          )}
          {/* un salto extra: si el texto termina en «\n», la última línea vacía también ocupa lugar */}
          {"\n"}
        </pre>
        <textarea
          id={id}
          className="editor-texto"
          value={valor}
          onChange={(evento) => alCambiar(evento.target.value)}
          onScroll={sincronizar}
          spellCheck={false}
          wrap="off"
          autoCapitalize="off"
          autoCorrect="off"
          placeholder={placeholder}
        />
      </div>
    </div>
  );
}
