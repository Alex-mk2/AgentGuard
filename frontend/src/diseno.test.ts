import assert from "node:assert/strict";
import { test } from "node:test";

import { contarLineas, fichasJson, plural, suma } from "./diseno.ts";
import { cifrasEgresos, tonoModoDlp } from "./egresos.ts";
import type { EstadoEgresos } from "./egresos.ts";
import { cifrasInyeccion, tonoModo } from "./inyeccion.ts";
import type { EstadoInyeccion } from "./inyeccion.ts";
import { cifrasBroker, tonoAccion } from "./secretos.ts";
import type { AccionEstado, EstadoBroker } from "./secretos.ts";

test("diseno_plural_y_suma", () => {
  assert.equal(plural(1, "regla", "reglas"), "1 regla");
  assert.equal(plural(0, "regla", "reglas"), "0 reglas");
  assert.equal(suma({ a: 2, b: 3 }), 5);
  assert.equal(suma({}), 0);
});

test("diseno_fichas_json_reconstruyen_el_texto_exacto", () => {
  const textos = [
    '{"tools": [{"name": "leer", "n": -1.5e3, "ok": true, "x": null}]}',
    '{"a": "con \\"comillas\\" y \\\\", "b":\n  [1, 2]}',
    '{"sin cerrar": "abc',
    "no es json { ni de cerca ]",
    "",
  ];
  for (const texto of textos) {
    assert.equal(
      fichasJson(texto)
        .map((f) => f.texto)
        .join(""),
      texto,
    );
  }
});

test("diseno_fichas_json_distinguen_claves_de_valores", () => {
  const fichas = fichasJson('{"name": "leer", "n": 3, "ok": false}').filter((f) => f.tipo !== "texto");
  assert.deepEqual(
    fichas.map((f) => [f.tipo, f.texto]),
    [
      ["puntuacion", "{"],
      ["clave", '"name"'],
      ["puntuacion", ":"],
      ["cadena", '"leer"'],
      ["puntuacion", ","],
      ["clave", '"n"'],
      ["puntuacion", ":"],
      ["numero", "3"],
      ["puntuacion", ","],
      ["clave", '"ok"'],
      ["puntuacion", ":"],
      ["literal", "false"],
      ["puntuacion", "}"],
    ],
  );
});

test("diseno_contar_lineas", () => {
  assert.equal(contarLineas(""), 1);
  assert.equal(contarLineas("a\nb\n"), 3);
});

function accion(id: string, disponible: boolean, bloqueada = false): AccionEstado {
  return { id, descripcion: "", secreto: "s", host: "h", bloqueada_por_egresos: bloqueada, disponible };
}

test("diseno_broker_tonos_y_cifras", () => {
  assert.equal(tonoAccion(accion("a", true)), "permitir");
  assert.equal(tonoAccion(accion("a", false)), "alerta");
  assert.equal(tonoAccion(accion("a", false, true)), "bloquear");
  const estado: EstadoBroker = {
    configurado: true,
    error: null,
    acciones: [accion("a", true), accion("b", false, true), accion("c", false)],
    agentes: [
      { id: "x", acciones: [], max_por_minuto: 1, web: [], token_cargado: true },
      { id: "y", acciones: [], max_por_minuto: 1, web: [], token_cargado: false },
    ],
    secretos: [
      { nombre: "s1", cargado: true, compartido: false, acciones: [] },
      { nombre: "s2", cargado: false, compartido: false, acciones: [] },
    ],
    avisos: [],
  };
  const cifras = cifrasBroker(estado);
  assert.deepEqual(
    cifras.map((c) => [c.id, c.valor, c.tono]),
    [
      ["acciones", 1, "alerta"],
      ["secretos", 1, "alerta"],
      ["agentes", 2, "alerta"],
      ["bloqueadas", 1, "bloquear"],
    ],
  );
  assert.equal(cifras[1]?.detalle, "faltan 1");
});

test("diseno_egresos_sin_allowlist_es_rojo", () => {
  assert.equal(tonoModoDlp("bloquear"), "bloquear");
  assert.equal(tonoModoDlp("observar"), "neutro");
  const estado: EstadoEgresos = {
    configurado: false,
    error: null,
    allowlist: [],
    reglas: [
      { id: "r1", modo: "bloquear" },
      { id: "r2", modo: "observar" },
    ],
    marcadores: 1,
    bloqueos: { allowlist: 2, dlp: 1 },
    observados: {},
    web: {},
  };
  const cifras = cifrasEgresos(estado);
  assert.deepEqual(
    cifras.map((c) => [c.id, c.valor, c.tono]),
    [
      ["allowlist", 0, "bloquear"],
      ["dlp", 2, "marca"],
      ["bloqueos", 3, "bloquear"],
      ["observados", 0, "neutro"],
    ],
  );
  assert.equal(cifras[1]?.detalle, "1 bloquean · 1 marcador");
});

test("diseno_inyeccion_tonos_y_cifras", () => {
  assert.equal(tonoModo("bloquear"), "bloquear");
  assert.equal(tonoModo("marcar"), "alerta");
  assert.equal(tonoModo("observar"), "neutro");
  const estado: EstadoInyeccion = {
    configurado: true,
    error: null,
    reglas: [
      { id: "a", modo: "marcar", detecciones: 2 },
      { id: "b", modo: "bloquear", detecciones: 1 },
    ],
    marcadores: 0,
    ttl_minutos: 60,
    origenes_confiables: {},
    sesiones: [],
    contadores: { sesiones_activas: 3, sesiones_contaminadas: 1, bloqueos_sesion_contaminada: 2 },
    avisos: [],
  };
  assert.deepEqual(
    cifrasInyeccion(estado).map((c) => [c.id, c.valor, c.tono]),
    [
      ["sesiones", 3, "marca"],
      ["contaminadas", 1, "alerta"],
      ["detecciones", 3, "alerta"],
      ["contenidas", 2, "bloquear"],
    ],
  );
});
