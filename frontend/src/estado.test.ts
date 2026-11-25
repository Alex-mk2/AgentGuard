import assert from "node:assert/strict";
import { test } from "node:test";

import { interpretarDependencias, interpretarVersion } from "./estado.ts";
import { MODULOS } from "./modulos.ts";

test("spec0001_e11_todo_ok", () => {
  const estado = interpretarDependencias({
    tipo: "ok",
    status: 200,
    cuerpo: { estado: "ok", dependencias: { postgres: "ok" } },
  });
  assert.deepEqual(estado, { api: "ok", postgres: "ok", mensaje: "Todo en orden." });
});

test("spec0001_e11_postgres_caido", () => {
  const estado = interpretarDependencias({
    tipo: "ok",
    status: 503,
    cuerpo: { estado: "degradado", dependencias: { postgres: "caida" } },
  });
  assert.equal(estado.api, "ok");
  assert.equal(estado.postgres, "caida");
});

test("spec0001_e12_api_sin_respuesta", () => {
  const estado = interpretarDependencias({ tipo: "sin_respuesta" });
  assert.equal(estado.api, "caida");
  assert.equal(estado.mensaje, "La API no responde.");
});

test("spec0001_e12_respuesta_inesperada_no_se_toma_como_ok", () => {
  // p. ej. un proxy que devuelve HTML con 200
  const estado = interpretarDependencias({ tipo: "ok", status: 200, cuerpo: null });
  assert.equal(estado.api, "caida");
  assert.equal(estado.postgres, "desconocido");
});

test("spec0001_rf10_version", () => {
  assert.equal(interpretarVersion({ tipo: "ok", status: 200, cuerpo: { version: "0.1.0" } }), "0.1.0");
  assert.equal(interpretarVersion({ tipo: "ok", status: 200, cuerpo: { version: 1 } }), null);
  assert.equal(interpretarVersion({ tipo: "sin_respuesta" }), null);
});

test("spec0001_e11_los_5_modulos_pendientes", () => {
  assert.equal(MODULOS.length, 5);
  assert.ok(MODULOS.every((modulo) => modulo.estado === "pendiente"));
});
