import assert from "node:assert/strict";
import { test } from "node:test";

import { EJEMPLO_TRIADA } from "./ejemplos/triada.ts";
import { paginaDe } from "./rutas.ts";
import {
  DESCRIPCION_PATA,
  describirEvidencia,
  interpretarAnalisis,
  MAX_BYTES,
  PATAS,
  pesoManifiesto,
  prepararManifiesto,
} from "./triada.ts";

test("spec0002_e15_vacio", () => {
  const resultado = prepararManifiesto("   ");
  assert.equal(resultado.ok, false);
});

test("spec0002_e15_json_roto_con_mensaje_claro", () => {
  const resultado = prepararManifiesto("{tools: [}");
  assert.equal(resultado.ok, false);
  if (!resultado.ok) assert.match(resultado.error, /^No es un JSON válido/);
});

test("spec0002_e15_arreglo_no_es_manifiesto", () => {
  const resultado = prepararManifiesto("[1, 2]");
  assert.equal(resultado.ok, false);
});

test("spec0002_rf06_mas_de_1mb_no_se_envia", () => {
  const grande = JSON.stringify({ tools: [], relleno: "a".repeat(MAX_BYTES) });
  const resultado = prepararManifiesto(grande);
  assert.equal(resultado.ok, false);
  if (!resultado.ok) assert.match(resultado.error, /1 MB/);
});

test("spec0002_e14_ejemplo_es_valido", () => {
  assert.equal(prepararManifiesto(JSON.stringify(EJEMPLO_TRIADA)).ok, true);
});

test("spec0002_e14_reporte_200", () => {
  const reporte = {
    formato: "mcp",
    severidad: "critica",
    incompleto: false,
    severidad_peor_caso: null,
    faltan: [],
    patas: { datos_privados: [], no_confiable: [], salida_externa: [] },
    herramientas: [],
    recomendaciones: [],
  };
  const resultado = interpretarAnalisis({ tipo: "ok", status: 200, cuerpo: reporte });
  assert.equal(resultado.ok, true);
});

test("spec0002_e15_422_resume_los_errores", () => {
  const resultado = interpretarAnalisis({
    tipo: "ok",
    status: 422,
    cuerpo: { detail: [{ loc: ["herramientas", 0, "patas", 0], msg: "Input should be 'datos_privados'" }] },
  });
  assert.equal(resultado.ok, false);
  if (!resultado.ok) assert.match(resultado.error, /herramientas › 0 › patas › 0: Input should be/);
});

test("spec0002_e15_413_y_sin_respuesta", () => {
  const grande = interpretarAnalisis({ tipo: "ok", status: 413, cuerpo: null });
  const caida = interpretarAnalisis({ tipo: "sin_respuesta" });
  assert.ok(!grande.ok && grande.error.includes("1 MB"));
  assert.ok(!caida.ok && caida.error.includes("no responde"));
});

test("spec0002_e15_200_con_forma_rara_no_se_muestra", () => {
  const resultado = interpretarAnalisis({ tipo: "ok", status: 200, cuerpo: { severidad: "inventada" } });
  assert.equal(resultado.ok, false);
});

test("spec0002_e6_texto_de_evidencia", () => {
  assert.equal(
    describirEvidencia({ herramienta: "run_sql", origen: "regla", regla: "P-BD", fragmento: "sql" }),
    "regla P-BD: «sql»",
  );
  assert.equal(
    describirEvidencia({ herramienta: "x", origen: "declarado", regla: null, fragmento: null }),
    "declarado",
  );
});

test("spec0002_e14_rutas", () => {
  assert.equal(paginaDe("/"), "estado");
  assert.equal(paginaDe("/modulos/triada"), "triada");
  assert.equal(paginaDe("/modulos/triada/"), "triada");
  assert.equal(paginaDe("/modulos/secretos"), "secretos");
  assert.equal(paginaDe("/modulos/egresos"), "egresos");
  assert.equal(paginaDe("/modulos/inyeccion"), "inyeccion");
  assert.equal(paginaDe("/modulos/aprobacion"), "aprobacion");
  assert.equal(paginaDe("/otra"), "no_encontrada");
});

test("diseno_peso_del_manifiesto", () => {
  assert.equal(pesoManifiesto(""), "0 B de 1 MB");
  assert.equal(pesoManifiesto("ñ"), "2 B de 1 MB");
  assert.equal(pesoManifiesto("x".repeat(2458)), "2,4 KB de 1 MB");
});

test("diseno_cada_pata_tiene_descripcion", () => {
  for (const pata of PATAS) assert.ok(DESCRIPCION_PATA[pata].length > 0);
});
