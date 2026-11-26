import assert from "node:assert/strict";
import { test } from "node:test";

import {
  interpretarInyeccion,
  nombreModo,
  nombreOrigen,
  nombreRegla,
  resumenInyeccion,
  sesionesOrdenadas,
  totalBloqueos,
} from "./inyeccion.ts";
import type { EstadoInyeccion, SesionEstado } from "./inyeccion.ts";

function sesion(agente: string, contaminada: boolean): SesionEstado {
  return {
    id: `${agente}-sesion…`,
    agente,
    implicita: false,
    acotada: false,
    contaminada,
    origen: contaminada ? "web" : null,
    desde: contaminada ? "2026-11-26T12:00:00+00:00" : null,
  };
}

const ESTADO: EstadoInyeccion = {
  configurado: true,
  error: null,
  reglas: [
    { id: "iny.invisible", modo: "marcar", detecciones: 2 },
    { id: "iny.rol", modo: "bloquear", detecciones: 0 },
  ],
  marcadores: 1,
  ttl_minutos: 30,
  origenes_confiables: { soporte: ["memoria"] },
  sesiones: [sesion("soporte", false), sesion("lector", true), sesion("analista", true)],
  contadores: {
    sesiones_activas: 3,
    sesiones_contaminadas: 2,
    contaminaciones: 2,
    bloqueos_sesion_contaminada: 4,
    bloqueos_fuera_de_sesion: 1,
    bloqueos_contenido: 0,
  },
  avisos: [],
};

test("spec0005_e12_estado_200", () => {
  const resultado = interpretarInyeccion({ tipo: "ok", status: 200, cuerpo: ESTADO });
  assert.ok(resultado.ok);
  if (resultado.ok) {
    assert.equal(
      resumenInyeccion(resultado.estado),
      "3 sesiones activas · 2 contaminadas · 5 acciones contenidas desde el arranque",
    );
  }
});

test("spec0005_e12_singular", () => {
  const una: EstadoInyeccion = {
    ...ESTADO,
    sesiones: [sesion("lector", true)],
    contadores: { sesiones_activas: 1, sesiones_contaminadas: 1, bloqueos_sesion_contaminada: 1 },
  };
  assert.equal(resumenInyeccion(una), "1 sesión activa · 1 contaminada · 1 acción contenida desde el arranque");
  assert.equal(totalBloqueos(una), 1);
});

test("spec0005_e12_401_sin_respuesta_y_forma_rara", () => {
  const sinToken = interpretarInyeccion({ tipo: "ok", status: 401, cuerpo: { detail: "x" } });
  const caida = interpretarInyeccion({ tipo: "sin_respuesta" });
  assert.ok(!sinToken.ok && sinToken.error.includes("Token"));
  assert.ok(!caida.ok && caida.error.includes("no responde"));
  assert.equal(interpretarInyeccion({ tipo: "ok", status: 200, cuerpo: { configurado: true } }).ok, false);
  assert.equal(interpretarInyeccion({ tipo: "ok", status: 503, cuerpo: ESTADO }).ok, false);
});

test("spec0005_e13_contaminadas_primero", () => {
  assert.deepEqual(
    sesionesOrdenadas(ESTADO.sesiones).map((s) => s.agente),
    ["analista", "lector", "soporte"],
  );
  assert.equal(ESTADO.sesiones[0]?.agente, "soporte"); // no muta el original
});

test("spec0005_e13_nombres_legibles", () => {
  assert.equal(nombreRegla("iny.oculto"), "Texto oculto en HTML");
  assert.equal(nombreRegla("iny.nueva"), "iny.nueva");
  assert.equal(nombreOrigen("herramienta"), "Respuesta de una acción");
  assert.equal(nombreOrigen(null), "—");
  assert.equal(nombreModo("marcar"), "Marca y entrega");
});
